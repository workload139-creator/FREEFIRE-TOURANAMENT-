from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from datetime import timedelta
from django.views.decorators.http import require_GET, require_POST

from apps.social.models import PlayerShopWallet
from .party_models import PartyRoom, PartyRoomMembership, PartyRoomMessage, PartyRoomGift, CommunityTournament, CommunityTournamentEntry
from .party_game import begin_quiz

GIFTS = {
    "rose": ("🌹", "Rose", 2),
    "tulip": ("🌷", "Tulip", 2),
    "sunflower": ("🌻", "Sunflower", 3),
    "hibiscus": ("🌺", "Hibiscus", 3),
    "cherry_blossom": ("🌸", "Cherry Blossom", 3),
    "bouquet": ("💐", "Flower Bouquet", 5),
    "red_heart": ("❤️", "Red Heart", 2),
    "sparkling_heart": ("💖", "Sparkling Heart", 5),
    "growing_heart": ("💗", "Growing Heart", 5),
    "heart_with_ribbon": ("💝", "Heart Gift", 8),
    "blue_heart": ("💙", "Blue Heart", 5),
    "purple_heart": ("💜", "Purple Heart", 5),
    "black_heart": ("🖤", "Black Heart", 5),
    "orange_heart": ("🧡", "Orange Heart", 5),
    "two_hearts": ("💕", "Two Hearts", 8),
    "heart_hands": ("🫶", "Heart Hands", 10),
    "kiss": ("💋", "Kiss", 10),
    "love_letter": ("💌", "Love Letter", 10),
    "teddy": ("🧸", "Teddy Bear", 20),
    "puppy": ("🐶", "Cute Puppy", 15),
    "kitten": ("🐱", "Cute Kitten", 15),
    "rabbit": ("🐰", "Rabbit", 15),
    "panda": ("🐼", "Panda", 20),
    "fox": ("🦊", "Fox", 20),
    "lion": ("🦁", "Lion", 25),
    "unicorn": ("🦄", "Unicorn", 30),
    "dragon": ("🐉", "Dragon", 40),
    "butterfly": ("🦋", "Butterfly", 10),
    "dolphin": ("🐬", "Dolphin", 20),
    "whale": ("🐳", "Whale", 25),
    "star": ("⭐", "Star", 2),
    "glowing_star": ("🌟", "Glowing Star", 5),
    "shooting_star": ("🌠", "Shooting Star", 10),
    "moon": ("🌙", "Moon", 5),
    "sun": ("☀️", "Sunshine", 5),
    "rainbow": ("🌈", "Rainbow", 10),
    "fire": ("🔥", "Fire", 10),
    "lightning": ("⚡", "Lightning", 10),
    "gem": ("💎", "Diamond Gem", 25),
    "crystal": ("🔮", "Magic Crystal", 30),
    "crown": ("👑", "Royal Crown", 50),
    "trophy": ("🏆", "Golden Trophy", 100),
    "medal": ("🏅", "Champion Medal", 40),
    "sports_medal": ("🥇", "Gold Medal", 50),
    "silver_medal": ("🥈", "Silver Medal", 30),
    "bronze_medal": ("🥉", "Bronze Medal", 20),
    "rocket": ("🚀", "Rocket", 50),
    "helicopter": ("🚁", "Helicopter", 60),
    "race_car": ("🏎️", "Racing Car", 60),
    "motorcycle": ("🏍️", "Super Bike", 50),
    "airplane": ("✈️", "Private Jet", 100),
    "ship": ("🚢", "Luxury Ship", 120),
    "castle": ("🏰", "Royal Castle", 150),
    "diamond_ring": ("💍", "Diamond Ring", 100),
    "watch": ("⌚", "Luxury Watch", 80),
    "handbag": ("👜", "Luxury Bag", 80),
    "crown_jewel": ("💠", "Crown Jewel", 120),
    "money_bag": ("💰", "Money Bag", 100),
    "gift_box": ("🎁", "Mystery Gift Box", 50),
    "party_popper": ("🎉", "Party Popper", 20),
    "confetti": ("🎊", "Confetti Blast", 20),
    "balloon": ("🎈", "Party Balloon", 5),
    "cake": ("🎂", "Birthday Cake", 20),
    "cupcake": ("🧁", "Cupcake", 10),
    "chocolate": ("🍫", "Chocolate", 10),
    "ice_cream": ("🍨", "Ice Cream", 10),
    "pizza": ("🍕", "Pizza Slice", 10),
    "burger": ("🍔", "Burger", 10),
    "coffee": ("☕", "Coffee", 5),
    "bubble_tea": ("🧋", "Bubble Tea", 10),
    "sunglasses": ("😎", "Cool Shades", 15),
    "smile": ("😁", "Big Smile", 5),
    "wink": ("😉", "Wink", 5),
    "laugh": ("😂", "Laugh Out Loud", 5),
    "cool_face": ("🤩", "Starstruck", 15),
    "clap": ("👏", "Clap", 5),
    "thumbs_up": ("👍", "Thumbs Up", 5),
    "muscle": ("💪", "Power", 10),
    "fireworks": ("🎆", "Fireworks", 30),
    "sparkles": ("✨", "Magic Sparkles", 10),
    "guitar": ("🎸", "Electric Guitar", 30),
    "headphones": ("🎧", "Headphones", 25),
    "music": ("🎵", "Music Note", 5),
    "microphone": ("🎤", "Golden Mic", 40),
    "drum": ("🥁", "Drum Set", 30),
    "gamepad": ("🎮", "Pro Gamepad", 40),
    "joystick": ("🕹️", "Arcade Joystick", 30),
    "controller": ("🎮", "Elite Controller", 60),
    "medkit": ("🧰", "Battle Kit", 25),
    "shield": ("🛡️", "Guardian Shield", 50),
    "sword": ("⚔️", "Twin Swords", 50),
    "helmet": ("🪖", "Battle Helmet", 30),
    "target": ("🎯", "Bullseye", 20),
    "flame_badge": ("🔱", "Legend Badge", 80),
    "phoenix": ("🐦‍🔥", "Phoenix", 150),
    "tiger": ("🐅", "Golden Tiger", 100),
    "eagle": ("🦅", "Royal Eagle", 100),
    "black_panther": ("🐈‍⬛", "Black Panther", 120),
    "supercar": ("🏁", "Champion Supercar", 200),
    "legendary_dragon": ("🐲", "Legendary Dragon", 250),
    "galaxy": ("🌌", "Galaxy", 300),
    "diamond_shower": ("💎", "Diamond Shower", 500),
    "royal_throne": ("🪑", "Royal Throne", 500),
    "golden_wings": ("🪽", "Golden Wings", 750),
    "mythic_crown": ("👑", "Mythic Crown", 1000),
}
CURRENCIES = {"diamonds": "diamonds", "coins": "coins", "fan_tokens": "fan_tokens"}


