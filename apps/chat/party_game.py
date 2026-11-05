from datetime import timedelta
from functools import wraps

from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from apps.social.models import PlayerShopWallet
from .party_models import PartyRoom, PartyRoomMembership, PartyRoomMessage


def json_login_required(view_func):
    """Return JSON for expired API sessions instead of redirecting to an HTML login page."""
    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({"error": "Login session expire ho gayi. Dobara login karein."}, status=401)
        return view_func(request, *args, **kwargs)
    return wrapped


import random

QUESTION_BANK = [
    {"text":"Free Fire mein sabse upar ka ranked tier kaunsa hai?","choices":{"A":"Grandmaster","B":"Gold","C":"Diamond","D":"Silver"},"correct":"A","explanation":"Grandmaster highest ranked tier hai."},
    {"text":"Gloo Wall ka main use kya hai?","choices":{"A":"HP restore karna","B":"Temporary cover banana","C":"Ammo reload karna","D":"Enemy ko revive karna"},"correct":"B","explanation":"Gloo Wall incoming fire se bachne ke liye cover deta hai."},
    {"text":"Teammate ko revive karne ke liye kya karna hota hai?","choices":{"A":"Grenade phenko","B":"Emote karo","C":"Uske paas jaakar revive action","D":"Match chhod do"},"correct":"C","explanation":"Down teammate ke paas jaakar revive action use hota hai."},
    {"text":"Booyah ka matlab kya hota hai?","choices":{"A":"Match jeetna","B":"Game restart","C":"Ammo khatam","D":"Drop location"},"correct":"A","explanation":"Booyah Battle Royale victory ko show karta hai."},
    {"text":"Med Kit ka use kis liye hota hai?","choices":{"A":"Armor badhana","B":"HP recover karna","C":"Ammo lena","D":"Vehicle repair"},"correct":"B","explanation":"Med Kit se health points recover hote hain."},
    {"text":"Free Fire mein parachute kab khulta hai?","choices":{"A":"Landing ke paas","B":"Lobby mein","C":"Victory ke baad","D":"Revive ke baad"},"correct":"A","explanation":"Drop ke dauran landing ke paas parachute deploy hota hai."},
    {"text":"Airdrop mein aam taur par kya milta hai?","choices":{"A":"High-tier loot","B":"Profile badge only","C":"Friend request","D":"Room code"},"correct":"A","explanation":"Airdrop mein valuable weapons aur equipment mil sakte hain."},
    {"text":"Helmet kis damage ko kam karne mein madad karta hai?","choices":{"A":"Headshot damage","B":"Fall damage","C":"Zone timer","D":"Reload time"},"correct":"A","explanation":"Helmet head damage se protection deta hai."},
    {"text":"Battle Royale mein safe zone se bahar rehne par kya hota hai?","choices":{"A":"HP damage hota hai","B":"Extra coins milte hain","C":"Weapon upgrade hota hai","D":"Auto revive"},"correct":"A","explanation":"Safe zone ke bahar player ko zone damage hota hai."},
    {"text":"Weapon attachment ka kaam kya hai?","choices":{"A":"Weapon performance improve karna","B":"Player rename karna","C":"Map change karna","D":"Room lock karna"},"correct":"A","explanation":"Attachments weapon ki handling ya performance improve karte hain."},
    {"text":"Squad mode mein aam taur par kitne players hote hain?","choices":{"A":"2","B":"3","C":"4","D":"6"},"correct":"C","explanation":"Standard squad team mein 4 players hote hain."},
    {"text":"Revive point ka use kis liye hota hai?","choices":{"A":"Teammate ko wapas match mein lana","B":"Weapon skin lena","C":"Map band karna","D":"Rank reset"},"correct":"A","explanation":"Revival system se eliminated teammate ko match mein wapas laya ja sakta hai."},
    {"text":"Free Fire mein character skill ka use kya hai?","choices":{"A":"Special ability dena","B":"Internet speed badhana","C":"Room capacity badhana","D":"Account password badalna"},"correct":"A","explanation":"Characters ki skills gameplay mein special abilities deti hain."},
    {"text":"Battle Royale mein match ki shuruaat kahan se hoti hai?","choices":{"A":"Plane se jump","B":"Shop screen","C":"Training result","D":"Friend list"},"correct":"A","explanation":"Players aircraft se map par drop karte hain."},
    {"text":"Weapon reload karne ka purpose kya hai?","choices":{"A":"Magazine mein ammo bharna","B":"HP restore karna","C":"Armor repair","D":"Map unlock"},"correct":"A","explanation":"Reload se weapon mein ammunition refill hoti hai."},
]
QUESTIONS = {index: question for index, question in enumerate(QUESTION_BANK, start=1)}

