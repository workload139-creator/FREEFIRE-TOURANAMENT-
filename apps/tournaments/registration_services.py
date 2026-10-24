from decimal import Decimal

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.accounts.models import Wallet, WalletTransaction
from .models import Registration, Tournament


class RegistrationError(Exception):
    """Raised when a tournament registration cannot proceed."""


@transaction.atomic
def create_pending_registration(*, tournament_id, player, free_fire_uid):
    tournament = Tournament.objects.select_for_update().get(pk=tournament_id)

    if tournament.status != Tournament.Status.UPCOMING:
        raise RegistrationError("Yeh tournament abhi registration ke liye available nahi hai.")
    if tournament.start_time <= timezone.now():
        raise RegistrationError("Tournament ka start time nikal chuka hai.")
    if tournament.is_full:
        raise RegistrationError("Tournament ki seats full ho chuki hain.")

    uid = str(free_fire_uid).strip()
    if not uid.isdigit() or not 5 <= len(uid) <= 30:
        raise RegistrationError("Free Fire UID 5 se 30 digits ka hona chahiye.")
    if uid != (player.free_fire_uid or "").strip():
        raise RegistrationError("Tournament UID account ke registered Free Fire UID se match honi chahiye.")
    if Registration.objects.filter(tournament=tournament, player=player).exists():
        raise RegistrationError("Aap is tournament mein pehle se registered hain.")

    wallet, _ = Wallet.objects.get_or_create(user=player)
    wallet = Wallet.objects.select_for_update().get(pk=wallet.pk)
    fee = tournament.entry_fee
    if wallet.balance < fee:
        raise RegistrationError(
            f"Wallet mein balance kam hai. Entry fee ₹{fee} hai; pehle wallet mein deposit karein."
        )

    registration = Registration.objects.create(
        tournament=tournament,
        player=player,
        free_fire_uid=uid,
        entry_fee_paid=fee,
        payment_verified=False,
        status=Registration.Status.PENDING_PAYMENT,
    )
    if fee > Decimal("0.00"):
        wallet.balance -= fee
        wallet.save(update_fields=["balance", "updated_at"])
        WalletTransaction.objects.create(
            wallet=wallet,
            transaction_type=WalletTransaction.TransactionType.ENTRY_FEE,
            amount=fee,
            status=WalletTransaction.Status.COMPLETED,
            reference=f"TOURNEY-ENTRY-{registration.pk}",
            description=f"Entry fee for tournament {tournament.title}; awaiting admin review",
        )
    return registration
