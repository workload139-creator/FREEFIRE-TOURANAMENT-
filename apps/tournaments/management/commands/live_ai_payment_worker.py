"""Single advisory AI Assessment worker.

Assesses Live Kill AI candidates and writes advisory proposals only.
It never verifies kills or credits player wallets; Admin approval is mandatory.
"""
import asyncio
import logging
from decimal import Decimal

from asgiref.sync import sync_to_async
from django.core.management.base import BaseCommand
from django.db import transaction, models
from django.utils import timezone

from apps.tournaments.kill_services import rewards_for_tournament
from apps.tournaments.live_ai_models import (
    LiveAIPaymentAssessment,
    LiveKillEvent,
)
from apps.tournaments.models import TournamentLiveSession

logger = logging.getLogger(__name__)
POLL_SECONDS = 5
MIN_KILLS_FOR_REWARD = 2
MIN_CONFIDENCE = Decimal("0.7500")


def build_payment_assessment(event, prior_count=0):
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
        "live_identity_verified": bool(
            event.session.identity_verified_at
            and event.session.lobby_nickname_verified_at
            and str(getattr(event.session, "verified_nickname", "") or "").strip()
        ),
        "registered_uid_matches_account": str(registration.free_fire_uid or "").strip()
            == str(getattr(player, "free_fire_uid", "") or "").strip(),
        "account_uid_verified": bool(getattr(player, "uid_verified", False)),
        "confidence_pass": Decimal(str(event.confidence or 0)) >= MIN_CONFIDENCE,
        "candidate_text_present": bool((event.detected_text or "").strip()),
        "session_registration_matches": event.session.registration_id == registration.pk,
        "no_reward_already_issued": not bool(getattr(event, "reward_reference", None)),
    }
    checks["kill_signal_present"] = any(word in " ".join(str(event.detected_text or "").casefold().split()).split() for word in ("eliminated", "knocked", "headshot", "kill", "killed"))
    checks["evidence_image_present"] = bool(event.evidence_image)
    checks["match_id_present"] = bool(event.match_id)
    checks["kill_time_present"] = bool(event.kill_at)
    checks["killer_name_present"] = bool(event.attributed_player_name)
    admin_completion_fields = {"match_id_present", "kill_time_present", "killer_name_present"}
    eligible = all(value for key, value in checks.items() if key not in admin_completion_fields)
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
        reason = f"Candidate passed checks; {MIN_KILLS_FOR_REWARD - proposed_kills} more Admin-verified kill(s) needed."
    return {
        "eligible": eligible,
        "proposed_kills": proposed_kills if eligible else 0,
        "proposed_rewards": rewards,
        "checks": checks,
        "decision_reason": reason[:250],
        "worker_version": "single-assessment-v2",
    }


@sync_to_async
def assess_pending_events(batch_size=25):
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
            prior_count = LiveAIPaymentAssessment.objects.filter(
                event__registration=event.registration,
                event__tournament=event.tournament,
                event__status=LiveKillEvent.Status.VERIFIED,
                eligible=True
            ).count()
            LiveAIPaymentAssessment.objects.create(
                event=event,
                **build_payment_assessment(event, prior_count),
            )
            TournamentLiveSession.objects.filter(pk=event.session_id).update(
                monitor_detections_seen=models.F("monitor_detections_seen") + 1,
                monitor_last_heartbeat_at=timezone.now(),
                updated_at=timezone.now(),
            )
            assessed += 1
    return assessed




class LiveAssessmentWorker:
    def __init__(self, poll_seconds=POLL_SECONDS):
        self.poll_seconds = max(2, int(poll_seconds))

    async def run(self, once=False):
        logger.info("Single AI Assessment worker started; wallet credit is disabled pending Admin approval.")
        while True:
            try:
                count = await assess_pending_events()
                if count:
                    logger.info("AI Assessment reviewed %s new candidate event(s).", count)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("AI Assessment worker cycle failed.")
            if once:
                return
            await asyncio.sleep(self.poll_seconds)


class Command(BaseCommand):
    help = "Run the single advisory live-kill AI assessment worker."

    def add_arguments(self, parser):
        parser.add_argument("--poll-seconds", type=int, default=POLL_SECONDS)
        parser.add_argument("--once", action="store_true")

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS(
            "Starting single AI Assessment: checks and reward proposals only; no automatic wallet credit."
        ))
        try:
            asyncio.run(LiveAssessmentWorker(options["poll_seconds"]).run(once=options["once"]))
        except KeyboardInterrupt:
            self.stdout.write("Payment AI worker stopped.")
