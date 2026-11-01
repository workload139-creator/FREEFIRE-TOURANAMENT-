"""Admin-triggered, idempotent live-kill reward settlement."""
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.social.models import PlayerShopWallet, PlayerShopWalletTransaction
from .kill_services import rewards_for_tournament
from .live_ai_models import LiveKillEvent
from .models import Registration, TournamentLedgerEntry


@transaction.atomic
def approve_live_kill_event(event_id, admin_user):
    """Approve one event and credit internal currency exactly once.

    This is an explicit Admin action, never called by either AI worker.
    """
    event = (
        LiveKillEvent.objects.select_for_update()
        .select_related("tournament", "registration__player", "session")
        .get(pk=event_id)
    )
    if event.status != LiveKillEvent.Status.REVIEW:
        return False, "This event is no longer awaiting review."
    if event.reward_reference:
        return False, "A reward reference already exists; duplicate credit blocked."

    registration = Registration.objects.select_for_update().get(pk=event.registration_id)
    assessment = getattr(event, "payment_assessment", None)
    player = registration.player
    if not assessment or not assessment.eligible:
        return False, "Payment AI has not marked this event eligible."
    if (
        event.tournament.status != "live"
        or event.session.status != "active"
        or registration.status != Registration.Status.READY
        or not registration.payment_verified
        or registration.refund_processed
        or registration.free_fire_uid != getattr(player, "free_fire_uid", "")
        or not getattr(player, "uid_verified", False)
    ):
        return False, "Player/session eligibility changed; reward held."
    if not event.match_id or not event.kill_at:
        return False, "Match ID and kill timestamp are required before approval."

    already_verified = LiveKillEvent.objects.filter(
        tournament=event.tournament,
        registration=registration,
        status=LiveKillEvent.Status.VERIFIED,
    ).count()
    if already_verified < 1:
        return False, "At least two distinct kills must be reviewed; approve the first only after reviewing a second candidate."

    reward_rows = rewards_for_tournament(event.tournament, 1)
    if not reward_rows:
        return False, "No reward is configured for this tournament."
    wallet, _ = PlayerShopWallet.objects.select_for_update().get_or_create(user=player)
    reference = f"livekill:{event.event_uuid}"
    for currency, quantity, label in reward_rows:
        if int(quantity) <= 0:
            continue
        key = f"live-kill:{event.event_uuid}:{currency}"
        if PlayerShopWalletTransaction.objects.filter(idempotency_key=key).exists():
            return False, "A matching wallet transaction already exists; duplicate credit blocked."
        balance = int(getattr(wallet, currency))
        new_balance = balance + int(quantity)
        setattr(wallet, currency, new_balance)
        PlayerShopWalletTransaction.objects.create(
            user=player,
            wallet=wallet,
            currency=currency,
            direction=PlayerShopWalletTransaction.Direction.CREDIT,
            quantity=int(quantity),
            balance_after=new_balance,
            source="live_kill_ai",
            reference=reference,
            idempotency_key=key,
            description=f"Admin-approved live kill reward: {event.tournament.title}",
        )
        TournamentLedgerEntry.objects.create(
            tournament=event.tournament,
            player=player,
            registration=registration,
            entry_type=TournamentLedgerEntry.EntryType.REWARD,
            currency=currency,
            quantity=int(quantity),
            status=TournamentLedgerEntry.Status.COMPLETED,
            reference=reference,
            description=f"Admin-approved live kill · {label}",
        )
    wallet.save(update_fields=("diamonds", "coins", "fan_tokens", "updated_at"))
    event.status = LiveKillEvent.Status.VERIFIED
    event.reviewed_at = timezone.now()
    event.reviewed_by = admin_user
    event.reward_reference = reference
    event.reward_payload = {
        "rewards": [
            {"currency": currency, "quantity": int(quantity)}
            for currency, quantity, _ in reward_rows if int(quantity) > 0
        ],
        "approved_by": str(admin_user.pk),
    }
    event.review_reason = "Manually approved by Admin; idempotent wallet and ledger records created."
    event.save(update_fields=(
        "status", "reviewed_at", "reviewed_by", "reward_reference",
        "reward_payload", "review_reason",
    ))
    return True, "Approved and credited once."
