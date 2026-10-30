from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from .models import Registration, Tournament, TournamentLedgerEntry


class RegistrationError(Exception):
    """Raised when a tournament registration cannot proceed."""


def send_unlimited_live_notifications(tournament_id):
    """Email the admin and all verified entrants after a 49-player Unlimited round starts."""
    tournament = Tournament.objects.filter(
        pk=tournament_id, is_unlimited_br=True, status=Tournament.Status.LIVE
    ).first()
    if not tournament:
        return

    registrations = list(
        Registration.objects.filter(
            tournament=tournament,
            payment_verified=True,
            refund_processed=False,
            status__in=[
                Registration.Status.CONFIRMED,
                Registration.Status.WAITING_READY,
                Registration.Status.READY,
            ],
        ).select_related("player").order_by("registered_at")
    )
    admin_recipients = []
    configured_admin = getattr(settings, "TOURNAMENT_ADMIN_EMAIL", "").strip()
    if configured_admin:
        admin_recipients.append(configured_admin)
    for entry in getattr(settings, "ADMINS", []):
        email = (entry[1] or "").strip()
        if email and email not in admin_recipients:
            admin_recipients.append(email)
    if not admin_recipients:
        sender_email = (settings.DEFAULT_FROM_EMAIL or "").strip()
        if sender_email and "@" in sender_email:
            admin_recipients.append(sender_email)

    tournament_url = settings.SITE_URL + reverse("tournaments:detail", args=[tournament.pk])
    subject = f"FF Arena Unlimited Tournament is LIVE: {tournament.title}"
    admin_message = (
        f"Unlimited Tournament is now LIVE.\n\n"
        f"Name: {tournament.title}\n"
        f"Players: {len(registrations)}/{tournament.max_players}\n"
        f"Entry fee: INR {tournament.entry_fee}\n"
        f"Started at: {timezone.localtime(timezone.now()).strftime('%d %b %Y, %I:%M %p')}\n"
        f"Tournament page: {tournament_url}\n"
    )
    success_count = 0
    failure_count = 0
    for recipient in admin_recipients:
        try:
            success_count += send_mail(
                subject, admin_message, settings.DEFAULT_FROM_EMAIL, [recipient],
                fail_silently=False,
            )
        except Exception:
            failure_count += 1

    for registration in registrations:
        email = (registration.player.email or "").strip()
        if not email:
            failure_count += 1
            continue
        player_message = (
            f"Hi {registration.player.username},\n\n"
            f"Your Unlimited Tournament, {tournament.title}, is now LIVE!\n"
            f"Your Free Fire UID: {registration.free_fire_uid}\n"
            f"Entry fee paid by: {registration.get_payment_method_display()}\n"
            f"Players: {len(registrations)}/{tournament.max_players}\n\n"
            f"Open tournament page: {tournament_url}\n\n"
            "Room ID/password will be shared only through the website when the admin enables access.\n"
        )
        try:
            success_count += send_mail(
                subject, player_message, settings.DEFAULT_FROM_EMAIL, [email],
                fail_silently=False,
            )
        except Exception:
            failure_count += 1

    expected_count = len(registrations) + len(admin_recipients)
    tournament.live_notification_status = (
        "sent" if failure_count == 0 and success_count >= expected_count
        else ("partial" if success_count else "failed")
    )
    if success_count:
        tournament.live_notification_sent_at = timezone.now()
    tournament.save(update_fields=[
        "live_notification_sent_at", "live_notification_status", "updated_at",
    ])


def tournament_team_size(tournament):
    if tournament.mode != Tournament.Mode.BR:
        return 1
    return {"duo": 2, "squad": 4}.get(tournament.br_format, 1)


