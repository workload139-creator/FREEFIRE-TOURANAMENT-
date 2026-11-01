"""Subscribe to player streams and verify the registered Free Fire UID via OCR.

This stage verifies identity only. It does not read/attribute killfeed entries or
issue wallet credits. No frames or OCR text are persisted.
"""
import asyncio
import logging
import os
import time
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
from apps.tournaments.models import TournamentLiveSession

logger = logging.getLogger(__name__)
OCR_SAMPLE_INTERVAL = 2.0


@dataclass
class SessionWorker:
    session_uuid: str
    room_name: str
    participant_identity: str
    registration_id: int
    free_fire_uid: str
    room: rtc.Room
    frame_tasks: set = field(default_factory=set)
    frames_pending: int = 0
    identity_verified: bool = False
    last_ocr_at: float = 0.0


@sync_to_async
def active_sessions():
    return list(
        TournamentLiveSession.objects.filter(
            status=TournamentLiveSession.Status.ACTIVE,
            tournament__status="live",
            registration__status="ready",
            registration__payment_verified=True,
            registration__refund_processed=False,
        ).values(
            "session_uuid", "room_name", "participant_identity",
            "registration_id", "registration__free_fire_uid",
        )
    )


@sync_to_async
def update_slots(session_uuid, state, frames_delta=0, error=""):
    LiveAIAgentSlot.objects.filter(session__session_uuid=session_uuid).update(
        state=state,
        last_heartbeat_at=timezone.now(),
        frames_seen=F("frames_seen") + max(0, int(frames_delta)),
        last_error=error[:250],
        updated_at=timezone.now(),
    )


@sync_to_async
def mark_identity_verified(session_uuid, confidence):
    now = timezone.now()
    LiveAIAgentSlot.objects.filter(session__session_uuid=session_uuid).update(
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
                if worker.identity_verified or now - worker.last_ocr_at < OCR_SAMPLE_INTERVAL:
                    continue
                worker.last_ocr_at = now
                try:
                    verified, confidence = await asyncio.to_thread(
                        _ocr_frame_for_uid, frame, worker.free_fire_uid
                    )
                    if verified:
                        worker.identity_verified = True
                        await mark_identity_verified(worker.session_uuid, confidence)
                        logger.info(
                            "Registered UID verified for session=%s registration=%s",
                            worker.session_uuid,
                            worker.registration_id,
                        )
                except Exception:
                    # Missing Tesseract or an OCR error must never count as identity proof.
                    logger.exception("UID OCR failed for session %s", worker.session_uuid)
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
    help = "Subscribe to active FF Arena LiveKit rooms and verify registered UID via OCR."

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
            "Starting LiveKit UID verification worker. Killfeed recognition and rewards remain disabled."
        ))
        try:
            asyncio.run(LiveAIWorker(options["poll_seconds"]).run())
        except KeyboardInterrupt:
            self.stdout.write("Live AI worker stopped.")
