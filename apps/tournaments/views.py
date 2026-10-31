from datetime import timedelta
import mimetypes
import os
from decimal import Decimal
import base64
import io

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db import IntegrityError, transaction
from django.http import FileResponse, Http404, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from urllib.parse import quote, urlencode
from django.views.decorators.http import require_POST

from apps.accounts.models import Wallet, WalletTransaction, AdminWallet, AdminWalletTransaction
from .forms import KillSubmissionForm, RegistrationForm
from .ai_review import AIReviewError, analyze_kill_evidence, fingerprint_evidence
from .registration_services import RegistrationError, create_pending_registration, assign_teams_for_tournament
from .constants import PLAYER_CONFIRMATION_TIMEOUT_SECONDS
from .models import KillSubmission, Registration, Tournament, TournamentLedgerEntry
from .kill_services import reward_for_tournament, rewards_for_tournament
from .services import process_expired_ready_registrations, mark_not_playing_and_refund
from .kill_safety import validate_match_dates, has_duplicate_match_id, get_match_id

import qrcode


def _credit_kill_submission_reward(submission, approved_kills, reward_override=None, source="Admin"):
    """Approve one submission and credit non-cash tournament currencies exactly once."""
    from apps.social.models import PlayerShopWallet

    # The registration row serializes every award for this player/tournament.
    registration = Registration.objects.select_for_update().get(pk=submission.registration_id)
    if submission.status == KillSubmission.Status.APPROVED:
        return []
    if KillSubmission.objects.filter(
        registration=registration, status=KillSubmission.Status.APPROVED
    ).exclude(pk=submission.pk).exists():
        raise ValueError("A reward has already been approved for this registration.")
    if has_duplicate_match_id(submission):
        raise ValueError("This Free Fire match ID has already been used for this UID in this tournament.")
    if not get_match_id(submission.ai_reviewer_reports) and "MATCH_ID_OVERRIDE:" not in (submission.admin_notes or ""):
        raise ValueError("A match ID was not readable/agreed by all reviewers. Admin must manually verify the original evidence and add MATCH_ID_OVERRIDE: with a reason.")
    date_ok, date_note = validate_match_dates(
        submission.ai_reviewer_reports, submission.tournament
    )
    if not date_ok and "DATE_OVERRIDE:" not in (submission.admin_notes or ""):
        raise ValueError(
            "Match date check failed. Admin must review the original evidence and add DATE_OVERRIDE: with a reason before a manual award. "
            + date_note
        )
    rewards = rewards_for_tournament(submission.tournament, approved_kills)
    if approved_kills < settings.MINIMUM_VERIFIED_KILLS:
        rewards = []
    if reward_override is not None:
        if not rewards:
            raise ValueError("Prize override is not allowed below the minimum verified kills.")
        currency, _quantity, label = rewards[0]
        rewards[0] = (currency, reward_override, label)

    primary_quantity = rewards[0][1] if rewards else 0
    coin_quantity = sum(quantity for currency, quantity, _label in rewards if currency == "coins")
    submission.approved_kills = approved_kills
    submission.proposed_reward = Decimal(primary_quantity)
    submission.approved_reward = Decimal(primary_quantity)
    submission.proposed_coins_reward = coin_quantity
    submission.approved_coins_reward = coin_quantity
    submission.status = KillSubmission.Status.APPROVED
    submission.reviewed_at = timezone.now()
    submission.save(update_fields=[
        "approved_kills", "proposed_reward", "approved_reward",
        "proposed_coins_reward", "approved_coins_reward",
        "status", "reviewed_at", "admin_notes",
    ])

    if not rewards:
        return []

    wallet, _ = PlayerShopWallet.objects.get_or_create(user=submission.player)
    wallet = PlayerShopWallet.objects.select_for_update().get(pk=wallet.pk)
    credited = []
    for currency, quantity, label in rewards:
        if quantity <= 0:
            continue
        reference = f"KILL-REWARD-{submission.pk}-{currency}"
        if TournamentLedgerEntry.objects.filter(reference=reference).exists():
            continue
        wallet_field = {
            "diamonds": "diamonds",
            "coins": "coins",
            "fan_tokens": "fan_tokens",
        }[currency]
        setattr(wallet, wallet_field, getattr(wallet, wallet_field) + int(quantity))
        TournamentLedgerEntry.objects.create(
            reference=reference,
            tournament=submission.tournament,
            player=submission.player,
            registration=submission.registration,
            entry_type=TournamentLedgerEntry.EntryType.REWARD,
            currency=currency,
            quantity=int(quantity),
            amount_inr=Decimal("0.00"),
            status=TournamentLedgerEntry.Status.COMPLETED,
            description=f"{source}: {int(quantity)} {label} for {approved_kills} verified kills",
        )
        credited.append((int(quantity), label))
    if credited:
        wallet.save(update_fields=("diamonds", "coins", "fan_tokens", "updated_at"))
    return credited


def cleanup_expired_kill_evidence():
    """Retain all pending evidence; only clean reviewed evidence after a 90-day audit window."""
    cutoff = timezone.now() - timedelta(days=90)
    expired = KillSubmission.objects.filter(
        status__in=[KillSubmission.Status.APPROVED, KillSubmission.Status.REJECTED],
        reviewed_at__isnull=False,
        reviewed_at__lte=cutoff,
    ).only("id", "history_video", "history_image_one", "history_image_two")
    for submission in expired.iterator():
        changed = []
        for field_name in ("history_video", "history_image_one", "history_image_two"):
            field_file = getattr(submission, field_name)
            if field_file and field_file.name:
                try:
                    field_file.delete(save=False)
                except (OSError, ValueError):
                    pass
                setattr(submission, field_name, "")
                changed.append(field_name)
        if changed:
            submission.save(update_fields=changed)


def tournament_list(request):
    cleanup_expired_kill_evidence()
    process_expired_ready_registrations()
    tournaments = Tournament.objects.filter(
        status__in=[Tournament.Status.UPCOMING, Tournament.Status.LIVE, Tournament.Status.COMPLETED]
    ).order_by("start_time")
    return render(
        request,
        "tournaments/list.html",
        {
            "tournaments": tournaments,
            "free_fan_tournaments": tournaments.filter(is_free_fan_tournament=True),
            "br_tournaments": tournaments.filter(mode=Tournament.Mode.BR, is_free_fan_tournament=False, is_diwali_offer=False, is_unlimited_br=False).exclude(gender_category=Tournament.GenderCategory.GIRLS_VS_BOYS),
            "vs_tournaments": tournaments.filter(mode=Tournament.Mode.VS).exclude(gender_category=Tournament.GenderCategory.GIRLS_VS_BOYS),
            "unlimited_tournaments": tournaments.filter(is_unlimited_br=True, is_diwali_offer=False),
            "diwali_tournaments": tournaments.filter(is_diwali_offer=True, mode=Tournament.Mode.BR, br_format=Tournament.BRFormat.SOLO),
            "girls_vs_boys_tournaments": tournaments.filter(gender_category=Tournament.GenderCategory.GIRLS_VS_BOYS),
        },
    )



