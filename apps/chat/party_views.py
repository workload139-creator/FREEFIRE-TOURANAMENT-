from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from datetime import timedelta
import random
import re
from django.views.decorators.http import require_GET, require_POST

from apps.social.models import PlayerShopWallet
from .party_models import PartyRoom, PartyRoomMembership, PartyRoomMessage, PartyRoomGift, CommunityTournament, CommunityTournamentEntry, PartyRoomGameAnswer

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
    return render(request, "chat/party.html", {"rooms": rooms, "themes": PartyRoom._meta.get_field("theme").choices})


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
    capacity = 12
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
                room.refresh_from_db()
                if room.game_status == "waiting" and room.memberships.count() >= 12:
                    start_party_game(room)
                messages.success(request, "Room join ho gaya.")
            return redirect("chat:party_room", room_id=room.pk)
        if not membership:
            messages.error(request, "Pehle room join karo.")
            return redirect("chat:party_room", room_id=room.pk)
        if action == "start_game":
            if request.user.pk != room.host_id:
                messages.error(request, "Game sirf host start kar sakta hai.")
            elif room.game_status not in ("waiting", "finished"):
                messages.info(request, "Game pehle hi start ho chuka hai.")
            elif room.memberships.count() < 2:
                messages.error(request, "Game start karne ke liye kam se kam 2 players chahiye.")
            else:
                start_party_game(room)
                messages.success(request, "3-round FF Quiz start ho gaya!")
        elif action == "message":
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
    return render(request, "chat/party_room.html", {"room": room, "members": members, "room_messages": list(reversed(room_messages)), "gifts": [{"code": code, "emoji": values[0], "name": values[1], "price": values[2]} for code, values in GIFTS.items()], "joined": bool(membership), "game_answers": room.game_answers.filter(round_number=room.game_round).select_related("player")})


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


# Timed, non-cash three-round Free Fire quiz for Party Rooms.
PARTY_QUIZ = {
    1: [
        ("Free Fire mein safe zone se bahar rehne par kya hota hai?", "damage"),
        ("Knocked teammate ko bachane ke liye kya karte hain?", "revive"),
        ("Battle Royale ka short form kya hai?", "br"),
        ("Headshot kis body part par hit hota hai?", "head"),
        ("Gloo wall ka main use kya hai?", "cover"),
    ],
    2: [
        ("Free Fire mein medkit ka use kya hai?", "heal"),
        ("Teammate ko location batane ke liye kya use karte hain?", "ping"),
        ("Weapon reload karne se kya hota hai?", "ammo"),
        ("Safe zone mein rehne ka main faida kya hai?", "survival"),
        ("Gloo wall kis cheez se bachane mein madad karti hai?", "bullets"),
    ],
    3: [
        ("Free Fire ka famous victory shout kya hai?", "booyah"),
        ("HP ka matlab kya hai?", "health points"),
        ("Scope ka use kis liye hota hai?", "aim"),
        ("Revive ke baad teammate ko kis cheez ki zaroorat ho sakti hai?", "heal"),
        ("BR match mein jeetne ke liye aakhir tak kya rehna hota hai?", "alive"),
    ],
}
ANSWER_ALIASES = {
    "damage": {"damage", "health damage", "hp kam"},
    "revive": {"revive", "reviving", "uthana", "teammate ko uthana"},
    "br": {"br", "battle royale", "battleroyale"},
    "head": {"head", "headshot", "sir"},
    "cover": {"cover", "protection", "bachav"},
    "heal": {"heal", "healing", "health", "hp badhana", "health badhana"},
    "ping": {"ping", "mark", "location mark"},
    "ammo": {"ammo", "bullets", "goli"},
    "survival": {"survival", "safe rehna", "bachna"},
    "bullets": {"bullets", "goli", "enemy fire"},
    "booyah": {"booyah"},
    "health points": {"health points", "health point", "hp"},
    "aim": {"aim", "target", "nishana"},
    "alive": {"alive", "zinda", "last tak zinda"},
}


def _clean_answer(value):
    return re.sub(r"[^a-z0-9 ]", "", (value or "").lower()).strip()


