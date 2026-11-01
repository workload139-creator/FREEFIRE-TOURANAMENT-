"""Private ingestion endpoint for the separate LiveKit vision worker."""
import base64
import binascii
import hmac
import json
import os
import re
from datetime import datetime

from django.http import JsonResponse
from django.core.files.base import ContentFile
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .models import LiveKillEvent, TournamentLiveSession


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
    if evidence_bytes and not evidence_bytes.startswith(b"\\xff\\xd8\\xff"):
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
    if evidence_bytes and not event.evidence_image:
        event.evidence_image.save(f"{event.event_uuid}.jpg", ContentFile(evidence_bytes), save=True)
    return JsonResponse({
        "success": True,
        "created": created,
        "event_uuid": str(event.event_uuid),
        "status": event.status,
        "reward_paid": False,
        "message": "Candidate saved once. No wallet credit was issued.",
    }, status=201 if created else 200)