def battle_royale_list(request):
    process_expired_ready_registrations()
    tournaments = Tournament.objects.filter(mode=Tournament.Mode.BR, is_free_fan_tournament=False, gender_category__in=[Tournament.GenderCategory.OPEN, Tournament.GenderCategory.BOYS, Tournament.GenderCategory.GIRLS], status__in=[Tournament.Status.UPCOMING, Tournament.Status.LIVE, Tournament.Status.COMPLETED]).order_by('br_format', '-created_at')
    return render(request, 'tournaments/battle_royale_list.html', {'tournaments': tournaments})


def clash_squad_list(request):
    process_expired_ready_registrations()
    tournaments = Tournament.objects.filter(mode=Tournament.Mode.VS, gender_category__in=[Tournament.GenderCategory.OPEN, Tournament.GenderCategory.BOYS, Tournament.GenderCategory.GIRLS], status__in=[Tournament.Status.UPCOMING, Tournament.Status.LIVE, Tournament.Status.COMPLETED]).order_by('vs_format', 'start_time')
    return render(request, 'tournaments/clash_squad_list.html', {'tournaments': tournaments})

def unlimited_tournament_list(request):
    """Dedicated page for recurring Unlimited BR tournaments."""
    process_expired_ready_registrations()
    tournaments = Tournament.objects.filter(
        mode=Tournament.Mode.BR,
        is_unlimited_br=True,
        is_diwali_offer=False,
        is_free_fan_tournament=False,
        gender_category__in=[
            Tournament.GenderCategory.OPEN,
            Tournament.GenderCategory.BOYS,
            Tournament.GenderCategory.GIRLS,
        ],
        status__in=[
            Tournament.Status.UPCOMING,
            Tournament.Status.LIVE,
            Tournament.Status.COMPLETED,
        ],
    ).order_by("br_format", "-created_at")
    return render(request, "tournaments/unlimited_list.html", {"tournaments": tournaments})


def free_fan_tournament_list(request):
    """Dedicated page for the date-free, recurring free 49-player fan arena."""
    process_expired_ready_registrations()
    rounds = Tournament.objects.filter(
        is_free_fan_tournament=True,
        status__in=[Tournament.Status.UPCOMING, Tournament.Status.LIVE],
    ).order_by("status", "created_at")
    recent_entry = False
    if request.user.is_authenticated:
        recent_entry = Registration.objects.filter(
            player=request.user,
            tournament__is_free_fan_tournament=True,
            registered_at__gte=timezone.now() - timedelta(hours=24),
        ).exclude(status__in=[Registration.Status.CANCELLED, Registration.Status.REFUNDED]).exists()
    return render(request, "tournaments/free_fan_list.html", {
        "tournaments": rounds.exclude(gender_category=Tournament.GenderCategory.GIRLS_VS_BOYS),
        "recent_entry": recent_entry,
    })


def tournament_detail(request, tournament_id):
    tournament = get_object_or_404(Tournament, pk=tournament_id)
    return render(request, "tournaments/tournament_detail.html", {"tournament": tournament, "diamonds_per_kill": int(settings.DIAMONDS_PER_APPROVED_KILL), "minimum_verified_kills": int(settings.MINIMUM_VERIFIED_KILLS)})


def build_entry_payment_uri(tournament):
    """Build a UPI deep link only when the configured receiving UPI ID exists."""
    if getattr(tournament, "is_diwali_offer", False):
        return ""  # Diwali offer accepts exactly one Diamond, never UPI/INR.
    if tournament.entry_fee <= Decimal("0.00"):
        return ""
    upi_id = os.getenv("FF_ARENA_UPI_ID", "").strip()
    if not upi_id or "@" not in upi_id or any(char.isspace() for char in upi_id):
        return ""
    query = urlencode({"pa": upi_id, "pn": os.getenv("FF_ARENA_UPI_NAME", "FF Arena").strip() or "FF Arena", "am": f"{tournament.entry_fee:.2f}", "cu": "INR", "tn": f"FFArena-{tournament.pk}"})
    return f"upi://pay?{query}"


def build_entry_qr_url(tournament):
    """Create QR locally, avoiding external QR API and cross-origin download failures."""
    uri = build_entry_payment_uri(tournament)
    if not uri:
        return ""
    image = qrcode.make(uri)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")

