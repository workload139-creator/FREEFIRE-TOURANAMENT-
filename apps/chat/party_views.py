from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from apps.social.models import PlayerShopWallet
from .party_models import PartyRoom, PartyRoomMembership, PartyRoomMessage, PartyRoomGift, CommunityTournament, CommunityTournamentEntry

GIFTS = {
    "rose": ("🌹", "Rose", 2),
    "heart": ("💖", "Heart", 10),
    "teddy": ("🧸", "Teddy Bear", 20),
    "crown": ("👑", "Champion Crown", 50),
    "trophy": ("🏆", "Golden Trophy", 100),
}
CURRENCIES = {"diamonds": "diamonds", "coins": "coins", "fan_tokens": "fan_tokens"}


@login_required
def party_home(request):
    rooms = PartyRoom.objects.filter(is_open=True, visibility=PartyRoom.Visibility.PUBLIC).select_related("host").annotate(people=Count("memberships")).order_by("-people", "-updated_at")
    tournaments = CommunityTournament.objects.filter(status=CommunityTournament.Status.OPEN).select_related("host").annotate(people=Count("entries")).order_by("starts_at")
    return render(request, "chat/party.html", {"rooms": rooms, "tournaments": tournaments, "themes": PartyRoom._meta.get_field("theme").choices, "modes": CommunityTournament._meta.get_field("game_mode").choices})


@login_required
@require_POST
def create_party_room(request):
    title = request.POST.get("title", "").strip()[:70]
    if not title:
        messages.error(request, "Room ka naam likho.")
        return redirect("chat:party")
    try:
        capacity = int(request.POST.get("max_members", "12"))
    except ValueError:
        capacity = 12
    if capacity < 2 or capacity > 30:
        messages.error(request, "Room capacity 2 se 30 ke beech rakho.")
        return redirect("chat:party")
    visibility = request.POST.get("visibility", "public")
    if visibility not in ("public", "private"):
        visibility = "public"
    room = PartyRoom.objects.create(
        host=request.user, title=title, description=request.POST.get("description", "").strip()[:240],
        theme=request.POST.get("theme", "violet") if request.POST.get("theme") in ("violet", "gold", "ocean", "fire") else "violet",
        visibility=visibility, passcode=request.POST.get("passcode", "").strip()[:24] if visibility == "private" else "",
        max_members=capacity,
    )
    PartyRoomMembership.objects.get_or_create(room=room, user=request.user)
    messages.success(request, "Room ban gaya! Ab doston ko invite karo.")
    return redirect("chat:party_room", room_id=room.pk)


@login_required
def party_room(request, room_id):
    room = get_object_or_404(PartyRoom.objects.select_related("host"), pk=room_id)
    membership = PartyRoomMembership.objects.filter(room=room, user=request.user).first()
    if room.visibility == "private" and not membership:
        if request.method == "POST" and request.POST.get("action") == "join":
            if request.POST.get("passcode", "") != room.passcode:
                messages.error(request, "Private room code galat hai.")
                return redirect("chat:party")
    if request.method == "POST":
        action = request.POST.get("action", "message")
        if action == "join":
            if not room.is_open:
                messages.error(request, "Room band hai.")
            elif room.memberships.count() >= room.max_members and not membership:
                messages.error(request, "Room full hai.")
            else:
                PartyRoomMembership.objects.get_or_create(room=room, user=request.user)
                messages.success(request, "Room join ho gaya.")
            return redirect("chat:party_room", room_id=room.pk)
        if not membership:
            messages.error(request, "Pehle room join karo.")
            return redirect("chat:party_room", room_id=room.pk)
        if action == "message":
            body = request.POST.get("body", "").strip()[:1000]
            if body:
                PartyRoomMessage.objects.create(room=room, sender=request.user, body=body)
                PartyRoom.objects.filter(pk=room.pk).update(updated_at=timezone.now())
        elif action == "gift":
            code = request.POST.get("gift_code", "")
            currency = request.POST.get("currency", "diamonds")
            recipient_id = request.POST.get("recipient_id")
            if code not in GIFTS or currency not in CURRENCIES:
                messages.error(request, "Gift select sahi nahi hai.")
            else:
                recipient_membership = get_object_or_404(PartyRoomMembership, room=room, user_id=recipient_id)
                if recipient_membership.user_id == request.user.pk:
                    messages.error(request, "Apne aap ko gift nahi bhej sakte.")
                else:
                    emoji, label, quantity = GIFTS[code]
                    with transaction.atomic():
                        sender_wallet, _ = PlayerShopWallet.objects.get_or_create(user=request.user)
                        receiver_wallet, _ = PlayerShopWallet.objects.get_or_create(user=recipient_membership.user)
                        sender_wallet = PlayerShopWallet.objects.select_for_update().get(pk=sender_wallet.pk)
                        receiver_wallet = PlayerShopWallet.objects.select_for_update().get(pk=receiver_wallet.pk)
                        field = CURRENCIES[currency]
                        if getattr(sender_wallet, field) < quantity:
                            messages.error(request, "Gift bhejne ke liye wallet balance kaafi nahi hai.")
                        else:
                            setattr(sender_wallet, field, getattr(sender_wallet, field) - quantity)
                            setattr(receiver_wallet, field, getattr(receiver_wallet, field) + quantity)
                            sender_wallet.save(update_fields=[field, "updated_at"])
                            receiver_wallet.save(update_fields=[field, "updated_at"])
                            PartyRoomGift.objects.create(room=room, sender=request.user, recipient=recipient_membership.user, gift_code=code, currency=currency, quantity=quantity)
                            PartyRoomMessage.objects.create(room=room, sender=request.user, body=f"{emoji} {request.user.username} ne {recipient_membership.user.username} ko {label} gift kiya!")
                            messages.success(request, f"{label} gift bhej diya.")
        elif action == "leave":
            if request.user.pk == room.host_id:
                room.is_open = False
                room.save(update_fields=["is_open", "updated_at"])
            else:
                PartyRoomMembership.objects.filter(room=room, user=request.user).delete()
            return redirect("chat:party")
        return redirect("chat:party_room", room_id=room.pk)
    PartyRoomMembership.objects.filter(room=room, user=request.user).update(last_seen_at=timezone.now())
    members = room.memberships.select_related("user").order_by("joined_at")
    room_messages = room.room_messages.select_related("sender").order_by("-pk")[:100]
    return render(request, "chat/party_room.html", {"room": room, "members": members, "room_messages": list(reversed(room_messages)), "gifts": [{"code": code, "emoji": values[0], "name": values[1], "price": values[2]} for code, values in GIFTS.items()], "joined": bool(membership)})