def _question_for_round(room):
    question_id = room.game_question_ids[room.current_round - 1] if len(room.game_question_ids) >= room.current_round else room.current_round
    return QUESTIONS.get(question_id, {})



def begin_quiz(room):
    """Start a new quiz run. Caller should hold a transaction and room row lock."""
    now = timezone.now()
    available_question_ids = [question_id for question_id in QUESTIONS if question_id not in set(room.game_question_ids or [])]
    if len(available_question_ids) < 3:
        available_question_ids = list(QUESTIONS.keys())
    question_ids = random.sample(available_question_ids, k=3)
    memberships = list(PartyRoomMembership.objects.select_for_update().filter(room=room).order_by("joined_at", "pk"))
    if not memberships:
        return False
    for member in memberships:
        member.is_eliminated = False
        member.eliminated_round = None
        member.elimination_reason = ""
        member.current_answer = ""
        member.answered_at = None
        member.score = 0
        member.decision_done = False
        member.save(update_fields=[
            "is_eliminated", "eliminated_round", "elimination_reason",
            "current_answer", "answered_at", "score", "decision_done",
        ])
    room.game_status = "live"
    room.game_phase = "question"
    room.current_round = 1
    room.game_question_ids = question_ids
    room.phase_deadline = now + timedelta(seconds=45)
    room.decision_index = 0
    room.winner = None
    room.game_winner_awarded = False
    room.save(update_fields=[
        "game_status", "game_phase", "current_round", "game_question_ids", "phase_deadline",
        "decision_index", "winner", "game_winner_awarded", "updated_at",
    ])
    PartyRoomMessage.objects.create(
        room=room, sender=room.host,
        body="🎮 GAME_STARTED|FF Arena Quiz Battle|Round 1 of 3|45 seconds to answer",
    )
    return True


def _finish_game(room):
    """Award a winner, or show a draw and automatically restart."""
    if room.game_phase in ("draw", "completed") or room.game_winner_awarded:
        return
    survivors = list(
        PartyRoomMembership.objects.select_for_update()
        .filter(room=room, is_eliminated=False)
        .select_related("user")
        .order_by("-score", "joined_at", "pk")
    )
    room.decision_index = 0
    if survivors:
        winner_member = survivors[0]
        room.game_status = "completed"
        room.game_phase = "completed"
        room.phase_deadline = None
        room.winner = winner_member.user
        wallet, _ = PlayerShopWallet.objects.get_or_create(user=winner_member.user)
        wallet = PlayerShopWallet.objects.select_for_update().get(pk=wallet.pk)
        wallet.fan_tokens += 5
        wallet.save(update_fields=["fan_tokens", "updated_at"])
        room.game_winner_awarded = True
        message = f"🏆 QUIZ_WINNER|{winner_member.user.username}|5 Fan Tokens awarded once"
    else:
        room.game_status = "live"
        room.game_phase = "draw"
        room.phase_deadline = timezone.now() + timedelta(seconds=30)
        room.winner = None
        room.game_winner_awarded = False
        message = "🤝 QUIZ_DRAW|Sabhi players eliminate ho gaye. 30 seconds mein naya game automatic restart hoga."
    room.save(update_fields=[
        "game_status", "game_phase", "phase_deadline", "decision_index",
        "winner", "game_winner_awarded", "updated_at",
    ])
    PartyRoomMessage.objects.create(room=room, sender=room.host, body=message)


