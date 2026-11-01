"""Independent Payment & Reward AI worker for 50 per-player slots.

It validates candidate eligibility, computes advisory reward proposals and records
an auditable assessment. It NEVER credits a wallet; Admin approval is mandatory.
"""
import asyncio
import logging
import os
from decimal import Decimal

from asgiref.sync import sync_to_async
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.social.models import PlayerShopWallet, PlayerShopWalletTransaction
from apps.tournaments.kill_services import rewards_for_tournament
from apps.tournaments.live_ai_models import LiveAIAgentSlot, LiveAIPaymentAssessment, LiveKillEvent
from apps.tournaments.models import TournamentLiveSession

logger = logging.getLogger(__name__)
POLL_SECONDS = 5
MIN_KILLS_FOR_REWARD = 2


def build_payment_assessment(event, live_slot, prior_count=0):
    """Pure validation/rules function, intentionally incapable of wallet writes."""
    checks = {
        "tournament_live": event.tournament.status == "live",
        "supported_mode": event.tournament.mode in ("BR", "VS"),
        "registration_ready": event.registration.status == "ready",
        "payment_verified": bool(event.registration.payment_verified),
        "not_refunded": not bool(event.registration.refund_processed),
        "live_ai_uid_verified": bool(live_slot and live_slot.identity_verified_at),
        "ocr_confidence_pass": Decimal(str(event.confidence)) >= Decimal("0.60"),
        "candidate_text_present": bool((event.detected_text or "").strip()),
        "event_session_matches": event.session.registration_id == event.registration_id,
    }
    eligible = all(checks.values())
    proposed_kills = int(prior_count) + (1 if eligible else 0)
    rewards = []
    reason = "Held: " + ", ".join(key for key, passed in checks.items() if not passed)
    if eligible and proposed_kills >= MIN_KILLS_FOR_REWARD:
        rewards = [
            {"currency": currency, "quantity": quantity, "label": label}
            for currency, quantity, label in rewards_for_tournament(event.tournament, proposed_kills)
        ]
        reason = "Payment AI checks passed; proposed reward awaits Admin verification."
    elif eligible:
        reason = f"Candidate passed checks; {MIN_KILLS_FOR_REWARD - proposed_kills} more verified kill(s) needed before reward proposal."
    return {
        "eligible": eligible,
        "proposed_kills": proposed_kills if eligible else 0,
        "proposed_rewards": rewards,
        "checks": checks,
        "decision_reason": reason[:250],
    }


@sync_to_async
def assess_pending_events(batch_size=100):
    """Assess unreviewed candidate events exactly once; no wallet writes occur."""
    assessed = 0
    with transaction.atomic():
        events = list(
            LiveKillEvent.objects.select_for_update(skip_locked=True)
            .select_related("tournament", "registration", "session")
            .filter(status=LiveKillEvent.Status.REVIEW, payment_assessment__isnull=True)
            .order_by("detected_at")[:batch_size]
        )
        for event in events:
            live_slot = LiveAIAgentSlot.objects.filter(
                session=event.session,
                kind=LiveAIAgentSlot.Kind.LIVE,
            ).first()
            result = build_payment_assessment(
                event,
                live_slot,
                prior_count=LiveAIPaymentAssessment.objects.filter(
                    event__registration=event.registration,
                    eligible=True,
                ).count(),
            )
            LiveAIPaymentAssessment.objects.create(event=event, **result)
            assessed += 1
    return assessed

@sync_to_async
def heartbeat_payment_slots():
    now = timezone.now()
    active_slots = LiveAIAgentSlot.objects.filter(
        kind=LiveAIAgentSlot.Kind.PAYMENT,
        session__status=TournamentLiveSession.Status.ACTIVE,
        tournament__status="live",
        registration__status="ready",
        registration__payment_verified=True,
        registration__refund_processed=False,
    )
    pending = LiveKillEvent.objects.filter(
        session__in=active_slots.values("session_id"),
        status=LiveKillEvent.Status.REVIEW,
        payment_assessment__isnull=True,
    ).values("session_id")
    pending_ids = list(pending.values_list("session_id", flat=True).distinct())
    active_slots.exclude(session_id__in=pending_ids).update(
        state=LiveAIAgentSlot.State.CONNECTED,
        last_heartbeat_at=now,
        last_error="",
        updated_at=now,
    )
    active_slots.filter(session_id__in=pending_ids).update(
        state=LiveAIAgentSlot.State.PROCESSING,
        last_heartbeat_at=now,
        last_error="",
        updated_at=now,
    )


class PaymentAIWorker:
    def __init__(self, poll_seconds=POLL_SECONDS):
        self.poll_seconds = max(2, int(poll_seconds))

    async def run(self):
        logger.info("Payment AI worker started; wallet credit is disabled pending Admin approval.")
        while True:
            try:
                count = await assess_pending_events()
                await heartbeat_payment_slots()
                if count:
                    logger.info("Payment AI assessed %s new candidate event(s).", count)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Payment AI worker cycle failed.")
            await asyncio.sleep(self.poll_seconds)


class Command(BaseCommand):
    help = "Run the independent Payment & Reward AI assessment worker."

    def add_arguments(self, parser):
        parser.add_argument("--poll-seconds", type=int, default=POLL_SECONDS)

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS(
            "Starting Payment AI: eligibility checks and reward proposals only; no automatic wallet credit."
        ))
        try:
            asyncio.run(PaymentAIWorker(options["poll_seconds"]).run())
        except KeyboardInterrupt:
            self.stdout.write("Payment AI worker stopped.")
