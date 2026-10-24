
from decimal import Decimal

from django.db import transaction

from .models import Tournament, Registration


class RegistrationError(Exception):
    """Raised when a tournament registration cannot proceed."""


@transaction.atomic
def create_pending_registration(
    *,
    tournament_id,
    player,
    free_fire_uid,
):
    tournament = Tournament.objects.select_for_update().get(
        pk=tournament_id
    )

    if tournament.status != Tournament.Status.UPCOMING:
        raise RegistrationError(
            "Yeh tournament abhi registration ke liye available nahi hai."
        )

    if tournament.start_time <= __import__(
        "django.utils.timezone", fromlist=["now"]
    ).now():
        raise RegistrationError(
            "Tournament ka start time nikal chuka hai."
        )

    if tournament.is_full:
        raise RegistrationError(
            "Tournament ki seats full ho chuki hain."
        )

    uid = str(free_fire_uid).strip()

    if not uid.isdigit() or not 5 <= len(uid) <= 32:
        raise RegistrationError(
            "Free Fire UID 5 se 32 digits ka hona chahiye."
        )

    if Registration.objects.filter(
        tournament=tournament,
        player=player,
    ).exists():
        raise RegistrationError(
            "Aap is tournament mein pehle se registered hain."
        )

    return Registration.objects.create(
        tournament=tournament,
        player=player,
        free_fire_uid=uid,
        entry_fee_paid=Decimal("0.00"),
        payment_verified=False,
        status=Registration.Status.PENDING_PAYMENT,
    )