def _start_decision_phase(room):
    active = list(
        PartyRoomMembership.objects.select_for_update()
        .filter(room=room, is_eliminated=False)
        .order_by("joined_at", "pk")
    )
    if not active:
        _finish_game(room)
        return
    for member in active:
        member.decision_done = False
        member.save(update_fields=["decision_done"])
    room.game_phase = "decision"
    room.decision_index = 0
    room.phase_deadline = timezone.now() + timedelta(seconds=15)
    room.save(update_fields=["game_phase", "decision_index", "phase_deadline", "updated_at"])
    PartyRoomMessage.objects.create(
        room=room, sender=room.host,
        body=f"🗣️ DECISION_PHASE|Round {room.current_round}|Har active player ko bolne ya Skip karne ke liye 15 seconds milenge.",
    )


def _advance_decision(room):
    active = list(
        PartyRoomMembership.objects.select_for_update()
        .filter(room=room, is_eliminated=False)
        .order_by("joined_at", "pk")
    )
    if not active:
        _finish_game(room)
        return
    for index, member in enumerate(active):
        if not member.decision_done:
            room.decision_index = index
            room.phase_deadline = timezone.now() + timedelta(seconds=15)
            room.save(update_fields=["decision_index", "phase_deadline", "updated_at"])
            return
    if room.current_round >= 3:
        _finish_game(room)
        return
    now = timezone.now()
    room.current_round += 1
    room.game_phase = "question"
    room.phase_deadline = now + timedelta(seconds=45)
    room.decision_index = 0
    for member in active:
        member.current_answer = ""
        member.answered_at = None
        member.decision_done = False
        member.save(update_fields=["current_answer", "answered_at", "decision_done"])
    room.save(update_fields=["current_round", "game_phase", "phase_deadline", "decision_index", "updated_at"])
    PartyRoomMessage.objects.create(
        room=room, sender=room.host,
        body=f"❓ ROUND_STARTED|Round {room.current_round} of 3|45 seconds to answer",
    )


def _advance_if_due(room):
    now = timezone.now()
    if room.game_phase == "draw" and room.phase_deadline and now >= room.phase_deadline:
        begin_quiz(room)
    elif room.game_phase == "question" and room.phase_deadline and now >= room.phase_deadline:
        active = list(
            PartyRoomMembership.objects.select_for_update()
            .filter(room=room, is_eliminated=False)
            .order_by("joined_at", "pk")
        )
        for member in active:
            if not member.current_answer:
                member.is_eliminated = True
                member.eliminated_round = room.current_round
                member.elimination_reason = "timeout"
                member.save(update_fields=["is_eliminated", "eliminated_round", "elimination_reason"])
                PartyRoomMessage.objects.create(
                    room=room, sender=room.host,
                    body=f"❌ PLAYER_ELIMINATED|{member.user.username}|Round {room.current_round}|Time ran out",
                )
        remaining_players = PartyRoomMembership.objects.filter(room=room, is_eliminated=False).count()
        if remaining_players == 1:
            _finish_game(room)
        elif remaining_players > 1:
            _start_decision_phase(room)
        else:
            _finish_game(room)
    elif room.game_phase == "decision" and room.phase_deadline and now >= room.phase_deadline:
        active = list(
            PartyRoomMembership.objects.select_for_update()
            .filter(room=room, is_eliminated=False)
            .order_by("joined_at", "pk")
        )
        if active and room.decision_index < len(active):
            current = active[room.decision_index]
            current.decision_done = True
            current.save(update_fields=["decision_done"])
            PartyRoomMessage.objects.create(
                room=room, sender=room.host,
                body=f"⏭️ DECISION_SKIPPED|{current.user.username}|15-second turn expired",
            )
        _advance_decision(room)