@login_required
def tournament_register(request, tournament_id):
    process_expired_ready_registrations()
    tournament = get_object_or_404(Tournament, pk=tournament_id)
    if tournament.is_free_fan_tournament:
        recent_free_entry = Registration.objects.filter(
            player=request.user, tournament__is_free_fan_tournament=True,
            registered_at__gte=timezone.now() - timedelta(hours=24),
        ).exclude(status__in=[Registration.Status.CANCELLED, Registration.Status.REFUNDED]).exists()
        if recent_free_entry and not Registration.objects.filter(tournament=tournament, player=request.user).exists():
            messages.error(request, "Free tournament mein 24 ghante mein sirf ek entry allowed hai.")
            return redirect("tournaments:free_fan_list")
    if tournament.gender_category == Tournament.GenderCategory.BOYS and request.user.gender != "boy":
        messages.error(request, "Yeh Boys Only tournament hai. Profile mein Boy category select karne wale players hi join kar sakte hain.")
        return redirect("tournaments:detail", tournament_id=tournament.pk)
    if tournament.gender_category == Tournament.GenderCategory.GIRLS and request.user.gender != "girl":
        messages.error(request, "Yeh Girls Only tournament hai. Profile mein Girl category select karne wale players hi join kar sakte hain.")
        return redirect("tournaments:detail", tournament_id=tournament.pk)
    if request.method == "GET":
        time_closed = tournament.start_time <= timezone.now() and not tournament.is_unlimited_br
        if tournament.status != Tournament.Status.UPCOMING or time_closed or tournament.is_full:
            messages.error(request, "Yeh tournament abhi registration ke liye available nahi hai.")
            return redirect("tournaments:list")
        if Registration.objects.filter(tournament=tournament, player=request.user).exists():
            messages.info(request, "Aap is tournament mein pehle se registered hain.")
            return redirect("tournaments:detail", tournament_id=tournament.pk)
        from apps.social.models import PlayerShopWallet
        shop_wallet, _ = PlayerShopWallet.objects.get_or_create(user=request.user)
        return render(request, "tournaments/register.html", {"tournament": tournament, "form": RegistrationForm(user=request.user, tournament=tournament), "upi_payment_uri": build_entry_payment_uri(tournament), "qr_image_url": build_entry_qr_url(tournament), "shop_wallet": shop_wallet})

    if request.method != "POST":
        return redirect("tournaments:list")

    form = RegistrationForm(request.POST, request.FILES, user=request.user, tournament=tournament)
    payment_method = request.POST.get("payment_method", "upi")
    if payment_method == "upi" and tournament.entry_fee > Decimal("0.00") and not build_entry_payment_uri(tournament):
        messages.error(request, "UPI payment abhi configured nahi hai. Diamonds ya Coins available hon to unse register karein.")
        return redirect("tournaments:detail", tournament_id=tournament.pk)
    if not form.is_valid():
        from apps.social.models import PlayerShopWallet
        shop_wallet, _ = PlayerShopWallet.objects.get_or_create(user=request.user)
        return render(request, "tournaments/register.html", {"tournament": tournament, "form": form, "upi_payment_uri": build_entry_payment_uri(tournament), "qr_image_url": build_entry_qr_url(tournament), "shop_wallet": shop_wallet})

    try:
        registration = create_pending_registration(
            tournament_id=tournament_id,
            player=request.user,
            free_fire_uid=form.cleaned_data["free_fire_uid"],
            payment_reference=form.cleaned_data.get("payment_reference", ""),
            payment_method=form.cleaned_data.get("payment_method", "upi"),
        )
    except RegistrationError as exc:
        if str(exc) in ("NO_COINS", "NO_DIAMONDS", "NO_FAN_TOKENS"):
            label = {"NO_COINS": "Coins", "NO_DIAMONDS": "Diamonds", "NO_FAN_TOKENS": "Fan Tokens"}[str(exc)]
            messages.warning(request, f"No {label} / not enough {label}. Shop ya follower milestones se {label} hasil karein, phir tournament join karein.")
            return redirect("social:shop")
        form.add_error(None, str(exc))
        from apps.social.models import PlayerShopWallet
        shop_wallet, _ = PlayerShopWallet.objects.get_or_create(user=request.user)
        return render(
            request,
            "tournaments/register.html",
            {"tournament": tournament, "form": form, "upi_payment_uri": build_entry_payment_uri(tournament), "qr_image_url": build_entry_qr_url(tournament), "shop_wallet": shop_wallet},
        )
    except IntegrityError:
        form.add_error(None, "Registration nahi ho saki; aap pehle se registered ho sakte hain.")
        return render(
            request,
            "tournaments/register.html",
            {"tournament": tournament, "form": form, "upi_payment_uri": build_entry_payment_uri(tournament), "qr_image_url": build_entry_qr_url(tournament)},
        )

    if form.cleaned_data.get("verification_photo"):
        registration.verification_photo = form.cleaned_data["verification_photo"]
        registration.save(update_fields=["verification_photo"])

    if registration.payment_method in ("diamonds", "coins", "fan_tokens"):
        messages.success(request, f"Tournament registration confirmed. {registration.currency_amount} {registration.get_payment_method_display()} use hue.")
    elif tournament.entry_fee > Decimal("0.00"):
        messages.info(request, "Payment UTR submit ho gaya. Registration tabhi confirm hogi jab admin aapki payment apne UPI/bank statement se verify karega.")
    else:
        messages.success(request, "Free tournament registration confirm ho gayi.")
    return redirect("tournaments:my_registrations")


@login_required
@require_POST
def confirm_playing(request, registration_id):
    process_expired_ready_registrations()
    with transaction.atomic():
        registration = get_object_or_404(
            Registration.objects.select_for_update().select_related("tournament"),
            pk=registration_id,
            player=request.user,
        )
        if registration.status != Registration.Status.WAITING_READY or not registration.payment_verified:
            messages.error(request, "Is registration ki confirmation available nahi hai ya deadline khatam ho chuki hai.")
            return redirect("tournaments:player_room", registration_id=registration.pk)
        if not registration.room_details_sent or not registration.tournament.room_id:
            messages.error(request, "Room details abhi available nahi hain.")
            return redirect("tournaments:list")
        if not registration.ready_deadline or timezone.now() >= registration.ready_deadline:
            messages.error(request, "Confirmation ke 5 minute khatam ho gaye. Admin se contact karein.")
            return redirect("tournaments:player_room", registration_id=registration.pk)

        registration.status = Registration.Status.READY
        registration.ready_confirmed_at = timezone.now()
        registration.save(update_fields=["status", "ready_confirmed_at", "updated_at"])

    messages.success(request, "Participation confirm ho gayi!")
    return redirect("tournaments:player_room", registration_id=registration_id)


@login_required
@require_POST
def decline_playing(request, registration_id):
    process_expired_ready_registrations()
    registration = get_object_or_404(Registration, pk=registration_id, player=request.user)
    if registration.status != Registration.Status.WAITING_READY:
        messages.error(request, "Is registration ke liye NO option ab available nahi hai.")
        return redirect("tournaments:my_registrations")
    registration.ready_deadline = timezone.now()
    registration.save(update_fields=["ready_deadline", "updated_at"])
    changed, detail = mark_not_playing_and_refund(registration.pk)
    if changed:
        messages.warning(request, "Aap NOT PLAYING mark ho gaye. Refund original in-app wallet currency mein credit hua hai; wallet history check karein.")
    else:
        messages.error(request, "Status update nahi ho saka: " + detail)
    return redirect("tournaments:my_registrations")


