from django.utils import timezone

from .models import Registration


def get_confirmation_deadline(registration):
    """Return the deadline stored when the room details were sent."""
    return registration.ready_deadline


def confirmation_has_expired(registration, now=None):
    deadline = get_confirmation_deadline(registration)
    if deadline is None:
        return False
    return (now or timezone.now()) >= deadline


def player_can_confirm(registration, now=None):
    now = now or timezone.now()
    return (
        registration.status == Registration.Status.WAITING_READY
        and registration.payment_verified
        and registration.room_details_sent
        and registration.ready_deadline is not None
        and now < registration.ready_deadline
    )
