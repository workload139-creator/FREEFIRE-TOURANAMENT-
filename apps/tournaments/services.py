```python
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.wallet.models import Wallet, WalletTransaction
from .models import Registration


@transaction.atomic
def mark_not_playing_and_refund(registration_id):
    registration = (
        Registration.objects
        .select_for_update()
        .select_related("tournament", "player")
        .get(pk=registration_id)
    )

    if registration.ready_confirmed_at:
        return False, "Player has already confirmed."

    if registration.refund_processed:
        return False, "Refund already processed."

    if registration.status not in (
        Registration.Status.CONFIRMED,
        Registration.Status.WAITING_READY,
    ):
        return False, "Registration is not awaiting confirmation."

    if not registration.ready_deadline:
        return False, "Confirmation deadline is not set."

    if timezone.now() < registration.ready_deadline:
        return False, "Confirmation deadline has not passed."

    # Mark the player as not playing and hide room access.
    registration.status = Registration.Status.NOT_PLAYING
    registration.room_details_sent = False

    if registration.payment_verified:
        amount = Decimal(str(registration.entry_fee_paid))

        if amount > 0:
            reference = f"REG-REFUND-{registration.pk}"

            # A stable reference must never create a second refund.
            existing = WalletTransaction.objects.filter(
                reference=reference
            ).first()

            if existing:
                if existing.status != WalletTransaction.Status.COMPLETED:
                    return False, "Existing refund transaction is not completed."

                # A completed ledger entry means the refund was already recorded.
                registration.refund_processed = True
                registration.refund_processed_at = timezone.now()
                registration.refund_reference = reference

            else:
                wallet = (
                    Wallet.objects
                    .select_for_update()
                    .get(
                        user=registration.player,
                        is_admin_wallet=False,
                    )
                )

                wallet.balance += amount
                wallet.save(update_fields=["balance", "updated_at"])

                WalletTransaction.objects.create(
                    wallet=wallet,
                    transaction_type=WalletTransaction.Type.REFUND,
                    amount=amount,
                    status=WalletTransaction.Status.COMPLETED,
                    reference=reference,
                    description=(
                        f"Entry fee refund for tournament "
                        f"{registration.tournament_id}"
                    ),
                )

                registration.refund_processed = True
                registration.refund_processed_at = timezone.now()
                registration.refund_reference = reference
        else:
            # Verified payment with no refundable amount.
            registration.refund_processed = True
            registration.refund_processed_at = timezone.now()
    else:
        # Payment was not verified, so no wallet credit is due.
        registration.refund_processed = True
        registration.refund_processed_at = timezone.now()

    registration.save(
        update_fields=[
            "status",
            "room_details_sent",
            "refund_processed",
            "refund_processed_at",
            "refund_reference",
            "updated_at",
        ]
    )

    return True, "Player marked NOT_PLAYING."
```