@login_required
@user_passes_test(lambda user: user.is_staff)
@require_POST
def send_room_details(request, tournament_id):
    room_id = request.POST.get("room_id", "").strip()
    room_password = request.POST.get("room_password", "").strip()
    room_qr_code = request.FILES.get("room_qr_code")
    if not room_id or not room_password:
        messages.error(request, "Room ID aur password dono bharo.")
        return redirect("tournaments:admin_room_page", tournament_id=tournament_id)

    with transaction.atomic():
        tournament = get_object_or_404(Tournament.objects.select_for_update(), pk=tournament_id)
        if tournament.status != Tournament.Status.LIVE:
            messages.error(request, "Room details sirf tournament LIVE hone ke baad release ki ja sakti hain.")
            return redirect("tournaments:admin_room_page", tournament_id=tournament_id)

        try:
            assigned_count, team_size = assign_teams_for_tournament(tournament.pk)
        except ValueError as exc:
            messages.error(request, str(exc))
            return redirect("tournaments:admin_room_page", tournament_id=tournament_id)

        tournament.room_id = room_id
        tournament.room_password = room_password
        update_fields = ["room_id", "room_password", "updated_at"]
        if room_qr_code:
            if getattr(room_qr_code, "content_type", "") not in ("image/jpeg", "image/png", "image/webp"):
                messages.error(request, "Room QR ke liye JPG, PNG ya WebP image upload karein.")
                return redirect("tournaments:admin_room_page", tournament_id=tournament_id)
            if room_qr_code.size > 5 * 1024 * 1024:
                messages.error(request, "Room QR image 5 MB se chhoti honi chahiye.")
                return redirect("tournaments:admin_room_page", tournament_id=tournament_id)
            tournament.room_qr_code = room_qr_code
            update_fields.append("room_qr_code")
        tournament.save(update_fields=update_fields)

        now = timezone.now()
        eligible = Registration.objects.select_for_update().filter(
            tournament=tournament,
            status=Registration.Status.CONFIRMED,
            payment_verified=True,
        )
        eligible.update(
            status=Registration.Status.WAITING_READY,
            room_details_sent=True,
            ready_deadline=now + timedelta(seconds=PLAYER_CONFIRMATION_TIMEOUT_SECONDS),
            ready_confirmed_at=None,
        )

    messages.success(request, f"Room details set ho gayi. {assigned_count} verified players ko {team_size}-player teams mein assign kiya. Eligible players ko 5 minute ke andar YES confirm karna hoga.")
    return redirect("tournaments:admin_room_page", tournament_id=tournament_id)


@login_required
@user_passes_test(lambda user: user.is_staff)
def admin_room_page(request, tournament_id):
    tournament = get_object_or_404(Tournament, pk=tournament_id)
    return render(request, "tournaments/admin_room.html", {"tournament": tournament})


@login_required
def player_room(request, registration_id):
    process_expired_ready_registrations()
    registration = get_object_or_404(
        Registration.objects.select_related("tournament"),
        pk=registration_id,
        player=request.user,
    )
    can_view_room = (
        registration.payment_verified
        and registration.room_details_sent
        and registration.status == Registration.Status.READY
        and bool(registration.tournament.room_id)
        and (registration.status == Registration.Status.READY or (
            registration.ready_deadline and timezone.now() < registration.ready_deadline
        ))
    )
    return render(request, "tournaments/player_room.html", {
        "registration": registration,
        "tournament": registration.tournament,
        "can_view_room": can_view_room,
    })


@login_required
def room_qr_file(request, tournament_id):
    """Stream the room QR only to staff or a paid player cleared for this room."""
    tournament = get_object_or_404(Tournament, pk=tournament_id)
    if not request.user.is_staff:
        allowed = Registration.objects.filter(
            tournament=tournament,
            player=request.user,
            payment_verified=True,
            room_details_sent=True,
            status=Registration.Status.READY,
        ).exists()
        if not allowed:
            return HttpResponseForbidden("Room QR access is available only to confirmed players.")

    if not tournament.room_qr_code:
        raise Http404("Room QR is not available.")

    try:
        file_handle = tournament.room_qr_code.open("rb")
    except (FileNotFoundError, OSError, ValueError):
        raise Http404("Room QR file is unavailable.")

    content_type = mimetypes.guess_type(tournament.room_qr_code.name)[0] or "application/octet-stream"
    response = FileResponse(file_handle, content_type=content_type)
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response


@login_required
@user_passes_test(lambda user: user.is_staff)
def admin_tournament_dashboard(request, tournament_id):
    process_expired_ready_registrations()
    tournament = get_object_or_404(Tournament, pk=tournament_id)
    registrations = Registration.objects.filter(tournament=tournament).select_related("player").order_by("-registered_at")
    kill_submissions = KillSubmission.objects.filter(
        tournament=tournament
    ).select_related("player", "registration").order_by("-submitted_at")
    from apps.social.models import PlayerShopWallet
    from apps.accounts.models import Wallet
    player_ids = list(registrations.values_list("player_id", flat=True).distinct())
    shop_wallets = {
        wallet.user_id: wallet
        for wallet in PlayerShopWallet.objects.filter(user_id__in=player_ids)
    }
    inr_wallets = {
        wallet.user_id: wallet
        for wallet in Wallet.objects.filter(user_id__in=player_ids)
    }
    for registration in registrations:
        registration.shop_wallet = shop_wallets.get(registration.player_id)
        registration.inr_wallet = inr_wallets.get(registration.player_id)
    tournament_history = TournamentLedgerEntry.objects.filter(
        tournament=tournament
    ).select_related("player", "registration").order_by("-created_at")
    from django.db.models import Q
    refund_history = registrations.filter(
        Q(refund_processed=True) | Q(status__in=[Registration.Status.CANCELLED, Registration.Status.NOT_PLAYING])
    ).select_related("player").order_by("-refund_processed_at", "-registered_at")
    context = {
        "tournament": tournament,
        "registrations": registrations,
        "kill_submissions": kill_submissions,
        "tournament_history": tournament_history,
        "pending_payments": registrations.filter(payment_verified=False, entry_fee_paid__gt=0),
        "refund_queue": registrations.filter(
            payment_verified=True,
            entry_fee_paid__gt=0,
            refund_processed=False,
            status__in=[Registration.Status.CANCELLED, Registration.Status.NOT_PLAYING],
        ).select_related("player"),
        "refund_history": refund_history,
        "total_players": registrations.count(),
        "verified_payments": registrations.filter(payment_verified=True).count(),
        "waiting_players": registrations.filter(status=Registration.Status.WAITING_READY).count(),
        "ready_players": registrations.filter(status=Registration.Status.READY).count(),
        "not_playing_players": registrations.filter(status=Registration.Status.NOT_PLAYING).count(),
        "refunded_players": registrations.filter(refund_processed=True).count(),
    }
    return render(request, "tournaments/admin_dashboard.html", context)



