
from datetime import timedelta

from django.utils import timezone

from .constants import PLAYER_CONFIRMATION_TIMEOUT_SECONDS
from .models import Registration


def get_confirmation_deadline(registration):
    """Return the deadline based on when room confirmation was requested."""
    requested_at = getattr(registration, "room_sent_at", None)

    if requested_at is None:
        return None

    return requested_at + timedelta(
        seconds=PLAYER_CONFIRMATION_TIMEOUT_SECONDS
    )


def confirmation_has_expired(registration, now=None):
    """Check whether the player's confirmation deadline has passed."""
    deadline = get_confirmation_deadline(registration)

    if deadline is None:
        return False

    now = now or timezone.now()
    return now >= deadline


def player_can_confirm(registration, now=None):
    """Check basic registration eligibility for player confirmation."""
    now = now or timezone.now()

    return (
        registration.status == Registration.Status.WAITING_READY
        and registration.payment_verified
        and not confirmation_has_expired(registration, now)
    )
