from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.accounts.models import AdminWallet, AdminWalletTransaction, Wallet, WalletTransaction
from .models import Registration, Tournament


@transaction.atomic
def award_tournament_winner(tournament_id):
    """Pay the admin-selected registered UID the configured tournament prize once."""
    tournament = Tournament.objects.select_for_update().get(pk=tournament_id)
    winner_uid = str(tournament.winner_uid or "").strip()
    if not winner_uid:
        return False, "Winner UID enter nahi ki gayi."
    if tournament.winner_prize_paid:
        return False, "Winner prize pehle hi pay ho chuka hai."
    if not winner_uid.isdigit():
        return False, "Winner UID sirf digits ki honi chahiye."
    eligible = Registration.objects.select_for_update().filter(
        tournament=tournament, free_fire_uid=winner_uid, payment_verified=True,
        refund_processed=False,
        status__in=[Registration.Status.CONFIRMED, Registration.Status.WAITING_READY, Registration.Status.READY],
    ).select_related("player")
    if eligible.count() != 1:
        return False, "Is tournament mein is UID ka exactly ek verified player hona chahiye."
    registration = eligible.first()
    prize = Decimal(str(tournament.prize_pool or "0.00"))
    if prize <= Decimal("0.00"):
        return False, "Tournament ka prize pool ₹0 hai; pehle admin panel mein prize pool set karein."
    reference = f"WIN-PRIZE-{tournament.pk}-{registration.pk}"
    if WalletTransaction.objects.filter(reference=reference).exists():
        return False, "Winner prize ka transaction reference pehle se maujood hai."
    admin_wallet, _ = AdminWallet.objects.get_or_create(name="Main Admin Wallet")
    admin_wallet = AdminWallet.objects.select_for_update().get(pk=admin_wallet.pk)
    if admin_wallet.balance < prize:
        return False, f"Admin wallet mein ₹{prize} se kam balance hai; prize pay nahi hua."
    player_wallet, _ = Wallet.objects.get_or_create(user=registration.player)
    player_wallet = Wallet.objects.select_for_update().get(pk=player_wallet.pk)
    admin_wallet.balance -= prize
    admin_wallet.save(update_fields=["balance", "updated_at"])
    player_wallet.balance += prize
    player_wallet.save(update_fields=["balance", "updated_at"])
    AdminWalletTransaction.objects.create(
        admin_wallet=admin_wallet, transaction_type=AdminWalletTransaction.TransactionType.PRIZE,
        amount=prize, status=AdminWalletTransaction.Status.COMPLETED, reference=reference,
        description=f"₹{prize} first-place prize for tournament {tournament.pk}, UID {winner_uid}",
    )
    WalletTransaction.objects.create(
        wallet=player_wallet, transaction_type=WalletTransaction.TransactionType.PRIZE,
        amount=prize, status=WalletTransaction.Status.COMPLETED, reference=reference,
        description=f"₹50 first-place prize for tournament {tournament.title}",
    )
    tournament.winner_prize_paid = True
    tournament.winner_prize_reference = reference
    tournament.save(update_fields=["winner_prize_paid", "winner_prize_reference", "updated_at"])
    return True, f"₹{prize} winner prize UID {winner_uid} ke wallet mein credit ho gaya."


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

    if amount > 0:
        entry_ref = f"ADMIN-ENTRY-{registration.pk}"
        refund_ref = f"ADMIN-REFUND-{registration.pk}"
        entry_ledger = AdminWalletTransaction.objects.filter(reference=entry_ref, status=AdminWalletTransaction.Status.COMPLETED).first()
        if entry_ledger and not AdminWalletTransaction.objects.filter(reference=refund_ref).exists():
            admin_wallet, _ = AdminWallet.objects.get_or_create(name="Main Admin Wallet")
            admin_wallet = AdminWallet.objects.select_for_update().get(pk=admin_wallet.pk)
            admin_wallet.balance -= amount
            admin_wallet.save(update_fields=["balance", "updated_at"])
            AdminWalletTransaction.objects.create(
                admin_wallet=admin_wallet,
                transaction_type=AdminWalletTransaction.TransactionType.REFUND,
                amount=amount,
                status=AdminWalletTransaction.Status.COMPLETED,
                reference=refund_ref,
                description=f"Reverse entry fee for player who missed tournament {registration.tournament_id}",
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
    already_cancelled = tournament.status == Tournament.Status.CANCELLED

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

    prefix = "Tournament was already cancelled" if already_cancelled else "Tournament cancelled"
    return refunded, f"{prefix}; {refunded} registration(s) refunded."


@transaction.atomic
def process_expired_ready_registrations(limit=500):
    """Refund and mark players who missed the 60-second room confirmation window."""
    now = timezone.now()
    registration_ids = list(
        Registration.objects.filter(
            status=Registration.Status.WAITING_READY,
            ready_deadline__lte=now,
            ready_confirmed_at__isnull=True,
            refund_processed=False,
        ).order_by("ready_deadline").values_list("pk", flat=True)[:limit]
    )
    processed = 0
    for registration_id in registration_ids:
        changed, _message = mark_not_playing_and_refund(registration_id)
        if changed:
            processed += 1
    return processed
