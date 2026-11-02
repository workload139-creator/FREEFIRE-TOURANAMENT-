"""Subscribe to BR LiveKit streams and hold kill screenshots until player elimination.

OCR is a candidate signal only. Screenshots stay in worker memory until an
elimination overlay is detected, then are submitted for Admin review. This
worker never approves kills or issues wallet credits. Clash Squad is excluded.
"""
import asyncio
import base64
import io
import logging
import os
import time
import hashlib
import json
import urllib.request
from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal

from asgiref.sync import sync_to_async
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.db.models import F
from livekit import api, rtc
from PIL import Image
import pytesseract

from apps.tournaments.live_ai_ocr import verify_profile_uid
from apps.tournaments.live_ai_killfeed import live_kill_detection_enabled, player_eliminated_from_text, scan_full_frame_for_kill_text
from apps.tournaments.models import TournamentLiveSession

logger = logging.getLogger(__name__)
OCR_SAMPLE_INTERVAL = 2.0
KILL_SCAN_INTERVAL = 1.5
KILL_TERMS = {"eliminated", "knocked", "headshot", "kill", "killed", "assist"}
MAX_PENDING_KILL_SCREENSHOTS = 49


@dataclass
class SessionWorker:
    session_uuid: str
    room_name: str
    participant_identity: str
    registration_id: int
    free_fire_uid: str
    tournament_mode: str
    room: rtc.Room
    frame_tasks: set = field(default_factory=set)
    frames_pending: int = 0
    identity_verified: bool = False
    last_ocr_at: float = 0.0
    last_kill_scan_at: float = 0.0
    last_kill_fingerprint: str = ""
    seen_kill_signatures: set = field(default_factory=set)
    pending_kill_evidence: list = field(default_factory=list)
    elimination_detected: bool = False


@sync_to_async
def active_sessions():
    return list(
        TournamentLiveSession.objects.filter(
            status=TournamentLiveSession.Status.ACTIVE,
            tournament__status="live",
            tournament__mode="BR",
            registration__status="ready",
            registration__payment_verified=True,
            registration__refund_processed=False,
        ).values(
            "session_uuid", "room_name", "participant_identity",
            "registration_id", "registration__free_fire_uid", "tournament__mode",
        )
    )


@sync_to_async
def update_monitor(session_uuid, state, frames_delta=0, detections_delta=0, error=""):
    """Update one shared-monitor status record stored on the player's live session."""
    TournamentLiveSession.objects.filter(session_uuid=session_uuid).update(
        monitor_state=state,
        monitor_last_heartbeat_at=timezone.now(),
        monitor_frames_seen=F("monitor_frames_seen") + max(0, int(frames_delta)),
        monitor_detections_seen=F("monitor_detections_seen") + max(0, int(detections_delta)),
        monitor_last_error=error[:250],
        updated_at=timezone.now(),
    )


@sync_to_async
def mark_identity_verified(session_uuid, confidence):
    now = timezone.now()
    TournamentLiveSession.objects.filter(session_uuid=session_uuid).update(
        identity_verified_at=now,
        identity_ocr_confidence=Decimal(str(round(float(confidence), 4))),
        monitor_state="processing",
        monitor_last_heartbeat_at=now,
        monitor_last_error="",
        updated_at=now,
    )


def _ocr_frame_for_uid(frame, registered_uid):
    """Convert a LiveKit frame to RGB and look for an exact UID label/value."""
    rgb = frame.convert(rtc.VideoBufferType.RGB24)
    image = Image.frombytes("RGB", (rgb.width, rgb.height), bytes(rgb.data))
    try:
        return verify_profile_uid(image, registered_uid)
    finally:
        image.close()


def _scan_live_frame(frame):
    """Return one kill screenshot candidate plus whether the player's own death is visible."""
    rgb = frame.convert(rtc.VideoBufferType.RGB24)
    image = Image.frombytes("RGB", (rgb.width, rgb.height), bytes(rgb.data))
    try:
        words = scan_full_frame_for_kill_text(image)
        text = " ".join(item["text"] for item in words)[:5000]
        eliminated = player_eliminated_from_text(text)
        relevant = [item for item in words if item["text"].lower() in KILL_TERMS]
        if eliminated or not relevant:
            return None, eliminated
        # Keep the temporary in-memory screenshot bounded; the original screen
        # share remains available to Admin in the Live Monitor.
        image.thumbnail((640, 360))
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=52, optimize=True)
        evidence_b64 = base64.b64encode(buffer.getvalue()).decode("ascii")
        return (text, min(item["confidence"] for item in relevant), evidence_b64), False
    finally:
        image.close()