@login_required
def party_home(request):
    # Visiting the public room list is also an active host presence signal.
    # This prevents a host's room from being closed just because they navigated
    # out of the room page to browse or share the public room list.
    PartyRoomMembership.objects.filter(
        room__is_open=True, room__host=request.user, user=request.user
    ).update(last_seen_at=timezone.now())

    # Close only rooms whose host has genuinely stopped sending presence updates.
    stale_before = timezone.now() - timedelta(seconds=90)
    for stale_room in PartyRoom.objects.filter(is_open=True).only("pk", "host_id"):
        host_presence = PartyRoomMembership.objects.filter(
            room_id=stale_room.pk, user_id=stale_room.host_id
        ).only("last_seen_at").first()
        if not host_presence or host_presence.last_seen_at < stale_before:
            PartyRoom.objects.filter(pk=stale_room.pk, is_open=True).update(
                is_open=False, updated_at=timezone.now()
            )
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
    room = PartyRoom.objects.create(
        host=request.user,
        title=title,
        description=request.POST.get("description", "").strip()[:240],
        theme=request.POST.get("theme", "violet") if request.POST.get("theme") in ("violet", "gold", "ocean", "fire") else "violet",
        visibility=PartyRoom.Visibility.PUBLIC,
        passcode="",
        max_members=12,
    )
    PartyRoomMembership.objects.get_or_create(room=room, user=request.user)
    messages.success(request, "Room ban gaya! Aap seedha room ke andar aa gaye.")
    return redirect("chat:party_room", room_id=room.pk)


