from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from apps.social.models import Follow, UserBlock, PlayerShopWallet, CurrencyGift
from .models import Conversation, Message

User = get_user_model()


def _blocked_either_way(first, second):
    return UserBlock.objects.filter(
        Q(blocker=first, blocked=second) | Q(blocker=second, blocked=first)
    ).exists()


def _can_chat(first, second):
    # One follow is enough to start a chat; the followed player can reply.
    return Follow.objects.filter(
        Q(follower=first, following=second) | Q(follower=second, following=first)
    ).exists()


@login_required
def chat_home(request):
    conversations = Conversation.objects.filter(
        Q(user_one=request.user) | Q(user_two=request.user)
    ).prefetch_related("messages")
    chat_rows = []
    for conversation in conversations:
        other = conversation.other_user(request.user)
        if not other or _blocked_either_way(request.user, other) or not _can_chat(request.user, other):
            continue
        last_message = conversation.messages.order_by("-created_at", "-pk").first()
        unread_count = conversation.messages.filter(
            read_at__isnull=True
        ).exclude(sender=request.user).count()
        chat_rows.append({
            "conversation": conversation,
            "other": other,
            "last_message": last_message,
            "unread_count": unread_count,
        })
    return render(request, "chat/home.html", {"chat_rows": chat_rows})


@login_required
def open_chat(request, user_id):
    other = get_object_or_404(User, pk=user_id)
    if other.pk == request.user.pk or _blocked_either_way(request.user, other) or not Follow.objects.filter(follower=request.user, following=other).exists():
        messages.error(request, "Chat shuru karne ke liye pehle player ko follow karein. Blocked players chat nahi kar sakte.")
        return redirect("social:home")

    first, second = sorted((request.user, other), key=lambda user: user.pk)
    with transaction.atomic():
        conversation, _ = Conversation.objects.get_or_create(user_one=first, user_two=second)
    return redirect("chat:conversation", conversation_id=conversation.pk)


@login_required
def conversation_detail(request, conversation_id):
    conversation = get_object_or_404(
        Conversation.objects.select_related("user_one", "user_two"),
        pk=conversation_id,
    )
    other = conversation.other_user(request.user)
    if not other:
        return redirect("chat:home")
    if _blocked_either_way(request.user, other) or not _can_chat(request.user, other):
        messages.error(request, "Ye chat ab available nahi hai.")
        return redirect("chat:home")

    if request.method == "POST":
        action = request.POST.get("action", "message")
        if action == "gift":
            currency = request.POST.get("currency")
            try:
                quantity = int(request.POST.get("quantity", "0"))
            except (TypeError, ValueError):
                quantity = 0
            if currency not in ("diamonds", "coins", "fan_tokens") or quantity < 1 or quantity > 10000:
                messages.error(request, "Valid gift amount select karein (1–10000).")
            else:
                with transaction.atomic():
                    sender_wallet, _ = PlayerShopWallet.objects.get_or_create(user=request.user)
                    recipient_wallet, _ = PlayerShopWallet.objects.get_or_create(user=other)
                    sender_wallet = PlayerShopWallet.objects.select_for_update().get(pk=sender_wallet.pk)
                    recipient_wallet = PlayerShopWallet.objects.select_for_update().get(pk=recipient_wallet.pk)
                    field = {"diamonds": "diamonds", "coins": "coins", "fan_tokens": "fan_tokens"}[currency]
                    if getattr(sender_wallet, field) < quantity:
                        messages.error(request, "Gift bhejne ke liye aapka balance kaafi nahi hai. Shop check karein.")
                    else:
                        setattr(sender_wallet, field, getattr(sender_wallet, field) - quantity)
                        setattr(recipient_wallet, field, getattr(recipient_wallet, field) + quantity)
                        sender_wallet.save(update_fields=[field, "updated_at"])
                        recipient_wallet.save(update_fields=[field, "updated_at"])
                        CurrencyGift.objects.create(sender=request.user, recipient=other, currency=currency, quantity=quantity, conversation_id=conversation.pk)
                        gift_label = {"diamonds": "💎 diamonds", "coins": "🪙 coins", "fan_tokens": "✨ Fan Tokens"}[currency]
                        Message.objects.create(conversation=conversation, sender=request.user, body=f"🎁 Sent {quantity} {gift_label} to {other.username}!")
                        Conversation.objects.filter(pk=conversation.pk).update(updated_at=timezone.now())
                        messages.success(request, "Gift chat mein bhej diya!")
            return redirect("chat:conversation", conversation_id=conversation.pk)
        body = request.POST.get("body", "").strip()
        if not body:
            messages.error(request, "Khali message nahi bhej sakte.")
        elif len(body) > 2000:
            messages.error(request, "Message 2000 characters se chhota rakho.")
        else:
            Message.objects.create(conversation=conversation, sender=request.user, body=body)
            Conversation.objects.filter(pk=conversation.pk).update(updated_at=timezone.now())
        return redirect("chat:conversation", conversation_id=conversation.pk)

    Message.objects.filter(
        conversation=conversation, read_at__isnull=True
    ).exclude(sender=request.user).update(read_at=timezone.now())
    chat_messages = conversation.messages.select_related("sender").order_by("-created_at", "-pk")[:100]
    chat_messages = list(reversed(chat_messages))
    return render(request, "chat/conversation.html", {
        "conversation": conversation,
        "other": other,
        "chat_messages": chat_messages,
        "last_message_id": chat_messages[-1].pk if chat_messages else 0,
    })


@require_GET
@login_required
def poll_messages(request, conversation_id):
    conversation = get_object_or_404(Conversation.objects.select_related("user_one", "user_two"), pk=conversation_id)
    other = conversation.other_user(request.user)
    if not other or _blocked_either_way(request.user, other) or not _can_chat(request.user, other):
        return JsonResponse({"error": "Chat unavailable."}, status=403)

    try:
        after_id = max(0, int(request.GET.get("after", "0")))
    except (TypeError, ValueError):
        after_id = 0

    unread = Message.objects.filter(
        conversation=conversation, read_at__isnull=True
    ).exclude(sender=request.user)
    unread.update(read_at=timezone.now())

    new_messages = Message.objects.filter(conversation=conversation, pk__gt=after_id).select_related("sender").order_by("pk")[:100]
    return JsonResponse({
        "messages": [{
            "id": item.pk,
            "sender": item.sender.username,
            "body": item.body,
            "created_at": timezone.localtime(item.created_at).strftime("%d %b, %I:%M %p"),
            "mine": item.sender_id == request.user.pk,
        } for item in new_messages]
    })


@require_POST
@login_required
def send_message(request, conversation_id):
    return conversation_detail(request, conversation_id)