@login_required
def my_registrations(request):
    cleanup_expired_kill_evidence()
    process_expired_ready_registrations()
    registrations = Registration.objects.filter(player=request.user).exclude(
        status=Registration.Status.REFUNDED
    ).exclude(refund_processed=True).select_related("tournament")
    from apps.accounts.models import WalletTransaction
    from apps.social.models import PlayerShopWallet
    from django.db.models import Q
    wallet_transactions = WalletTransaction.objects.filter(wallet__user=request.user).order_by("-created_at")[:50]
    tournament_transactions = TournamentLedgerEntry.objects.filter(player=request.user).select_related("tournament").order_by("-created_at")[:100]
    shop_wallet, _ = PlayerShopWallet.objects.get_or_create(user=request.user)
    return render(request, "tournaments/my_registrations.html", {
        "registrations": registrations,
        "wallet_transactions": wallet_transactions,
        "tournament_transactions": tournament_transactions,
        "shop_wallet": shop_wallet,
    })


@login_required
def kill_submission(request, registration_id):
    registration = get_object_or_404(
        Registration.objects.select_related("tournament", "player"),
        pk=registration_id,
        player=request.user,
    )
    if not registration.payment_verified or registration.status != Registration.Status.READY:
        messages.error(request, "Kill evidence submit karne ke liye verified registration zaroori hai.")
        return redirect("tournaments:my_registrations")

    if KillSubmission.objects.filter(registration=registration).exists():
        messages.info(request, "Is registration ki evidence submission pehle hi maujood hai.")
        return redirect("tournaments:my_registrations")

    if request.method == "POST":
        form = KillSubmissionForm(request.POST, request.FILES)
        if form.is_valid():
            submitted_uid = form.cleaned_data["free_fire_uid"]
            if submitted_uid != registration.free_fire_uid:
                form.add_error("free_fire_uid", "UID registration wali UID se match nahi karti.")
            else:
                # Lock the registration while creating evidence so two simultaneous
                # POSTs cannot create two submissions for the same paid entry.
                with transaction.atomic():
                    locked_registration = Registration.objects.select_for_update().get(
                        pk=registration.pk, player=request.user
                    )
                    if KillSubmission.objects.filter(registration=locked_registration).exists():
                        messages.info(request, "Is registration ki evidence submission pehle hi maujood hai.")
                        return redirect("tournaments:my_registrations")
                    submission = form.save(commit=False)
                    submission.registration = locked_registration
                    submission.player = request.user
                    submission.tournament = locked_registration.tournament
                    submission.registered_uid = locked_registration.free_fire_uid
                    submission.proposed_reward = Decimal("0.00")
                    submission.save()
                try:
                    submission.evidence_sha256 = fingerprint_evidence(submission)
                    submission.save(update_fields=["evidence_sha256"])
                    ai_result = analyze_kill_evidence(submission)
                    submission.ai_proposed_kills = ai_result["proposed_kills"]
                    submission.ai_confidence = ai_result["confidence"][:10]
                    submission.ai_uid_matches = ai_result["uid_matches"]
                    submission.ai_review_notes = ai_result["reason"]
                    submission.ai_reviewer_reports = ai_result.get("reviewer_reports", {})
                    proposed_kills = ai_result["proposed_kills"]
                    uid_ok = (
                        ai_result.get("uid_matches") is True
                        and submitted_uid == registration.free_fire_uid
                        and registration.free_fire_uid == submission.registered_uid
                        and str(getattr(registration.player, "free_fire_uid", "") or "").strip() == registration.free_fire_uid
                    )
                    proposed_kills = int(proposed_kills or 0)
                    match_date_ok, match_date_note = validate_match_dates(
                        ai_result.get("reviewer_reports", {}), registration.tournament
                    )
                    duplicate_match = has_duplicate_match_id(submission)
                    match_id_ok = bool(get_match_id(ai_result.get("reviewer_reports", {})))
                    submission.ai_review_notes = (
                        (submission.ai_review_notes or "") + "\nDATE CHECK: " + match_date_note
                        + ("\nDUPLICATE MATCH ID: blocked." if duplicate_match else "")
                        + ("\nMATCH ID: missing or reviewers disagreed." if not match_id_ok else "")
                    )[:6000]
                    if uid_ok and match_date_ok and match_id_ok and not duplicate_match and ai_result.get("proposed_kills") is not None and proposed_kills >= settings.MINIMUM_VERIFIED_KILLS:
                        _currency, proposed_quantity, _label = reward_for_tournament(registration.tournament, proposed_kills)
                        submission.proposed_reward = Decimal(proposed_quantity)
                    else:
                        submission.proposed_reward = Decimal("0.00")
                    submission.ai_proposed_kills = ai_result["proposed_kills"]
                    submission.ai_confidence = ai_result["confidence"][:10]
                    submission.ai_uid_matches = ai_result["uid_matches"]
                    submission.ai_review_notes = (
                        (ai_result.get("reason") or "") + "\nDATE CHECK: " + match_date_note
                        + ("\nDUPLICATE MATCH ID: blocked." if duplicate_match else "")
                        + ("\nMATCH ID: missing or reviewers disagreed." if not match_id_ok else "")
                    )[:6000]
                    submission.save(update_fields=[
                        "ai_proposed_kills", "ai_confidence", "ai_uid_matches",
                        "ai_review_notes", "proposed_reward", "ai_reviewer_reports",
                    ])
                    if ai_result.get("four_way_agreement") is True and uid_ok and match_date_ok and match_id_ok and not duplicate_match:
                        messages.success(request, f"Four AI reviewers agreed: {proposed_kills} kills reported. Reward/payment is not handled by Kill Verification; submission is waiting for Admin Review.")
                    else:
                        messages.info(request, "AI kill report saved. Any reviewer failure, disagreement, UID/date/match issue or unclear evidence remains in Admin Review.")
                except Exception as exc:
                    # Keep a durable assessment record even when an AI provider,
                    # network, video decoder, or model response fails. Never pay
                    # from a fallback/guessed kill count.
                    submission.ai_proposed_kills = None
                    submission.ai_confidence = "low"
                    submission.ai_uid_matches = None
                    submission.proposed_reward = Decimal("0.00")
                    submission.ai_reviewer_reports = ai_result.get("reviewer_reports", {}) if "ai_result" in locals() else {
                        key: {"name": label, "status": "BLOCKED", "proposed_kills": None, "confidence": "low",
                              "reason": "Evidence fingerprint could not be established or verified; Admin Review required."}
                        for key, label in [
                            ("ff_arena_assessment_openai", "FF Arena AI Assessment · OpenAI"),
                            ("ff_arena_assessment_ollama", "FF Arena AI Assessment · Ollama Cloud"),
                            ("ff_arena_agent_openai", "FF Arena AI Agent Audit · OpenAI"),
                            ("ff_arena_agent_ollama", "FF Arena AI Agent Audit · Ollama Cloud"),
                        ]
                    }
                    submission.ai_review_notes = (
                        "AI ASSESSMENT STATUS: PROVIDER_UNAVAILABLE_OR_FAILED. "
                        "The evidence was saved, but no reliable AI result was returned. "
                        "The AI Agent has flagged this submission for Admin Review; "
                        "no automatic reward was issued. Technical detail: "
                        f"{exc.__class__.__name__}: {str(exc).strip()[:700]}"
                    )[:2000]
                    submission.save(update_fields=[
                        "ai_proposed_kills", "ai_confidence", "ai_uid_matches",
                        "ai_review_notes", "proposed_reward", "ai_reviewer_reports",
                    ])
                    messages.warning(
                        request,
                        "Evidence save ho gaya. AI assessment record bana diya gaya hai, "
                        "lekin AI provider se result nahi mila. Submission Admin Review queue mein hai; "
                        "koi automatic reward nahi diya gaya.",
                    )
                return redirect("tournaments:my_registrations")
    else:
        form = KillSubmissionForm(initial={"free_fire_uid": registration.free_fire_uid})

    return render(request, "tournaments/kill_submission.html", {
        "form": form,
        "registration": registration,
        "tournament": registration.tournament,
    })