def _eligible_players(room, round_number):
    members = list(room.memberships.select_related("user").order_by("joined_at"))
    for previous_round in range(1, round_number):
        correct_ids = set(PartyRoomGameAnswer.objects.filter(
            room=room, round_number=previous_round, is_correct=True
        ).values_list("player_id", flat=True))
        members = [m for m in members if m.user_id in correct_ids]
    return members


def start_party_game(room, round_number=1):
    if round_number == 1 and room.game_status == "finished":
        room.game_answers.all().delete()
        room.game_winner = None
        room.reward_awarded = False
    if room.game_status == "break" and "DRAW" in (room.game_result or "").upper():
        room.game_answers.filter(round_number=round_number).delete()
    room.game_round = round_number
    question, answer = random.choice(PARTY_QUIZ[round_number])
    old_questions = set(room.room_messages.filter(body__startswith="[QUIZ QUESTION]").values_list("body", flat=True))
    options = [pair for pair in PARTY_QUIZ[round_number] if "[QUIZ QUESTION] " + pair[0] not in old_questions]
    if options:
        question, answer = random.choice(options)
    room.game_question = question
    room.game_answer = answer
    room.game_status = "live"
    room.game_deadline = timezone.now() + timedelta(seconds=30)
    room.game_result = "Round " + str(round_number) + ": 30 seconds mein answer submit karo."
    room.save(update_fields=["game_round", "game_question", "game_answer", "game_status", "game_deadline", "game_result", "game_winner", "reward_awarded", "updated_at"])
    PartyRoomMessage.objects.create(room=room, sender=room.host, body="[QUIZ QUESTION] " + question)


def _award_quiz_winner(room, winner):
    with transaction.atomic():
        locked = PartyRoom.objects.select_for_update().get(pk=room.pk)
        if locked.game_status == "finished" or locked.reward_awarded:
            return
        wallet, _ = PlayerShopWallet.objects.get_or_create(user=winner)
        wallet = PlayerShopWallet.objects.select_for_update().get(pk=wallet.pk)
        wallet.fan_tokens += 5
        wallet.save(update_fields=["fan_tokens", "updated_at"])
        locked.game_winner = winner
        locked.reward_awarded = True
        locked.game_status = "finished"
        locked.game_deadline = None
        locked.game_result = winner.username + " jeet gaya! +5 Fan Tokens."
        locked.save(update_fields=["game_winner", "reward_awarded", "game_status", "game_deadline", "game_result", "updated_at"])


def advance_party_game(room):
    now = timezone.now()
    if room.game_status == "break" and room.game_deadline and now >= room.game_deadline:
        if room.game_round < 3:
            start_party_game(room, room.game_round + 1)
        else:
            start_party_game(room, 3)
        return
    if room.game_status != "live" or not room.game_deadline or now < room.game_deadline:
        return
    answers = list(room.game_answers.filter(round_number=room.game_round).select_related("player").order_by("answered_at", "pk"))
    correct = [item for item in answers if item.is_correct]
    if room.game_round == 3 and correct:
        _award_quiz_winner(room, correct[0].player)
        return
    eligible = _eligible_players(room, room.game_round)
    correct_ids = {item.player_id for item in correct}
    survivors = [member for member in eligible if member.user_id in correct_ids]
    if not survivors:
        room.game_status = "break"
        room.game_deadline = now + timedelta(seconds=5)
        room.game_result = "Round " + str(room.game_round) + " DRAW — sabke jawab galat ya time out. 5 sec baad naya sawaal."
        room.save(update_fields=["game_status", "game_deadline", "game_result", "updated_at"])
        if room.game_round < 3:
            # A draw retries the same round with a new question.
            room.game_round -= 1
            room.save(update_fields=["game_round", "updated_at"])
        return
    if room.game_round < 3:
        room.game_status = "break"
        room.game_deadline = now + timedelta(seconds=5)
        room.game_result = "Round " + str(room.game_round) + " complete — " + str(len(survivors)) + " player(s) advance. Wrong / unanswered players can watch."
        room.save(update_fields=["game_status", "game_deadline", "game_result", "updated_at"])
    else:
        room.game_status = "break"
        room.game_deadline = now + timedelta(seconds=5)
        room.game_result = "Final round draw — koi sahi jawab nahi. 5 sec baad naya final question."
        room.save(update_fields=["game_status", "game_deadline", "game_result", "updated_at"])