def _post_kill_candidate(session_uuid, detected_text, confidence, fingerprint, evidence_image_b64):
    base = os.getenv("LIVE_AI_INGEST_URL", "").strip()
    token = os.getenv("LIVE_AI_INGEST_TOKEN", "").strip()
    if not base or not token:
        return False
    payload = json.dumps({
        "session_uuid": session_uuid,
        "event_fingerprint": fingerprint,
        "confidence": confidence,
        "detected_text": detected_text,
        "evidence_image_b64": evidence_image_b64,
    }).encode("utf-8")
    request = urllib.request.Request(
        base.rstrip("/") + "/tournaments/live/ai/kill-candidate/",
        data=payload,
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return 200 <= response.status < 300
    except Exception:
        logger.exception("Could not submit kill candidate for session %s", session_uuid)
        return False


class LiveAIWorker:
    def __init__(self, poll_seconds=5):
        self.poll_seconds = max(2, poll_seconds)
        self.url = os.getenv("LIVEKIT_URL", "").strip()
        self.key = os.getenv("LIVEKIT_API_KEY", "").strip()
        self.secret = os.getenv("LIVEKIT_API_SECRET", "").strip()
        self.workers = {}

    def _token(self, session):
        identity = f"ffarena-ai-{str(session['session_uuid']).replace('-', '')[:20]}"
        return (
            api.AccessToken(self.key, self.secret)
            .with_identity(identity)
            .with_name("FF Arena Live AI")
            .with_ttl(timedelta(minutes=10))
            .with_grants(api.VideoGrants(
                room_join=True,
                room=session["room_name"],
                can_publish=False,
                can_subscribe=True,
            ))
            .to_jwt()
        )

    async def _read_video(self, worker, track, participant):
        if participant.identity != worker.participant_identity or track.kind != rtc.TrackKind.KIND_VIDEO:
            return
        stream = rtc.VideoStream(track)
        try:
            async for frame_event in stream:
                frame = frame_event.frame
                if frame is None:
                    continue
                worker.frames_pending += 1
                now = time.monotonic()
                try:
                    if not worker.identity_verified and now - worker.last_ocr_at >= OCR_SAMPLE_INTERVAL:
                        worker.last_ocr_at = now
                        verified, confidence = await asyncio.to_thread(
                            _ocr_frame_for_uid, frame, worker.free_fire_uid
                        )
                        if verified:
                            worker.identity_verified = True
                            await mark_identity_verified(worker.session_uuid, confidence)
                            logger.info("Registered UID verified for session=%s registration=%s", worker.session_uuid, worker.registration_id)
                    if live_kill_detection_enabled(worker.tournament_mode) and worker.identity_verified and not worker.elimination_detected and now - worker.last_kill_scan_at >= KILL_SCAN_INTERVAL:
                        worker.last_kill_scan_at = now
                        candidate, player_eliminated = await asyncio.to_thread(_scan_live_frame, frame)
                        if candidate:
                            detected_text, confidence, evidence_image_b64 = candidate
                            normalized_text = " ".join(detected_text.casefold().split())
                            signature = hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()
                            if signature not in worker.seen_kill_signatures:
                                worker.seen_kill_signatures.add(signature)
                                worker.last_kill_fingerprint = signature
                                worker.pending_kill_evidence.append({
                                    "text": detected_text,
                                    "confidence": confidence,
                                    "image": evidence_image_b64,
                                    "signature": signature,
                                })
                                if len(worker.pending_kill_evidence) > MAX_PENDING_KILL_SCREENSHOTS:
                                    worker.pending_kill_evidence.pop(0)
                                await update_monitor(worker.session_uuid, "processing", detections_delta=1)

                        if player_eliminated:
                            # Only now send the temporarily buffered kill screenshots
                            # to the private ingestion endpoint for permanent evidence storage.
                            while worker.pending_kill_evidence:
                                item = worker.pending_kill_evidence[0]
                                fingerprint = hashlib.sha256(
                                    f"{worker.session_uuid}|{item['signature']}".encode("utf-8")
                                ).hexdigest()
                                accepted = await asyncio.to_thread(
                                    _post_kill_candidate, worker.session_uuid, item["text"],
                                    item["confidence"], fingerprint, item["image"]
                                )
                                if not accepted:
                                    break
                                worker.pending_kill_evidence.pop(0)
                            if not worker.pending_kill_evidence:
                                worker.elimination_detected = True
                                await update_monitor(worker.session_uuid, "eliminated")
                except Exception:
                    logger.exception("Live AI frame analysis failed for session %s", worker.session_uuid)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Video stream read failed for session %s", worker.session_uuid)
        finally:
            await stream.aclose()

    async def _connect(self, session):
        session_uuid = str(session["session_uuid"])
        room = rtc.Room()
        worker = SessionWorker(
            session_uuid=session_uuid,
            room_name=session["room_name"],
            participant_identity=session["participant_identity"],
            registration_id=session["registration_id"],
            free_fire_uid=str(session["registration__free_fire_uid"] or ""),
            tournament_mode=str(session["tournament__mode"] or ""),
            room=room,
        )

        @room.on("track_subscribed")
        def on_track_subscribed(track, publication, participant):
            if participant.identity != worker.participant_identity:
                return
            if track.kind != rtc.TrackKind.KIND_VIDEO:
                return
            task = asyncio.create_task(self._read_video(worker, track, participant))
            worker.frame_tasks.add(task)
            task.add_done_callback(worker.frame_tasks.discard)

        await room.connect(self.url, self._token(session))
        self.workers[session_uuid] = worker
        await update_monitor(session_uuid, "connected")
        logger.info("Live AI subscriber connected: session=%s room=%s", session_uuid, worker.room_name)

    async def _disconnect(self, session_uuid, error=""):
        worker = self.workers.pop(session_uuid, None)
        if worker:
            for task in tuple(worker.frame_tasks):
                task.cancel()
            if worker.frame_tasks:
                await asyncio.gather(*worker.frame_tasks, return_exceptions=True)
            try:
                await worker.room.disconnect()
            except Exception:
                logger.exception("Room disconnect failed for session %s", session_uuid)
        await update_monitor(
            session_uuid,
            "degraded" if error else "stopped",
            error=error,
        )

    async def run(self):
        try:
            while True:
                sessions = await active_sessions()
                current = {str(row["session_uuid"]): row for row in sessions}

                for session_uuid in set(self.workers) - set(current):
                    await self._disconnect(session_uuid)

                for session_uuid, session in current.items():
                    if session_uuid in self.workers:
                        continue
                    try:
                        await self._connect(session)
                    except Exception as exc:
                        logger.exception("Could not subscribe to LiveKit session %s", session_uuid)
                        await update_monitor(
                            session_uuid,
                            "degraded",
                            error=f"LiveKit subscriber error: {exc}",
                        )

                for session_uuid, worker in tuple(self.workers.items()):
                    delta = worker.frames_pending
                    worker.frames_pending = 0
                    await update_monitor(
                        session_uuid,
                        "processing" if worker.identity_verified else "connected",
                        frames_delta=delta,
                    )

                await asyncio.sleep(self.poll_seconds)
        finally:
            for session_uuid in tuple(self.workers):
                await self._disconnect(session_uuid)


class Command(BaseCommand):
    help = "Subscribe to BR LiveKit rooms, temporarily capture kill screenshots, and save them as evidence after player elimination."

    def add_arguments(self, parser):
        parser.add_argument("--poll-seconds", type=int, default=5)

    def handle(self, *args, **options):
        url = os.getenv("LIVEKIT_URL", "").strip()
        key = os.getenv("LIVEKIT_API_KEY", "").strip()
        secret = os.getenv("LIVEKIT_API_SECRET", "").strip()
        if not (url.startswith(("wss://", "ws://")) and key and secret):
            raise CommandError("Set valid LIVEKIT_URL, LIVEKIT_API_KEY and LIVEKIT_API_SECRET.")
        try:
            pytesseract.get_tesseract_version()
        except Exception as exc:
            raise CommandError(
                "Tesseract OCR binary is missing. Run this command in the dedicated OCR worker image."
            ) from exc
        self.stdout.write(self.style.SUCCESS(
            "Starting BR-only LiveKit worker: UID verification and temporary kill screenshots; evidence is saved only after elimination and requires Admin review."
        ))
        try:
            asyncio.run(LiveAIWorker(options["poll_seconds"]).run())
        except KeyboardInterrupt:
            self.stdout.write("Live AI worker stopped.")