@login_required
@user_passes_test(lambda user: user.is_staff)
def admin_kill_review(request):
    cleanup_expired_kill_evidence()
    submissions = KillSubmission.objects.filter(
        status=KillSubmission.Status.PENDING
    ).select_related("player", "tournament", "registration")
    tournament_id = request.GET.get("tournament")
    if tournament_id and str(tournament_id).isdigit():
        submissions = submissions.filter(tournament_id=int(tournament_id))
    submission_id = request.GET.get("submission")
    if submission_id and str(submission_id).isdigit():
        submissions = submissions.filter(pk=int(submission_id))

    # Do not render broken media links that return 404 when a deployment's
    # media storage no longer has the uploaded file.
    for item in submissions:
        for field_name, flag_name in (
            ("history_video", "history_video_available"),
            ("history_image_one", "history_image_one_available"),
            ("history_image_two", "history_image_two_available"),
        ):
            media = getattr(item, field_name)
            available = False
            if media and media.name:
                try:
                    available = media.storage.exists(media.name)
                except (OSError, ValueError):
                    available = False
            setattr(item, flag_name, available)

    return render(request, "tournaments/admin_kill_review.html", {
        "submissions": submissions,
        "selected_tournament_id": tournament_id or "",
        "ai_provider": "LOCAL · FOUR REVIEWERS",
        "ai_model": "Tesseract OCR + Pillow + FFmpeg",
        "ai_openai_configured": False,
        "ai_compatible_configured": False,
        "diamonds_per_kill": int(settings.DIAMONDS_PER_APPROVED_KILL),
        "minimum_verified_kills": int(settings.MINIMUM_VERIFIED_KILLS),
    })


@login_required
@user_passes_test(lambda user: user.is_staff)
def ai_assessment_dashboard(request):
    """Separate staff page for all AI assessment results and items needing manual revision."""
    submissions = KillSubmission.objects.select_related(
        "player", "tournament", "registration"
    ).order_by("-submitted_at")
    status_filter = request.GET.get("status", "").strip()
    if status_filter in dict(KillSubmission.Status.choices):
        submissions = submissions.filter(status=status_filter)
    return render(request, "tournaments/admin_ai_assessments.html", {
        "submissions": submissions[:250],
        "status_filter": status_filter,
        "status_choices": KillSubmission.Status.choices,
        "pending_count": KillSubmission.objects.filter(status=KillSubmission.Status.PENDING).count(),
        "approved_count": KillSubmission.objects.filter(status=KillSubmission.Status.APPROVED).count(),
        "rejected_count": KillSubmission.objects.filter(status=KillSubmission.Status.REJECTED).count(),
    })


@login_required
@user_passes_test(lambda user: user.is_staff)
def ai_source_settings(request):
    """Show local reviewer readiness; no external AI provider or API key is used."""
    import shutil
    return render(request, "tournaments/admin_ai_sources.html", {
        "provider": "LOCAL FOUR-REVIEWER ENGINE",
        "openai_model": "Not used",
        "open_source_model": "Not used",
        "openai_key_configured": False,
        "open_source_endpoint_configured": False,
        "open_source_key_configured": False,
        "dual_mode": False,
        "tesseract_available": bool(shutil.which(os.getenv("TESSERACT_PATH", "tesseract"))),
        "ffmpeg_available": bool(os.getenv("FFMPEG_PATH")) or bool(shutil.which("ffmpeg")),
        "diamonds_per_kill": int(settings.DIAMONDS_PER_APPROVED_KILL),
        "minimum_kills": int(settings.MINIMUM_VERIFIED_KILLS),
    })


