from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from apps.social.models import FriendRequest, UserBlock
from .models import Conversation, Message

User = get_user_model()


def _blocked_either_way(first, second):
    return UserBlock.objects.filter(
        Q(blocker=first, blocked=second) | Q(blocker=second, blocked=first)
    ).exists()


def _are_friends(first, second):
    return FriendRequest.objects.filter(
        Q(requester=first, recipient=second) | Q(requester=second, recipient=first),
        status=FriendRequest.Status.ACCEPTED,
    ).exists()


@login_required
def chat_home(request):
    conversations = Conversation.objects.filter(
        Q(user_one=request.user) | Q(user_two=request.user)
    ).prefetch_related("messages")
    chat_rows = []
    for conversation in conversations:
        other = conversation.other_user(request.user)
        if not other or _blocked_either_way(request.user, other) or not _are_friends(request.user, other):
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
    if other.pk == request.user.pk or _blocked_either_way(request.user, other) or not _are_friends(request.user, other):
        messages.error(request, "Chat ke liye pehle friend request accept honi chahiye. Blocked players chat nahi kar sakte.")
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
    if _blocked_either_way(request.user, other) or not _are_friends(request.user, other):
        messages.error(request, "Ye chat ab available nahi hai.")
        return redirect("chat:home")

    if request.method == "POST":
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
    })


@require_GET
@login_required
def poll_messages(request, conversation_id):
    conversation = get_object_or_404(Conversation.objects.select_related("user_one", "user_two"), pk=conversation_id)
    other = conversation.other_user(request.user)
    if not other or _blocked_either_way(request.user, other) or not _are_friends(request.user, other):
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
