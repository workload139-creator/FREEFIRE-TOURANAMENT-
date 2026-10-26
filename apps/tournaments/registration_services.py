from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from .models import Registration, Tournament


class RegistrationError(Exception):
    """Raised when a tournament registration cannot proceed."""


@transaction.atomic
def create_pending_registration(*, tournament_id, player, free_fire_uid, payment_reference=""):
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
    if fee > Decimal("0.00"):
        if not reference or len(reference) < 6:
            raise RegistrationError("Payment ke baad UTR/reference number zaroor daalein.")
        if Registration.objects.filter(payment_reference__iexact=reference).exists():
            raise RegistrationError("Ye UTR pehle submit ho chuka hai.")
        registration_status = Registration.Status.PENDING_PAYMENT
        payment_verified = False
    else:
        registration_status = Registration.Status.CONFIRMED
        payment_verified = True

    registration = Registration.objects.create(
        tournament=tournament,
        player=player,
        free_fire_uid=uid,
        entry_fee_paid=fee,
        payment_reference=reference,
        payment_submitted_at=timezone.now() if reference else None,
        payment_verified=payment_verified,
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