@transaction.atomic
def assign_teams_for_tournament(tournament_id):
    """Assign complete teams in verified registration order when room is created."""
    tournament = Tournament.objects.select_for_update().get(pk=tournament_id)
    team_size = tournament_team_size(tournament)
    registrations = list(Registration.objects.select_for_update().filter(
        tournament=tournament, payment_verified=True, refund_processed=False,
        status__in=[Registration.Status.CONFIRMED, Registration.Status.WAITING_READY, Registration.Status.READY],
    ).order_by("registered_at", "pk"))
    if not registrations:
        raise ValueError("Room banane se pehle verified players zaroori hain.")
    if len(registrations) % team_size:
        raise ValueError(f"{len(registrations)} verified players se complete {team_size}-player teams nahi ban sakti.")
    for index, registration in enumerate(registrations):
        registration.team_number = index // team_size + 1
        registration.team_position = index % team_size + 1
    Registration.objects.bulk_update(registrations, ["team_number", "team_position"])
    return len(registrations), team_size


@transaction.atomic
def maybe_start_unlimited_tournament(tournament_id):
    """Auto-start when the format's configured verified-player capacity is full."""
    tournament = Tournament.objects.select_for_update().get(pk=tournament_id)
    if not tournament.is_unlimited_br or not tournament.auto_start_at_capacity or tournament.status != Tournament.Status.UPCOMING:
        return False

    active_count = Registration.objects.filter(
        tournament=tournament,
        payment_verified=True,
        status__in=[Registration.Status.CONFIRMED, Registration.Status.WAITING_READY, Registration.Status.READY],
    ).count()
    team_size = tournament_team_size(tournament)
    if active_count < tournament.max_players or active_count % team_size:
        return False

    tournament.status = Tournament.Status.LIVE
    tournament.save(update_fields=["status", "updated_at"])
    transaction.on_commit(lambda tournament_id=tournament.pk: send_unlimited_live_notifications(tournament_id))
    return True


