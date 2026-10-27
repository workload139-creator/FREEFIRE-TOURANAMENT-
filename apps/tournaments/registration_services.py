from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from .models import Registration, Tournament


class RegistrationError(Exception):
    """Raised when a tournament registration cannot proceed."""


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
    # Start a BR round at 49 registrations, then optionally open a fresh round.
    if tournament.is_unlimited_br and tournament.auto_start_at_capacity:
        active_count = Registration.objects.filter(
            tournament=tournament,
            payment_verified=True,
            status__in=[Registration.Status.CONFIRMED, Registration.Status.WAITING_READY, Registration.Status.READY],
        ).count()
        if active_count >= tournament.max_players:
            tournament.status = Tournament.Status.LIVE
            tournament.save(update_fields=["status", "updated_at"])
            root_id = tournament.series_root_id or tournament.pk
            root = Tournament.objects.select_for_update().get(pk=root_id)
            if root.auto_reopen:
                next_round_number = root.series_rounds.count() + 2
                Tournament.objects.create(
                    title=f"{root.title} - Round {next_round_number}"[:120],
                    mode=Tournament.Mode.BR, vs_format="", description=root.description,
                    entry_fee=root.entry_fee, prize_pool=root.prize_pool, max_players=49,
                    start_time=timezone.now() + timedelta(minutes=10),
                    status=Tournament.Status.UPCOMING, is_unlimited_br=True,
                    auto_start_at_capacity=True, auto_reopen=root.auto_reopen, series_root=root,
                )
    return registration
