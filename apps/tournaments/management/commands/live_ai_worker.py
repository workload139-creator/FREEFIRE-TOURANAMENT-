"""Subscribe to BR/VS LiveKit streams, verify UID and submit kill candidates for Admin review.

OCR is a candidate signal only. This worker never approves kills or issues wallet credits.
"""
import asyncio
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
from django.db.models import F
from django.utils import timezone
from livekit import api, rtc
from PIL import Image
import pytesseract

from apps.tournaments.live_ai_models import LiveAIAgentSlot
from apps.tournaments.live_ai_ocr import verify_profile_uid
from apps.tournaments.live_ai_killfeed import live_kill_detection_enabled, scan_full_frame_for_kill_text
from apps.tournaments.models import TournamentLiveSession

logger = logging.getLogger(__name__)
OCR_SAMPLE_INTERVAL = 2.0
KILL_SCAN_INTERVAL = 1.5
KILL_TERMS = {"eliminated", "knocked", "headshot", "kill", "killed", "assist"}


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


@sync_to_async
def active_sessions():
    return list(
        TournamentLiveSession.objects.filter(
            status=TournamentLiveSession.Status.ACTIVE,
            tournament__status="live",
            tournament__mode__in=("BR", "VS"),
            registration__status="ready",
            registration__payment_verified=True,
            registration__refund_processed=False,
        ).values(
            "session_uuid", "room_name", "participant_identity",
            "registration_id", "registration__free_fire_uid", "tournament__mode",
        )
    )


@sync_to_async
def update_slots(session_uuid, state, frames_delta=0, detections_delta=0, error=""):
    """Update only the Live Kill AI slot; Payment AI has its own worker lifecycle."""
    LiveAIAgentSlot.objects.filter(
        session__session_uuid=session_uuid,
        kind=LiveAIAgentSlot.Kind.LIVE,
    ).update(
        state=state,
        last_heartbeat_at=timezone.now(),
        frames_seen=F("frames_seen") + max(0, int(frames_delta)),
        detections_seen=F("detections_seen") + max(0, int(detections_delta)),
        last_error=error[:250],
        updated_at=timezone.now(),
    )


@sync_to_async
def mark_identity_verified(session_uuid, confidence):
    """Identity evidence belongs to the Live slot, never the Payment slot."""
    now = timezone.now()
    LiveAIAgentSlot.objects.filter(
        session__session_uuid=session_uuid,
        kind=LiveAIAgentSlot.Kind.LIVE,
    ).update(
        identity_verified_at=now,
        identity_ocr_confidence=Decimal(str(round(float(confidence), 4))),
        state=LiveAIAgentSlot.State.PROCESSING,
        last_heartbeat_at=now,
        last_error="",
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


def _scan_kill_candidate(frame):
    rgb = frame.convert(rtc.VideoBufferType.RGB24)
    image = Image.frombytes("RGB", (rgb.width, rgb.height), bytes(rgb.data))
    try:
        words = scan_full_frame_for_kill_text(image)
        relevant = [item for item in words if item["text"].lower() in KILL_TERMS]
        if not relevant:
            return None
        text = " ".join(item["text"] for item in words)[:5000]
        return text, min(item["confidence"] for item in relevant)
    finally:
        image.close()


def _post_kill_candidate(session_uuid, detected_text, confidence, fingerprint):
    base = os.getenv("LIVE_AI_INGEST_URL", "").strip()
    token = os.getenv("LIVE_AI_INGEST_TOKEN", "").strip()
    if not base or not token:
        return False
    payload = json.dumps({
        "session_uuid": session_uuid,
        "event_fingerprint": fingerprint,
        "confidence": confidence,
        "detected_text": detected_text,
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
                    if live_kill_detection_enabled(worker.tournament_mode) and worker.identity_verified and now - worker.last_kill_scan_at >= KILL_SCAN_INTERVAL:
                        worker.last_kill_scan_at = now
                        candidate = await asyncio.to_thread(_scan_kill_candidate, frame)
                        if candidate:
                            detected_text, confidence = candidate
                            # Stable fingerprint: do not include a time bucket. A persistent
                            # killfeed notification can remain on screen across many OCR scans;
                            # time-bucket fingerprints would turn that one notification into
                            # repeated reward candidates every few seconds. The DB unique
                            # constraint then deduplicates this event across worker restarts.
                            normalized_text = " ".join(detected_text.casefold().split())
                            fingerprint = hashlib.sha256(
                                f"{worker.session_uuid}|{normalized_text}".encode("utf-8")
                            ).hexdigest()
                            if fingerprint != worker.last_kill_fingerprint:
                                accepted = await asyncio.to_thread(
                                    _post_kill_candidate, worker.session_uuid, detected_text, confidence, fingerprint
                                )
                                if accepted:
                                    worker.last_kill_fingerprint = fingerprint
                                    await update_slots(worker.session_uuid, LiveAIAgentSlot.State.PROCESSING, detections_delta=1)
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
        await update_slots(session_uuid, LiveAIAgentSlot.State.CONNECTED)
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
        await update_slots(
            session_uuid,
            LiveAIAgentSlot.State.DEGRADED if error else LiveAIAgentSlot.State.STOPPED,
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
                        await update_slots(
                            session_uuid,
                            LiveAIAgentSlot.State.DEGRADED,
                            error=f"LiveKit subscriber error: {exc}",
                        )

                for session_uuid, worker in tuple(self.workers.items()):
                    delta = worker.frames_pending
                    worker.frames_pending = 0
                    await update_slots(
                        session_uuid,
                        LiveAIAgentSlot.State.PROCESSING if worker.identity_verified else LiveAIAgentSlot.State.CONNECTED,
                        frames_delta=delta,
                    )

                await asyncio.sleep(self.poll_seconds)
        finally:
            for session_uuid in tuple(self.workers):
                await self._disconnect(session_uuid)


class Command(BaseCommand):
    help = "Subscribe to active FF Arena LiveKit rooms, verify UID, and submit BR/VS kill candidates for Admin review."

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
            "Starting LiveKit worker: UID verification plus BR/VS full-frame kill candidates; rewards require Admin review."
        ))
        try:
            asyncio.run(LiveAIWorker(options["poll_seconds"]).run())
        except KeyboardInterrupt:
            self.stdout.write("Live AI worker stopped.")