@login_required
@require_GET
def party_poll(request, room_id):
    room = get_object_or_404(PartyRoom, pk=room_id)
    if not PartyRoomMembership.objects.filter(room=room, user=request.user).exists():
        return JsonResponse({"error": "Join this room first."}, status=403)
    try:
        after = max(0, int(request.GET.get("after", "0")))
    except (ValueError, TypeError):
        after = 0
    items = PartyRoomMessage.objects.filter(room=room, pk__gt=after).select_related("sender").order_by("pk")[:100]
    return JsonResponse({"messages": [{"id": item.pk, "sender": item.sender.username, "body": item.body, "time": timezone.localtime(item.created_at).strftime("%H:%M"), "mine": item.sender_id == request.user.pk} for item in items]})


@login_required
@require_POST
def create_community_tournament(request):
    title = request.POST.get("title", "").strip()[:90]
    starts = request.POST.get("starts_at", "").strip()
    mode = request.POST.get("game_mode", "BR")
    if not title or mode not in dict(CommunityTournament._meta.get_field("game_mode").choices):
        messages.error(request, "Tournament ka naam aur valid mode bharo.")
        return redirect("chat:party")
    from django.utils.dateparse import parse_datetime
    starts_at = parse_datetime(starts)
    if not starts_at:
        messages.error(request, "Start date aur time sahi select karo.")
        return redirect("chat:party")
    if timezone.is_naive(starts_at):
        starts_at = timezone.make_aware(starts_at, timezone.get_current_timezone())
    if starts_at <= timezone.now():
        messages.error(request, "Tournament ka time future mein hona chahiye.")
        return redirect("chat:party")
    try:
        capacity = int(request.POST.get("max_players", "12"))
    except ValueError:
        capacity = 12
    if capacity < 2 or capacity > 49:
        messages.error(request, "Players 2 se 49 ke beech rakho.")
        return redirect("chat:party")
    CommunityTournament.objects.create(host=request.user, title=title, game_mode=mode, description=request.POST.get("description", "").strip()[:500], starts_at=starts_at, max_players=capacity, entry_note=request.POST.get("entry_note", "").strip()[:120])
    messages.success(request, "Community tournament create ho gaya.")
    return redirect("chat:party")


@login_required
@require_POST
def join_community_tournament(request, tournament_id):
    tournament = get_object_or_404(CommunityTournament, pk=tournament_id)
    with transaction.atomic():
        tournament = CommunityTournament.objects.select_for_update().get(pk=tournament.pk)
        if tournament.status != CommunityTournament.Status.OPEN or tournament.starts_at <= timezone.now():
            messages.error(request, "Is tournament ki registration band hai.")
        elif tournament.entries.count() >= tournament.max_players:
            messages.error(request, "Tournament full hai.")
        else:
            _, created = CommunityTournamentEntry.objects.get_or_create(tournament=tournament, user=request.user)
            messages.success(request, "Tournament join ho gaya." if created else "Tum pehle se registered ho.")
    return redirect("chat:party")
