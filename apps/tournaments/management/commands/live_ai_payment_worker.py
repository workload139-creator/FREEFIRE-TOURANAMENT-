"""Independent Payment & Reward AI worker.

Assesses Live Kill AI candidates and writes advisory proposals only.
It never verifies kills or credits player wallets; Admin approval is mandatory.
"""
import asyncio
import logging
import time
from decimal import Decimal

from asgiref.sync import sync_to_async
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.tournaments.kill_services import rewards_for_tournament
from apps.tournaments.live_ai_models import (
    LiveAIAgentSlot,
    LiveAIPaymentAssessment,
    LiveKillEvent,
)
from apps.tournaments.models import TournamentLiveSession

logger = logging.getLogger(__name__)
POLL_SECONDS = 5
MIN_KILLS_FOR_REWARD = 2
MIN_CONFIDENCE = Decimal("0.7500")


def build_payment_assessment(event, live_slot, prior_count=0):
    """Pure eligibility/rules function; deliberately has no wallet dependency."""
    registration = event.registration
    player = registration.player
    checks = {
        "session_active": event.session.status == TournamentLiveSession.Status.ACTIVE,
        "tournament_live": event.tournament.status == "live",
        "supported_mode": event.tournament.mode in ("BR", "VS"),
        "registration_ready": registration.status == "ready",
        "payment_verified": bool(registration.payment_verified),
        "not_refunded": not registration.refund_processed and registration.status != "refunded",
        "live_identity_verified": bool(live_slot and live_slot.identity_verified_at),
        "registered_uid_matches_account": str(registration.free_fire_uid or "").strip()
            == str(getattr(player, "free_fire_uid", "") or "").strip(),
        "account_uid_verified": bool(getattr(player, "uid_verified", False)),
        "confidence_pass": Decimal(str(event.confidence or 0)) >= MIN_CONFIDENCE,
        "candidate_text_present": bool((event.detected_text or "").strip()),
        "session_registration_matches": event.session.registration_id == registration.pk,
        "no_reward_already_issued": not bool(event.reward_reference),
    }
    eligible = all(checks.values())
    proposed_kills = int(prior_count) + (1 if eligible else 0)
    rewards = []
    failed = [name for name, passed in checks.items() if not passed]
    reason = "Held for Admin review: " + ", ".join(failed)
    if eligible and proposed_kills >= MIN_KILLS_FOR_REWARD:
        rewards = [
            {"currency": currency, "quantity": quantity, "label": label}
            for currency, quantity, label in rewards_for_tournament(event.tournament, proposed_kills)
            if quantity > 0
        ]
        reason = "Automated checks passed; proposed reward only. Admin must verify kills before credit."
    elif eligible:
        reason = f"Candidate passed checks; {MIN_KILLS_FOR_REWARD - proposed_kills} more candidate kill(s) needed."
    return {
        "eligible": eligible,
        "proposed_kills": proposed_kills if eligible else 0,
        "proposed_rewards": rewards,
        "checks": checks,
        "decision_reason": reason[:250],
        "worker_version": "payment-ai-v1",
    }


@sync_to_async
def assess_pending_events(batch_size=100):
    """Lock and assess new events once, leaving their review and payout state untouched."""
    assessed = 0
    with transaction.atomic():
        events = list(
            LiveKillEvent.objects.select_for_update(skip_locked=True)
            .select_related("tournament", "registration__player", "session")
            .filter(status=LiveKillEvent.Status.REVIEW, payment_assessment__isnull=True)
            .order_by("detected_at")[:batch_size]
        )
        for event in events:
            live_slot = LiveAIAgentSlot.objects.filter(
                session=event.session, kind=LiveAIAgentSlot.Kind.LIVE
            ).first()
            prior_count = LiveAIPaymentAssessment.objects.filter(
                event__registration=event.registration, eligible=True
            ).count()
            LiveAIPaymentAssessment.objects.create(
                event=event,
                **build_payment_assessment(event, live_slot, prior_count),
            )
            LiveAIAgentSlot.objects.filter(
                session=event.session, kind=LiveAIAgentSlot.Kind.PAYMENT
            ).update(
                state=LiveAIAgentSlot.State.PROCESSING,
                last_heartbeat_at=timezone.now(),
                detections_seen=F("detections_seen") + 1,
                last_error="",
                updated_at=timezone.now(),
            )
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
    active_slots.exclude(state=LiveAIAgentSlot.State.PROCESSING).update(
        state=LiveAIAgentSlot.State.CONNECTED,
        last_heartbeat_at=now,
        last_error="",
        updated_at=now,
    )


class PaymentAIWorker:
    def __init__(self, poll_seconds=POLL_SECONDS):
        self.poll_seconds = max(2, int(poll_seconds))

    async def run(self, once=False):
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
            if once:
                return
            await asyncio.sleep(self.poll_seconds)


class Command(BaseCommand):
    help = "Run the independent Payment & Reward AI assessment worker."

    def add_arguments(self, parser):
        parser.add_argument("--poll-seconds", type=int, default=POLL_SECONDS)
        parser.add_argument("--once", action="store_true")

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS(
            "Starting Payment AI: eligibility checks and reward proposals only; no automatic wallet credit."
        ))
        try:
            asyncio.run(PaymentAIWorker(options["poll_seconds"]).run(once=options["once"]))
        except KeyboardInterrupt:
            self.stdout.write("Payment AI worker stopped.")