def _current_decision_member(room):
    active = list(
        PartyRoomMembership.objects.filter(room=room, is_eliminated=False)
        .select_related("user").order_by("joined_at", "pk")
    )
    if room.game_phase != "decision" or room.decision_index >= len(active):
        return None
    return active[room.decision_index]


@json_login_required
@require_GET
def party_game_state(request, room_id):
    with transaction.atomic():
        room = get_object_or_404(PartyRoom.objects.select_for_update().select_related("host"), pk=room_id)
        my_membership = PartyRoomMembership.objects.filter(room=room, user=request.user).first()
        if not my_membership:
            return JsonResponse({"error": "Join this room first."}, status=403)
        now = timezone.now()
        if request.user.pk != room.host_id:
            host_presence = PartyRoomMembership.objects.filter(
                room=room, user_id=room.host_id
            ).only("last_seen_at").first()
            if not host_presence or host_presence.last_seen_at < now - timedelta(seconds=90):
                room.is_open = False
                room.save(update_fields=["is_open", "updated_at"])
                return JsonResponse({"error": "Host offline hai. Yeh room close kar diya gaya hai."}, status=410)
        PartyRoomMembership.objects.filter(pk=my_membership.pk).update(last_seen_at=now)
        _advance_if_due(room)
        room.refresh_from_db()
        members = list(
            PartyRoomMembership.objects.filter(room=room).select_related("user")
            .order_by("joined_at", "pk")
        )
        my_member = next(member for member in members if member.user_id == request.user.pk)
        question = _question_for_round(room) if room.current_round else {}
        current_decision = _current_decision_member(room)
        remaining = None
        if room.phase_deadline:
            remaining = max(0, int((room.phase_deadline - timezone.now()).total_seconds() + 0.999))
        payload = {
            "phase": room.game_phase,
            "status": room.game_status,
            "round": room.current_round,
            "deadline": room.phase_deadline.isoformat() if room.phase_deadline else None,
            "seconds_left": remaining,
            "is_eliminated": my_member.is_eliminated,
            "elimination_reason": my_member.elimination_reason,
            "my_answer": my_member.current_answer,
            "score": my_member.score,
            "question": question.get("text") if room.game_phase == "question" and not my_member.is_eliminated and not my_member.current_answer else None,
            "choices": question.get("choices") if room.game_phase == "question" and not my_member.is_eliminated and not my_member.current_answer else None,
            "correct_answer": question.get("choices", {}).get(question.get("correct")) if room.game_phase in ("decision", "completed") else None,
            "explanation": question.get("explanation") if room.game_phase in ("decision", "completed") else None,
            "decision_player": current_decision.user.username if current_decision else None,
            "is_my_decision": bool(current_decision and current_decision.user_id == request.user.pk),
            "winner": room.winner.username if room.winner_id else None,
            "winner_awarded": room.game_winner_awarded,
            "leaderboard": [
                {
                    "username": member.user.username,
                    "score": member.score,
                    "eliminated": member.is_eliminated,
                    "eliminated_round": member.eliminated_round,
                    "reason": member.elimination_reason,
                    "winner": bool(room.winner_id and member.user_id == room.winner_id),
                }
                for member in sorted(members, key=lambda m: (m.is_eliminated, -m.score, m.joined_at, m.pk))
            ],
        }
    return JsonResponse(payload)


