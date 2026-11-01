"""Private ingestion endpoint for the separate LiveKit vision worker."""
import base64
import binascii
import hmac
import json
import os
import re
from datetime import datetime

from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.core.files.base import ContentFile
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .models import LiveKillEvent, TournamentLiveSession
from .live_ai_models import LiveAIPaymentAssessment
from .management.commands.live_ai_payment_worker import build_payment_assessment


@csrf_exempt
@require_POST
def ingest_live_kill_candidate(request):
    """Accept an OCR candidate from the private worker; never pays a reward."""
    expected = os.getenv("LIVE_AI_INGEST_TOKEN", "").strip()
    supplied = request.headers.get("Authorization", "")
    if not expected or not supplied.startswith("Bearer ") or not hmac.compare_digest(supplied[7:].strip(), expected):
        return JsonResponse({"error": "Unauthorized worker."}, status=401)
    if len(request.body) > 3_000_000:
        return JsonResponse({"error": "Payload too large."}, status=413)
    try:
        payload = json.loads(request.body.decode("utf-8"))
        session_uuid = str(payload.get("session_uuid", ""))
        fingerprint = str(payload.get("event_fingerprint", "")).lower()
        confidence = float(payload.get("confidence", 0))
        detected_text = str(payload.get("detected_text", ""))[:5000]
        evidence_image_b64 = str(payload.get("evidence_image_b64", ""))
        match_id = str(payload.get("match_id", ""))[:100]
        attributed_player_name = str(payload.get("attributed_player_name", "")).strip()[:80]
        kill_at_raw = payload.get("kill_at")
    except (ValueError, TypeError, UnicodeDecodeError):
        return JsonResponse({"error": "Invalid JSON payload."}, status=400)
    if not re.fullmatch(r"[0-9a-f]{64}", fingerprint) or not 0 <= confidence <= 1:
        return JsonResponse({"error": "Invalid fingerprint or confidence."}, status=400)
    try:
        session = TournamentLiveSession.objects.select_related("tournament", "registration").get(
            session_uuid=session_uuid,
            status=TournamentLiveSession.Status.ACTIVE,
            tournament__status="live",
            registration__status="ready",
            registration__payment_verified=True,
            registration__refund_processed=False,
        )
    except (TournamentLiveSession.DoesNotExist, ValueError):
        return JsonResponse({"error": "No eligible active player session found."}, status=404)
    kill_at = None
    if kill_at_raw:
        try:
            kill_at = datetime.fromisoformat(str(kill_at_raw).replace("Z", "+00:00"))
            if timezone.is_naive(kill_at):
                kill_at = timezone.make_aware(kill_at, timezone.get_current_timezone())
        except ValueError:
            return JsonResponse({"error": "Invalid kill timestamp."}, status=400)
    if len(evidence_image_b64) > 2_800_000:
        return JsonResponse({"error": "Evidence image is too large."}, status=413)
    try:
        evidence_bytes = base64.b64decode(evidence_image_b64, validate=True) if evidence_image_b64 else b""
    except (ValueError, binascii.Error):
        return JsonResponse({"error": "Invalid evidence image."}, status=400)
    if evidence_bytes and not evidence_bytes.startswith(b"\xff\xd8\xff"):
        return JsonResponse({"error": "Evidence must be a JPEG screenshot."}, status=400)
    event, created = LiveKillEvent.objects.get_or_create(
        event_fingerprint=fingerprint,
        defaults={
            "tournament": session.tournament,
            "registration": session.registration,
            "session": session,
            "match_id": match_id,
            "attributed_player_name": attributed_player_name,
            "kill_at": kill_at,
            "detected_text": detected_text,
            "confidence": confidence,
            "status": LiveKillEvent.Status.REVIEW,
            "review_reason": "Worker OCR candidate; independent validation and Admin approval required.",
        },
    )
    evidence_saved = False
    if evidence_bytes and not event.evidence_image:
        event.evidence_image.save(f"{event.event_uuid}.jpg", ContentFile(evidence_bytes), save=True)
        evidence_saved = True

    # Assess immediately when a candidate arrives. The periodic Payment AI worker
    # remains a retry/fallback, but the admin queue no longer stays blank simply
    # because a separate Render worker is not running.
    assessment = LiveAIPaymentAssessment.objects.filter(event=event).first()
    if assessment is None:
        try:
            prior_count = LiveAIPaymentAssessment.objects.filter(
                event__registration=event.registration,
                event__tournament=event.tournament,
                event__status=LiveKillEvent.Status.VERIFIED,
                eligible=True,
            ).count()
            with transaction.atomic():
                assessment, _ = LiveAIPaymentAssessment.objects.get_or_create(
                    event=event,
                    defaults=build_payment_assessment(event, prior_count),
                )
        except Exception:
            # Candidate evidence must remain safely queued even if assessment fails.
            import logging
            logging.getLogger(__name__).exception(
                "Synchronous AI assessment failed for live kill event %s", event.pk
            )

    return JsonResponse({
        "success": True,
        "created": created,
        "event_uuid": str(event.event_uuid),
        "status": event.status,
        "assessment_ready": bool(assessment),
        "assessment_reason": assessment.decision_reason if assessment else "Assessment queued for retry.",
        "evidence_saved": evidence_saved,
        "reward_paid": False,
        "message": "Candidate saved once. No wallet credit was issued.",
    }, status=201 if created else 200)



@login_required
@require_POST
def admin_approve_live_kill(request, event_id):
    """Admin confirms one candidate after supplying match attribution; payout remains idempotent."""
    if not request.user.is_staff:
        return JsonResponse({"error": "Staff access required."}, status=403)
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
        match_id = str(payload.get("match_id", "")).strip()[:100]
        killer_name = str(payload.get("attributed_player_name", "")).strip()[:80]
        kill_at_raw = str(payload.get("kill_at", "")).strip()
        if not match_id or not killer_name or not kill_at_raw:
            return JsonResponse({"error": "Match ID, kill time and in-game killer name are required."}, status=400)
        kill_at = datetime.fromisoformat(kill_at_raw.replace("Z", "+00:00"))
        if timezone.is_naive(kill_at):
            kill_at = timezone.make_aware(kill_at, timezone.get_current_timezone())
    except (ValueError, TypeError, UnicodeDecodeError, json.JSONDecodeError):
        return JsonResponse({"error": "Invalid approval details. Use a valid date/time."}, status=400)

    from .live_ai_rewards import approve_live_kill_event
    with transaction.atomic():
        event = LiveKillEvent.objects.select_for_update().get(pk=event_id)
        if event.status != LiveKillEvent.Status.REVIEW:
            return JsonResponse({"error": "This kill is no longer awaiting Admin review."}, status=409)
        event.match_id = match_id
        event.kill_at = kill_at
        event.attributed_player_name = killer_name
        event.save(update_fields=("match_id", "kill_at", "attributed_player_name"))
        ok, message = approve_live_kill_event(event.pk, request.user)
        if not ok:
            return JsonResponse({"error": message}, status=409)
    return JsonResponse({"success": True, "message": message, "event_id": event_id})
