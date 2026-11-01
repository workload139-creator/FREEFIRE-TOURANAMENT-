"""Subscribe to eligible tournament LiveKit streams and count decoded frames.

This worker intentionally does not infer kills or issue wallet credits. The
Killfeed OCR/validation adapter must be added and calibrated before candidates
can be emitted or any automatic rewards can be enabled.
"""
import asyncio
import logging
import os
from dataclasses import dataclass, field
from datetime import timedelta

from asgiref.sync import sync_to_async
from django.core.management.base import BaseCommand, CommandError
from django.db.models import F
from django.utils import timezone
from livekit import api, rtc

from apps.tournaments.models import LiveAIAgentSlot, TournamentLiveSession

logger = logging.getLogger(__name__)


@dataclass
class SessionWorker:
    session_uuid: str
    room_name: str
    participant_identity: str
    registration_id: int
    room: rtc.Room
    frame_tasks: set = field(default_factory=set)
    frames_pending: int = 0
    last_persisted_frames: int = 0


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
            "registration_id", "tournament_id",
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
        if participant.identity != worker.participant_identity:
            return
        if track.kind != rtc.TrackKind.KIND_VIDEO:
            return
        stream = rtc.VideoStream(track)
        try:
            async for frame_event in stream:
                # Decode is real; only counters are persisted at this stage.
                # No screenshot/video is saved and no kill is inferred here.
                if frame_event.frame is not None:
                    worker.frames_pending += 1
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
                        LiveAIAgentSlot.State.CONNECTED,
                        frames_delta=delta,
                    )

                await asyncio.sleep(self.poll_seconds)
        finally:
            for session_uuid in tuple(self.workers):
                await self._disconnect(session_uuid)


class Command(BaseCommand):
    help = "Subscribe to active FF Arena LiveKit rooms and monitor decoded video frames."

    def add_arguments(self, parser):
        parser.add_argument("--poll-seconds", type=int, default=5)

    def handle(self, *args, **options):
        url = os.getenv("LIVEKIT_URL", "").strip()
        key = os.getenv("LIVEKIT_API_KEY", "").strip()
        secret = os.getenv("LIVEKIT_API_SECRET", "").strip()
        if not (url.startswith(("wss://", "ws://")) and key and secret):
            raise CommandError("Set valid LIVEKIT_URL, LIVEKIT_API_KEY and LIVEKIT_API_SECRET.")
        self.stdout.write(self.style.SUCCESS(
            "Starting LiveKit subscriber worker. This process reads frames only; "
            "Killfeed OCR and rewards remain disabled."
        ))
        try:
            asyncio.run(LiveAIWorker(options["poll_seconds"]).run())
        except KeyboardInterrupt:
            self.stdout.write("Live AI worker stopped.")
