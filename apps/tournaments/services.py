from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Wallet, WalletTransaction
from .models import Registration


@transaction.atomic
def mark_not_playing_and_refund(registration_id):
    registration = (
        Registration.objects.select_for_update()
        .select_related("tournament", "player")
        .get(pk=registration_id)
    )

    if registration.ready_confirmed_at or registration.status == Registration.Status.READY:
        return False, "Player has already confirmed."
    if registration.refund_processed:
        return False, "Refund already processed."
    if registration.status != Registration.Status.WAITING_READY:
        return False, "Registration is not awaiting confirmation."
    if not registration.ready_deadline:
        return False, "Confirmation deadline is not set."
    if timezone.now() < registration.ready_deadline:
        return False, "Confirmation deadline has not passed."

    amount = Decimal(str(registration.entry_fee_paid))
    if amount > 0:
        reference = f"REG-REFUND-{registration.pk}"
        existing = WalletTransaction.objects.filter(reference=reference).first()
        if existing:
            if existing.status != WalletTransaction.Status.COMPLETED:
                return False, "Existing refund transaction is not completed."
        else:
            wallet, _ = Wallet.objects.get_or_create(user=registration.player)
            wallet = Wallet.objects.select_for_update().get(pk=wallet.pk)
            wallet.balance += amount
            wallet.save(update_fields=["balance", "updated_at"])
            WalletTransaction.objects.create(
                wallet=wallet,
                transaction_type=WalletTransaction.TransactionType.REFUND,
                amount=amount,
                status=WalletTransaction.Status.COMPLETED,
                reference=reference,
                description=f"Entry fee refund for tournament {registration.tournament_id}",
            )

    registration.status = Registration.Status.NOT_PLAYING
    registration.room_details_sent = False
    registration.refund_processed = True
    registration.refund_processed_at = timezone.now()
    registration.refund_reference = f"REG-REFUND-{registration.pk}" if amount > 0 else ""
    registration.save(update_fields=[
        "status", "room_details_sent", "refund_processed",
        "refund_processed_at", "refund_reference", "updated_at",
    ])
    return True, "Player marked NOT_PLAYING and refund recorded."



@transaction.atomic
def cancel_tournament_and_refund(tournament_id):
    """Cancel a tournament and refund every paid entry exactly once."""
    from .models import Tournament

    tournament = Tournament.objects.select_for_update().get(pk=tournament_id)
    if tournament.status == Tournament.Status.CANCELLED:
        return 0, "Tournament already cancelled."

    tournament.status = Tournament.Status.CANCELLED
    tournament.room_id = ""
    tournament.room_password = ""
    tournament.save(update_fields=["status", "room_id", "room_password", "updated_at"])

    refunded = 0
    registrations = Registration.objects.select_for_update().filter(tournament=tournament)
    for registration in registrations:
        if registration.refund_processed or registration.entry_fee_paid <= 0:
            continue
        reference = f"TOURNEY-CANCEL-REFUND-{registration.pk}"
        existing = WalletTransaction.objects.filter(reference=reference).first()
        if existing:
            if existing.status != WalletTransaction.Status.COMPLETED:
                continue
        else:
            wallet, _ = Wallet.objects.get_or_create(user=registration.player)
            wallet = Wallet.objects.select_for_update().get(pk=wallet.pk)
            wallet.balance += registration.entry_fee_paid
            wallet.save(update_fields=["balance", "updated_at"])
            WalletTransaction.objects.create(
                wallet=wallet,
                transaction_type=WalletTransaction.TransactionType.REFUND,
                amount=registration.entry_fee_paid,
                status=WalletTransaction.Status.COMPLETED,
                reference=reference,
                description=f"Automatic wallet refund because tournament {tournament.title} was cancelled",
            )

        registration.status = Registration.Status.REFUNDED
        registration.room_details_sent = False
        registration.refund_processed = True
        registration.refund_processed_at = timezone.now()
        registration.refund_reference = reference
        registration.save(update_fields=[
            "status", "room_details_sent", "refund_processed",
            "refund_processed_at", "refund_reference", "updated_at",
        ])
        refunded += 1

    return refunded, f"Tournament cancelled; {refunded} registration(s) refunded."