@login_required
def party_room(request, room_id):
    room = get_object_or_404(PartyRoom.objects.select_related("host"), pk=room_id)
    membership = PartyRoomMembership.objects.filter(room=room, user=request.user).first()
    if request.method == "POST":
        action = request.POST.get("action", "message")
        if action == "join":
            if not room.is_open:
                messages.error(request, "Room band hai.")
            elif room.visibility == PartyRoom.Visibility.PRIVATE and not membership:
                from django.core.cache import cache
                from django.utils.crypto import constant_time_compare
                from hashlib import sha256
                throttle_key = "party-room-passcode:" + sha256(f"{room.pk}:{request.user.pk}".encode()).hexdigest()
                attempts = cache.get(throttle_key, 0)
                if attempts >= 5:
                    messages.error(request, "Bahut attempts hue. 10 minute baad try karein.")
                    return redirect("chat:party_room", room_id=room.pk)
                submitted = request.POST.get("passcode", "").strip()
                if not room.passcode or not constant_time_compare(submitted, room.passcode):
                    cache.set(throttle_key, attempts + 1, 600)
                    messages.error(request, "Private room code galat hai.")
                    return redirect("chat:party_room", room_id=room.pk)
                cache.delete(throttle_key)
            if room.game_status != "lobby" and not membership:
                messages.error(request, "Game start ho chuka hai; ab naye players join nahi kar sakte.")
            elif room.memberships.count() >= 12 and not membership:
                messages.error(request, "Room full hai.")
            elif room.visibility == PartyRoom.Visibility.PRIVATE and not room.passcode and not membership:
                messages.error(request, "Host ne abhi private room code set nahi kiya hai.")
            else:
                PartyRoomMembership.objects.get_or_create(room=room, user=request.user)
                room.refresh_from_db()
                if room.auto_start and room.game_status == "lobby" and room.memberships.count() >= 12:
                    with transaction.atomic():
                        locked_room = PartyRoom.objects.select_for_update().get(pk=room.pk)
                        if locked_room.game_status == "lobby" and locked_room.memberships.count() >= 12:
                            begin_quiz(locked_room)
                messages.success(request, "Room join ho gaya.")
            return redirect("chat:party_room", room_id=room.pk)
        if action == "privacy":
            if request.user.pk != room.host_id or not membership:
                messages.error(request, "Sirf room host privacy change kar sakta hai.")
            else:
                visibility = request.POST.get("visibility", "public")
                passcode = request.POST.get("passcode", "").strip()
                if visibility not in ("public", "private"):
                    messages.error(request, "Privacy option valid nahi hai.")
                elif visibility == "private" and len(passcode) < 4:
                    messages.error(request, "Private room ke liye kam se kam 4 characters ka passcode rakho.")
                else:
                    room.visibility = visibility
                    room.passcode = passcode[:24] if visibility == "private" else ""
                    room.save(update_fields=["visibility", "passcode", "updated_at"])
                    messages.success(request, "Room privacy update ho gayi.")
            return redirect("chat:party_room", room_id=room.pk)
        if action == "toggle_auto_start":
            if request.user.pk != room.host_id or not membership:
                messages.error(request, "Auto-start setting sirf room host badal sakta hai.")
            elif room.game_status != "lobby":
                messages.error(request, "Game start hone ke baad auto-start setting nahi badal sakte.")
            else:
                room.auto_start = not room.auto_start
                room.save(update_fields=["auto_start", "updated_at"])
                messages.success(request, "Auto-start ON ho gaya: 12 players poore hote hi game start hoga." if room.auto_start else "Auto-start OFF ho gaya.")
            return redirect("chat:party_room", room_id=room.pk)
        if action == "start_game":
            is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
            is_admin = request.user.is_staff or request.user.is_superuser
            error = ""
            started = False
            player_count = 0
            if not is_admin and (request.user.pk != room.host_id or not membership):
                error = "Game sirf room host ya FF Arena admin start kar sakta hai."
            else:
                with transaction.atomic():
                    locked_room = PartyRoom.objects.select_for_update().get(pk=room.pk)
                    player_count = locked_room.memberships.count()
                    if locked_room.game_status != "lobby":
                        error = "Game pehle hi start ho chuka hai."
                    elif player_count < 1:
                        error = "Match start karne ke liye kam se kam 1 player room mein hona chahiye."
                    else:
                        started = begin_quiz(locked_room)
                        if not started:
                            error = "Match start nahi ho paya. Room mein kam se kam 1 player hona chahiye."
            if is_ajax:
                if error:
                    return JsonResponse({"ok": False, "error": error}, status=409)
                return JsonResponse({"ok": started, "phase": "question", "round": 1, "players": player_count})
            if error:
                messages.error(request, error)
            else:
                messages.success(request, f"Admin/Host ne match start kar diya! {player_count}/12 players ke saath Round 1 shuru.")
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
            if room.game_status == "live" and membership:
                if room.game_phase == "decision":
                    active_before = list(
                        PartyRoomMembership.objects.filter(room=room, is_eliminated=False)
                        .order_by("joined_at", "pk").values_list("pk", flat=True)
                    )
                    if membership.pk in active_before and active_before.index(membership.pk) < room.decision_index:
                        room.decision_index = max(0, room.decision_index - 1)
                        room.save(update_fields=["decision_index", "updated_at"])
                membership.is_eliminated = True
                membership.eliminated_round = room.current_round
                membership.elimination_reason = "left_game"
                membership.save(update_fields=["is_eliminated", "eliminated_round", "elimination_reason"])
                if request.user.pk == room.host_id:
                    room.is_open = False
                    room.save(update_fields=["is_open", "updated_at"])
                messages.info(request, "Game ke beech leave karne par aap spectator/eliminated mark ho gaye.")
            elif request.user.pk == room.host_id:
                room.is_open = False
                room.save(update_fields=["is_open", "updated_at"])
            else:
                PartyRoomMembership.objects.filter(room=room, user=request.user).delete()
            return redirect("chat:party")
        return redirect("chat:party_room", room_id=room.pk)
    if room.visibility == PartyRoom.Visibility.PRIVATE and not membership:
        # Do not expose member lists, chat history, or gifts to private-room visitors.
        members = []
        room_messages = []
    else:
        PartyRoomMembership.objects.filter(room=room, user=request.user).update(last_seen_at=timezone.now())
        members = room.memberships.select_related("user").order_by("joined_at")
        room_messages = room.room_messages.select_related("sender").order_by("-pk")[:100]
    return render(request, "chat/party_room.html", {"room": room, "members": members, "room_messages": list(reversed(room_messages)), "gifts": [{"code": code, "emoji": values[0], "name": values[1], "price": values[2]} for code, values in GIFTS.items()], "joined": bool(membership), "is_admin": request.user.is_staff or request.user.is_superuser})


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
    PartyRoomMembership.objects.filter(room=room, user=request.user).update(last_seen_at=timezone.now())
    items = PartyRoomMessage.objects.filter(room=room, pk__gt=after).select_related("sender").order_by("pk")[:100]
    members = list(PartyRoomMembership.objects.filter(room=room).select_related("user").order_by("joined_at"))
    return JsonResponse({
        "messages": [{"id": item.pk, "sender": item.sender.username, "body": item.body, "time": timezone.localtime(item.created_at).strftime("%H:%M"), "mine": item.sender_id == request.user.pk} for item in items],
        "members": [{"id": member.user_id, "username": member.user.username, "avatar_url": (member.user.profile_photo.url if member.user.profile_photo else ""), "is_host": member.user_id == room.host_id} for member in members],
        "member_count": len(members),
        "game_status": room.game_status,
    })


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
