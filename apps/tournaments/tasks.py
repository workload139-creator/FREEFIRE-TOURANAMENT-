
from django.utils import timezone

from .models import Registration
from .services import mark_not_playing_and_refund


def process_expired_confirmations():
    now = timezone.now()

    expired_ids = list(
        Registration.objects.filter(
            status__in=[
                Registration.Status.CONFIRMED,
                Registration.Status.WAITING_READY,
            ],
            ready_deadline__isnull=False,
            ready_deadline__lte=now,
            ready_confirmed_at__isnull=True,
            refund_processed=False,
        ).values_list("id", flat=True)
    )

    results = []

    for registration_id in expired_ids:
        try:
            results.append(
                (
                    registration_id,
                    mark_not_playing_and_refund(registration_id),
                )
            )
        except Registration.DoesNotExist:
            continue

    return results