@login_required
@user_passes_test(lambda user: user.is_staff)
@require_POST
def retry_ai_kill_review(request, submission_id):
    submission = get_object_or_404(
        KillSubmission.objects.select_related("registration", "player", "tournament"),
        pk=submission_id,
    )
    if submission.status != KillSubmission.Status.PENDING:
        messages.error(request, "Sirf pending submission ka AI review dobara chala sakte hain.")
        return redirect("tournaments:admin_kill_review")

    try:
        result = analyze_kill_evidence(submission)
        proposed = result.get("proposed_kills")
        uid_ok = (
            result.get("uid_matches") is True
            and submission.free_fire_uid == submission.registered_uid
            and submission.registered_uid == submission.registration.free_fire_uid
            and str(getattr(submission.player, "free_fire_uid", "") or "").strip() == submission.registration.free_fire_uid
        )
        submission.ai_reviewer_reports = result.get("reviewer_reports", {})
        date_ok, date_note = validate_match_dates(
            submission.ai_reviewer_reports, submission.tournament
        )
        duplicate_match = has_duplicate_match_id(submission)
        match_id_ok = bool(get_match_id(submission.ai_reviewer_reports))
        if (
            proposed is not None and proposed >= settings.MINIMUM_VERIFIED_KILLS
            and uid_ok and date_ok and match_id_ok and not duplicate_match
        ):
            _currency, quantity, _label = reward_for_tournament(submission.tournament, proposed)
            submission.proposed_reward = Decimal(quantity)
        else:
            submission.proposed_reward = Decimal("0.00")
        submission.ai_proposed_kills = proposed
        submission.ai_confidence = (result.get("confidence") or "")[:10]
        submission.ai_uid_matches = result.get("uid_matches")
        submission.ai_review_notes = (
            (result.get("reason") or "") + "\nDATE CHECK: " + date_note
            + ("\nDUPLICATE MATCH ID: blocked." if duplicate_match else "")
            + ("\nMATCH ID: missing or reviewers disagreed." if not match_id_ok else "")
        )[:6000]
        submission.ai_reviewer_reports = result.get("reviewer_reports", {})
        submission.save(update_fields=[
            "ai_proposed_kills", "ai_confidence", "ai_uid_matches",
            "ai_review_notes", "proposed_reward", "ai_reviewer_reports",
        ])
        if result.get("four_way_agreement") is True and uid_ok and date_ok and match_id_ok and not duplicate_match:
            messages.success(request, f"Four AI reviewers agreed: {proposed} kills reported. Kill Verification does not issue rewards; submission remains for Admin Review.")
        else:
            messages.info(request, "AI review updated. Any failed check or disagreement remains in Admin Review.")
    except Exception as exc:
        submission.ai_reviewer_reports = {
            key: {"name": label, "status": "BLOCKED", "proposed_kills": None, "confidence": "low", "reason": "Evidence integrity check failed or original upload fingerprint is missing; manual Admin Review required."}
            for key, label in [
                ("ff_arena_assessment_openai", "FF Arena AI Assessment · OpenAI"),
                ("ff_arena_assessment_ollama", "FF Arena AI Assessment · Ollama Cloud"),
                ("ff_arena_agent_openai", "FF Arena AI Agent Audit · OpenAI"),
                ("ff_arena_agent_ollama", "FF Arena AI Agent Audit · Ollama Cloud"),
            ]
        }
        submission.ai_review_notes = f"AI review blocked ({exc.__class__.__name__}): {str(exc).strip()[:850]}"
        submission.save(update_fields=["ai_review_notes", "ai_reviewer_reports"])
        messages.error(request, f"AI review abhi fail hua: {str(exc).strip()[:250]}")

    return redirect(f"{reverse('tournaments:admin_kill_review')}?submission={submission.pk}")

@login_required
@user_passes_test(lambda user: user.is_staff)
@require_POST
def review_kill_submission(request, submission_id):
    with transaction.atomic():
        submission = get_object_or_404(
            KillSubmission.objects.select_for_update().select_related("registration", "player", "tournament"),
            pk=submission_id,
        )
        if submission.status != KillSubmission.Status.PENDING:
            messages.error(request, "Yeh submission pehle hi review ho chuki hai.")
            return redirect("tournaments:admin_ai_assessments")

        decision = request.POST.get("decision", "").strip()
        notes = request.POST.get("admin_notes", "").strip()[:4000]
        if decision == "reject":
            submission.status = KillSubmission.Status.REJECTED
            submission.admin_notes = notes
            submission.reviewed_at = timezone.now()
            submission.save(update_fields=["status", "admin_notes", "reviewed_at"])
            messages.success(request, "Submission reject kar di gayi. Status AI Assessment Queue mein update ho gaya hai.")
            return redirect("tournaments:admin_ai_assessments")

        if decision != "approve":
            messages.error(request, "Valid review action select karo.")
            return redirect(f"{reverse('tournaments:admin_kill_review')}?submission={submission.pk}")

        try:
            approved_kills = int(request.POST.get("approved_kills", ""))
        except (TypeError, ValueError):
            messages.error(request, "Approved kills ek valid whole number hona chahiye.")
            return redirect(f"{reverse('tournaments:admin_kill_review')}?submission={submission.pk}")
        if approved_kills < 0 or approved_kills > 99:
            messages.error(request, "Approved kills 0 se 99 ke beech hone chahiye.")
            return redirect(f"{reverse('tournaments:admin_kill_review')}?submission={submission.pk}")
        if (
            submission.registration.status != Registration.Status.READY
            or submission.registration.refund_processed
            or not submission.registration.payment_verified
            or submission.tournament.status == Tournament.Status.CANCELLED
            or submission.free_fire_uid != submission.registered_uid
            or submission.registered_uid != submission.registration.free_fire_uid
            or str(getattr(submission.player, "free_fire_uid", "") or "").strip() != submission.registration.free_fire_uid
        ):
            messages.error(request, "UID mismatch hai; payout eligibility roki gayi.")
            return redirect(f"{reverse('tournaments:admin_kill_review')}?submission={submission.pk}")

        date_ok, date_note = validate_match_dates(
            submission.ai_reviewer_reports, submission.tournament
        )
        if not date_ok and "DATE_OVERRIDE:" not in notes:
            messages.error(
                request,
                "Match date verify nahi hui. Original screenshots/video manually check karke admin notes ki shuruaat DATE_OVERRIDE: aur reason se karein. " + date_note,
            )
            return redirect(f"{reverse('tournaments:admin_kill_review')}?submission={submission.pk}")
        if has_duplicate_match_id(submission):
            messages.error(request, "Same match ID is already used for this UID in this tournament. Reward blocked.")
            return redirect(f"{reverse('tournaments:admin_kill_review')}?submission={submission.pk}")
        if not get_match_id(submission.ai_reviewer_reports) and "MATCH_ID_OVERRIDE:" not in notes:
            messages.error(request, "Match ID AI se confirm nahi hua. Original evidence manually verify karke admin notes ki shuruaat MATCH_ID_OVERRIDE: aur reason se karein.")
            return redirect(f"{reverse('tournaments:admin_kill_review')}?submission={submission.pk}")
        submission.admin_notes = notes
        try:
            credited = _credit_kill_submission_reward(
                submission, approved_kills, source="Admin-approved kill reward"
            )
        except ValueError as exc:
            messages.error(request, str(exc))
            return redirect(f"{reverse('tournaments:admin_kill_review')}?submission={submission.pk}")
        reward_text = ", ".join(f"{qty} {label}" for qty, label in credited) or "0 reward"


    messages.success(
        request,
        f"Admin confirmation complete: {approved_kills} kills approved; {reward_text} credited to the player's in-app wallet. These are non-cash rewards.",
    )
    return redirect(f"{reverse('tournaments:admin_kill_review')}?submission={submission.pk}")