@transaction.atomic
def create_pending_registration(*, tournament_id, player, free_fire_uid, payment_reference="", payment_method="upi"):
    tournament = Tournament.objects.select_for_update().get(pk=tournament_id)

    if tournament.status != Tournament.Status.UPCOMING:
        raise RegistrationError("Yeh tournament abhi registration ke liye available nahi hai.")
    if tournament.start_time <= timezone.now() and not tournament.is_unlimited_br:
        raise RegistrationError("Tournament ka start time nikal chuka hai.")
    if tournament.is_full:
        raise RegistrationError("Tournament ki seats full ho chuki hain.")

    uid = str(free_fire_uid).strip()
    if not uid.isdigit() or not 5 <= len(uid) <= 30:
        raise RegistrationError("Free Fire UID 5 se 30 digits ka hona chahiye.")
    if Registration.objects.filter(tournament=tournament, player=player).exists():
        raise RegistrationError("Aap is tournament mein pehle se registered hain.")
    if tournament.is_free_fan_tournament:
        cooldown = timezone.now() - timedelta(hours=24)
        recent_free_entry = Registration.objects.filter(
            player=player, tournament__is_free_fan_tournament=True,
            registered_at__gte=cooldown,
        ).exclude(status__in=[Registration.Status.CANCELLED, Registration.Status.REFUNDED]).exists()
        if recent_free_entry:
            raise RegistrationError("Aap free tournament mein 24 ghante mein sirf ek baar entry le sakte hain. Cooldown khatam hone par dobara try karein.")

    fee = tournament.entry_fee
    reference = str(payment_reference or "").strip()
    currency_amount = 0
    if fee <= Decimal("0.00"):
        payment_method = "free"
        registration_status = Registration.Status.CONFIRMED
        payment_verified = True
    elif payment_method == "diamonds":
        if fee != fee.to_integral_value():
            raise RegistrationError("Diamond entry ke liye fee poore rupees mein honi chahiye. Admin se contact karein.")
        currency_amount = int(fee)  # 1 diamond = ₹1 entry value
        from apps.social.models import PlayerShopWallet
        shop_wallet, _ = PlayerShopWallet.objects.get_or_create(user=player)
        shop_wallet = PlayerShopWallet.objects.select_for_update().get(pk=shop_wallet.pk)
        if shop_wallet.diamonds < currency_amount:
            raise RegistrationError("NO_DIAMONDS")
        shop_wallet.diamonds -= currency_amount
        shop_wallet.save(update_fields=["diamonds", "updated_at"])
        registration_status = Registration.Status.CONFIRMED
        payment_verified = True
        reference = ""
    elif payment_method == "coins":
        coin_value = fee * Decimal("10")
        if coin_value != coin_value.to_integral_value():
            raise RegistrationError("Coin entry ke liye fee ₹0.10 ke multiples mein honi chahiye.")
        currency_amount = int(coin_value)  # 10 coins = ₹1 entry value
        from apps.social.models import PlayerShopWallet
        shop_wallet, _ = PlayerShopWallet.objects.get_or_create(user=player)
        shop_wallet = PlayerShopWallet.objects.select_for_update().get(pk=shop_wallet.pk)
        if shop_wallet.coins < currency_amount:
            raise RegistrationError("NO_COINS")
        shop_wallet.coins -= currency_amount
        shop_wallet.save(update_fields=["coins", "updated_at"])
        registration_status = Registration.Status.CONFIRMED
        payment_verified = True
        reference = ""
    elif payment_method == "fan_tokens":
        # One Fan Token equals ₹1 of tournament entry value; tokens are non-cash and non-withdrawable.
        if fee != fee.to_integral_value():
            raise RegistrationError("Fan Token entry ke liye fee poore rupees mein honi chahiye.")
        currency_amount = int(fee)
        from apps.social.models import PlayerShopWallet
        shop_wallet, _ = PlayerShopWallet.objects.get_or_create(user=player)
        shop_wallet = PlayerShopWallet.objects.select_for_update().get(pk=shop_wallet.pk)
        if shop_wallet.fan_tokens < currency_amount:
            raise RegistrationError("NO_FAN_TOKENS")
        shop_wallet.fan_tokens -= currency_amount
        shop_wallet.save(update_fields=["fan_tokens", "updated_at"])
        registration_status = Registration.Status.CONFIRMED
        payment_verified = True
        reference = ""
    else:
        if not reference or len(reference) < 6:
            raise RegistrationError("Payment ke baad UTR/reference number zaroor daalein.")
        if Registration.objects.filter(payment_reference__iexact=reference).exists():
            raise RegistrationError("Ye UTR pehle submit ho chuka hai.")
        registration_status = Registration.Status.PENDING_PAYMENT
        payment_verified = False
        payment_method = "upi"

    registration = Registration.objects.create(
        tournament=tournament,
        player=player,
        free_fire_uid=uid,
        entry_fee_paid=fee,
        payment_reference=reference,
        payment_submitted_at=timezone.now() if reference else None,
        payment_verified=payment_verified,
        payment_method=payment_method,
        currency_amount=currency_amount,
        status=registration_status,
    )
    TournamentLedgerEntry.objects.create(
        tournament=tournament, player=player, registration=registration,
        entry_type=TournamentLedgerEntry.EntryType.ENTRY,
        currency={"upi": "inr", "diamonds": "diamonds", "coins": "coins", "fan_tokens": "fan_tokens", "free": "inr"}[registration.payment_method],
        quantity=currency_amount, amount_inr=fee,
        status=TournamentLedgerEntry.Status.PENDING if not payment_verified else TournamentLedgerEntry.Status.COMPLETED,
        reference=reference or f"REG-ENTRY-{registration.pk}",
        description="Tournament entry payment",
    )
    # Wallet entries start immediately at capacity; UPI entries start after admin verifies payment.
    if tournament.is_unlimited_br and tournament.auto_start_at_capacity:
        maybe_start_unlimited_tournament(tournament.pk)
    return registration