@login_required
@require_GET
def party_game_state(request, room_id):
    room = get_object_or_404(PartyRoom, pk=room_id)
    if not PartyRoomMembership.objects.filter(room=room, user=request.user).exists():
        return JsonResponse({"error": "Join this room first."}, status=403)
    advance_party_game(room)
    room.refresh_from_db()
    answers = room.game_answers.filter(round_number=room.game_round)
    eligible_ids = {m.user_id for m in _eligible_players(room, room.game_round)}
    own_answer = answers.filter(player=request.user).first()
    return JsonResponse({
        "status": room.game_status, "round": room.game_round, "question": room.game_question,
        "result": room.game_result, "deadline": room.game_deadline.isoformat() if room.game_deadline else None,
        "seconds_left": max(0, int((room.game_deadline - timezone.now()).total_seconds())) if room.game_deadline and room.game_status == "live" else 0,
        "answered": answers.count(), "members": room.memberships.count(),
        "eligible": request.user.pk in eligible_ids, "has_answered": bool(own_answer),
        "winner": room.game_winner.username if room.game_winner_id else None,
        "reward_awarded": room.reward_awarded,
        "can_start": request.user.pk == room.host_id and room.game_status in ("waiting", "finished"),
    })


@login_required
@require_POST
def party_game_answer(request, room_id):
    room = get_object_or_404(PartyRoom, pk=room_id)
    if not PartyRoomMembership.objects.filter(room=room, user=request.user).exists():
        return JsonResponse({"error": "Room membership required."}, status=403)
    advance_party_game(room)
    room.refresh_from_db()
    if room.game_status != "live" or not room.game_deadline or timezone.now() >= room.game_deadline:
        return JsonResponse({"error": "Answer time khatam ho gaya."}, status=400)
    if request.user.pk not in {m.user_id for m in _eligible_players(room, room.game_round)}:
        return JsonResponse({"error": "Aap spectator mode mein hain."}, status=403)
    answer = request.POST.get("answer", "").strip()[:240]
    if not answer:
        return JsonResponse({"error": "Jawab likho."}, status=400)
    normalized = _clean_answer(answer)
    expected = _clean_answer(room.game_answer)
    accepted = {_clean_answer(item) for item in ANSWER_ALIASES.get(expected, {expected})}
    is_correct = normalized == expected or normalized in accepted
    try:
        with transaction.atomic():
            PartyRoomGameAnswer.objects.create(room=room, round_number=room.game_round, player=request.user, answer=answer, is_correct=is_correct)
    except Exception:
        return JsonResponse({"error": "Is round mein aap ek jawab de chuke ho."}, status=409)
    if room.game_round == 3 and is_correct:
        _award_quiz_winner(room, request.user)
    return JsonResponse({"ok": True, "correct": is_correct, "message": "Sahi jawab!" if is_correct else "Galat jawab — aap ab spectator hain."})

@login_required
@require_POST
def party_quick_join(request):
    with transaction.atomic():
        rooms = PartyRoom.objects.select_for_update().filter(
            is_open=True, visibility=PartyRoom.Visibility.PUBLIC
        ).annotate(people=Count("memberships")).filter(people__lt=12).order_by("people", "-updated_at")
        room = rooms.first()
        if room is None:
            room = PartyRoom.objects.create(
                host=request.user, title="Quick Match Arena", description="Random public 12-player quiz room",
                theme="violet", visibility=PartyRoom.Visibility.PUBLIC, max_members=12
            )
        if not PartyRoomMembership.objects.filter(room=room, user=request.user).exists():
            if room.memberships.count() < 12 and room.game_status == "waiting":
                PartyRoomMembership.objects.create(room=room, user=request.user)
            elif room.memberships.count() < 12 and room.game_status != "waiting":
                PartyRoomMembership.objects.create(room=room, user=request.user)
        if room.game_status == "waiting" and room.memberships.count() >= 12:
            start_party_game(room)
    return redirect("chat:party_room", room_id=room.pk)