@login_required
@user_passes_test(lambda user: user.is_staff)
def admin_kill_batch_review(request):
    """One-tournament batch view for reviewing and crediting many player rewards."""
    tournaments = Tournament.objects.filter(
        kill_submissions__isnull=False
    ).distinct().order_by("-start_time")
    tournament_id = request.POST.get("tournament_id") if request.method == "POST" else request.GET.get("tournament", "")
    selected_tournament = None
    if tournament_id and str(tournament_id).isdigit():
        selected_tournament = get_object_or_404(Tournament, pk=int(tournament_id))

    if request.method == "POST":
        if selected_tournament is None:
            messages.error(request, "Pehle ek tournament select karo.")
            return redirect("tournaments:admin_kill_batch_review")
        selected_ids = request.POST.getlist("submission_ids")
        if not selected_ids:
            messages.error(request, "Bulk approval ke liye kam se kam ek player select karo.")
            return redirect(f"{reverse('tournaments:admin_kill_batch_review')}?tournament={selected_tournament.pk}")
        common_notes = request.POST.get("bulk_admin_notes", "").strip()[:1000]
        approved_count = 0
        skipped = []
        with transaction.atomic():
            for submission_id in selected_ids:
                if not str(submission_id).isdigit():
                    continue
                submission = (
                    KillSubmission.objects.select_for_update()
                    .select_related("player", "registration", "tournament")
                    .filter(pk=int(submission_id), tournament=selected_tournament)
                    .first()
                )
                if not submission or submission.status != KillSubmission.Status.PENDING:
                    skipped.append(str(submission_id))
                    continue
                if (
                    not submission.registration.payment_verified
                    or submission.registration.status != Registration.Status.READY
                    or submission.registration.refund_processed
                    or submission.free_fire_uid != submission.registered_uid
                    or submission.registered_uid != submission.registration.free_fire_uid
                    or str(getattr(submission.player, "free_fire_uid", "") or "").strip() != submission.registration.free_fire_uid
                ):
                    skipped.append(str(submission_id))
                    continue
                try:
                    kills = int(request.POST.get(f"approved_kills_{submission.pk}", ""))
                except (TypeError, ValueError):
                    skipped.append(str(submission_id))
                    continue
                if kills < 0 or kills > 99:
                    skipped.append(str(submission_id))
                    continue
                raw_override = request.POST.get(f"reward_override_{submission.pk}", "").strip()
                override = None
                if raw_override:
                    try:
                        override = int(raw_override)
                    except (TypeError, ValueError):
                        skipped.append(str(submission_id))
                        continue
                    if override < 0 or override > 1000000 or kills < settings.MINIMUM_VERIFIED_KILLS:
                        skipped.append(str(submission_id))
                        continue
                date_ok, _date_note = validate_match_dates(
                    submission.ai_reviewer_reports, submission.tournament
                )
                if (
                    (not date_ok and "DATE_OVERRIDE:" not in common_notes)
                    or has_duplicate_match_id(submission)
                    or (not get_match_id(submission.ai_reviewer_reports) and "MATCH_ID_OVERRIDE:" not in common_notes)
                ):
                    skipped.append(str(submission_id))
                    continue
                submission.admin_notes = common_notes or "Reviewed in tournament bulk reward panel."
                try:
                    _credit_kill_submission_reward(
                        submission, kills, reward_override=override,
                        source="Admin bulk-approved tournament reward",
                    )
                except ValueError:
                    skipped.append(str(submission_id))
                    continue
                approved_count += 1
        if skipped:
            messages.warning(request, f"{approved_count} players approved and credited. {len(skipped)} rows skipped because of status, UID/payment mismatch, or invalid values.")
        else:
            messages.success(request, f"{approved_count} players approved and tournament rewards credited in one batch.")
        return redirect(f"{reverse('tournaments:admin_kill_batch_review')}?tournament={selected_tournament.pk}")

    submissions = KillSubmission.objects.none()
    if selected_tournament:
        submissions = KillSubmission.objects.filter(
            tournament=selected_tournament,
        ).select_related("player", "registration", "tournament").order_by("-submitted_at")
    return render(request, "tournaments/admin_kill_batch.html", {
        "tournaments": tournaments,
        "selected_tournament": selected_tournament,
        "submissions": submissions,
        "minimum_verified_kills": int(settings.MINIMUM_VERIFIED_KILLS),
    })


def results(request):
    completed_tournaments = Tournament.objects.filter(
        status=Tournament.Status.COMPLETED
    ).order_by("-start_time")
    return render(
        request,
        "tournaments/results.html",
        {"completed_tournaments": completed_tournaments},
    )


def leaderboard(request, tournament_id):
    """Show every paid, verified entrant; kills/rewards appear only after admin approval."""
    tournament = get_object_or_404(Tournament, pk=tournament_id)
    eligible_statuses = [
        Registration.Status.CONFIRMED,
        Registration.Status.WAITING_READY,
        Registration.Status.READY,
    ]
    registrations = list(
        Registration.objects.filter(
            tournament=tournament,
            payment_verified=True,
            refund_processed=False,
            status__in=eligible_statuses,
        ).select_related("player").order_by("registered_at")
    )
    approved_submissions = {
        item.registration_id: item
        for item in KillSubmission.objects.filter(
            tournament=tournament,
            status=KillSubmission.Status.APPROVED,
        ).select_related("player", "registration")
    }
    rows = []
    for registration in registrations:
        submission = approved_submissions.get(registration.pk)
        rows.append({
            "registration": registration,
            "submission": submission,
            "kills": submission.approved_kills if submission and submission.approved_kills is not None else -1,
            "is_winner": bool(tournament.winner_uid and registration.free_fire_uid == tournament.winner_uid),
        })

    # Admin-confirmed winner stays first; remaining verified entrants sort by approved kills,
    # with players awaiting evidence/review still visible and shown as pending.
    rows.sort(key=lambda row: (
        not row["is_winner"],
        -row["kills"],
        row["registration"].registered_at,
    ))
    return render(request, "tournaments/leaderboard.html", {
        "tournament": tournament,
        "leaderboard_rows": rows,
        "verified_player_count": len(rows),
        "diwali_winner_reward_awarded": TournamentLedgerEntry.objects.filter(
            tournament=tournament,
            reference=f"DIWALI-WINNER-20-DIAMONDS-{tournament.pk}",
            status=TournamentLedgerEntry.Status.COMPLETED,
        ).exists() if tournament.is_diwali_offer else False,
    })