@json_login_required
@require_POST
def party_game_answer(request, room_id):
    answer = request.POST.get("answer", "").strip().upper()
    if answer not in ("A", "B", "C", "D", "SKIP"):
        return JsonResponse({"error": "Answer option valid nahi hai."}, status=400)
    with transaction.atomic():
        room = get_object_or_404(PartyRoom.objects.select_for_update().select_related("host"), pk=room_id)
        member = get_object_or_404(PartyRoomMembership.objects.select_for_update(), room=room, user=request.user)
        _advance_if_due(room)
        room.refresh_from_db()
        member.refresh_from_db()
        if room.game_phase != "question" or room.phase_deadline is None or timezone.now() >= room.phase_deadline:
            return JsonResponse({"error": "Answer timer khatam ho gaya ya question phase band hai."}, status=409)
        if member.is_eliminated:
            return JsonResponse({"error": "Aap eliminate ho chuke hain; spectator mode mein hain."}, status=403)
        if member.current_answer:
            return JsonResponse({"error": "Aapka answer pehle hi submit ho chuka hai."}, status=409)
        question = _question_for_round(room)
        if not question:
            return JsonResponse({"error": "Question available nahi hai."}, status=409)
        member.current_answer = answer
        member.answered_at = timezone.now()
        if answer == question["correct"]:
            member.score += 1
            outcome = f"✅ ANSWER_CORRECT|{request.user.username}|Round {room.current_round}"
        else:
            member.is_eliminated = True
            member.eliminated_round = room.current_round
            member.elimination_reason = "skip" if answer == "SKIP" else "wrong_answer"
            outcome = f"❌ PLAYER_ELIMINATED|{request.user.username}|Round {room.current_round}|{'Skipped' if answer == 'SKIP' else 'Wrong answer'}"
        member.save(update_fields=["current_answer", "answered_at", "score", "is_eliminated", "eliminated_round", "elimination_reason"])
        PartyRoomMessage.objects.create(room=room, sender=request.user, body=outcome)
        active = list(PartyRoomMembership.objects.filter(room=room, is_eliminated=False))
        if len(active) == 1:
            _finish_game(room)
        elif not active:
            _finish_game(room)
        elif all(player.current_answer for player in active):
            _start_decision_phase(room)
    return JsonResponse({"ok": True, "result": "correct" if answer == question["correct"] else "eliminated"})


@json_login_required
@require_POST
def party_game_decision(request, room_id):
    action = request.POST.get("action", "").strip().lower()
    if action not in ("done", "skip"):
        return JsonResponse({"error": "Decision action valid nahi hai."}, status=400)
    with transaction.atomic():
        room = get_object_or_404(PartyRoom.objects.select_for_update().select_related("host"), pk=room_id)
        member = get_object_or_404(PartyRoomMembership.objects.select_for_update(), room=room, user=request.user)
        _advance_if_due(room)
        room.refresh_from_db()
        member.refresh_from_db()
        current = _current_decision_member(room)
        if room.game_phase != "decision" or current is None or current.user_id != request.user.pk:
            return JsonResponse({"error": "Abhi aapki speaking turn nahi hai."}, status=409)
        if member.decision_done:
            return JsonResponse({"error": "Aapki turn already complete hai."}, status=409)
        member.decision_done = True
        member.save(update_fields=["decision_done"])
        PartyRoomMessage.objects.create(
            room=room, sender=request.user,
            body=f"{'🗣️ DECISION_DONE' if action == 'done' else '⏭️ DECISION_SKIPPED'}|{request.user.username}|Round {room.current_round}",
        )
        _advance_decision(room)
    return JsonResponse({"ok": True})


@json_login_required
@require_POST
def party_game_restart_draw(request, room_id):
    with transaction.atomic():
        room = get_object_or_404(PartyRoom.objects.select_for_update().select_related("host"), pk=room_id)
        if room.host_id != request.user.pk:
            return JsonResponse({"error": "Sirf host draw game restart kar sakta hai."}, status=403)
        if room.game_phase not in ("draw", "completed") or room.winner_id:
            return JsonResponse({"error": "Restart sirf draw match mein available hai."}, status=409)
        if not room.memberships.exists():
            return JsonResponse({"error": "Room mein koi player nahi hai."}, status=409)
        begin_quiz(room)
    return JsonResponse({"ok": True})
