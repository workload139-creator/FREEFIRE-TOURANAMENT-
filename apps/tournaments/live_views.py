"""Authenticated LiveKit access for tournament screen-sharing sessions.

LiveKit room media is streamed only; this module does not enable recording or egress.
"""
import json
import logging
import os
import uuid
from datetime import timedelta

from django.contrib.auth.decorators import login_required
from asgiref.sync import async_to_sync
from django.db import IntegrityError, transaction
from django.db.models import Count, F
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from livekit import api

from .models import LiveKillEvent, Registration, Tournament, TournamentLiveMessage, TournamentLiveSession
from .kill_services import rewards_for_tournament

logger = logging.getLogger(__name__)



def _livekit_config():
    url = os.getenv("LIVEKIT_URL", "").strip()
    key = os.getenv("LIVEKIT_API_KEY", "").strip()
    secret = os.getenv("LIVEKIT_API_SECRET", "").strip()
    if not (url and key and secret):
        return None, None, None
    if not url.startswith(("wss://", "ws://")):
        return None, None, None
    return url, key, secret


@login_required
@require_POST
def tournament_live_token(request, registration_id):
    """Issue a short-lived publisher token to the registration's own eligible player."""
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Login required."}, status=401)

    url, key, secret = _livekit_config()
    if not url:
        return JsonResponse(
            {"error": "LiveKit config missing or invalid. Check LIVEKIT_URL, LIVEKIT_API_KEY and LIVEKIT_API_SECRET in Render."},
            status=503,
        )

    with transaction.atomic():
        registration = get_object_or_404(
            Registration.objects.select_for_update().select_related("tournament", "player"),
            pk=registration_id,
        )
        if registration.player_id != request.user.pk:
            return JsonResponse({"error": "This registration does not belong to you."}, status=403)
        # Serialize allocation per tournament so concurrent joins cannot exceed capacity.
        tournament = Tournament.objects.select_for_update().get(pk=registration.tournament_id)
        if (
            tournament.status != Tournament.Status.LIVE
            or registration.status != Registration.Status.READY
            or not registration.payment_verified
            or registration.refund_processed
        ):
            return JsonResponse(
                {"error": "Live sharing is available only for paid, confirmed players in a LIVE tournament."},
                status=403,
            )

        TournamentLiveSession.objects.filter(
            tournament=tournament,
            registration__free_fire_uid=registration.free_fire_uid,
            status=TournamentLiveSession.Status.ACTIVE,
        ).exclude(registration=registration).update(
            status=TournamentLiveSession.Status.ENDED,
            ended_at=timezone.now(),
            updated_at=timezone.now(),
        )
        session = TournamentLiveSession.objects.filter(
            registration=registration, status=TournamentLiveSession.Status.ACTIVE
        ).first()
        if session is None:

            session_id = uuid.uuid4()
            room_name = f"ffarena-tournament-{tournament.pk}-reg-{registration.pk}-{session_id.hex[:12]}"
            identity = f"ffarena-player-{registration.player_id}-reg-{registration.pk}-{session_id.hex[:8]}"
            try:
                with transaction.atomic():
                    session = TournamentLiveSession.objects.create(
                        tournament=tournament,
                        registration=registration,
                        session_uuid=session_id,
                        room_name=room_name,
                        participant_identity=identity,
                    )
            except IntegrityError:
                session = TournamentLiveSession.objects.filter(
                    registration=registration, status=TournamentLiveSession.Status.ACTIVE
                ).first()
                if session is None:
                    raise


    try:
        token = (
            api.AccessToken(key, secret)
            .with_identity(session.participant_identity)
            .with_name(request.user.get_username()[:64])
            .with_ttl(timedelta(minutes=30))
            .with_grants(api.VideoGrants(
                room_join=True,
                room=session.room_name,
                can_publish=True,
                can_subscribe=True,
            ))
            .to_jwt()
        )
        return JsonResponse({
            "url": url,
            "token": token,
            "room_name": session.room_name,
            "session_id": str(session.session_uuid),
            "expires_in": 1800,
            "recording": False,
            "monitor": {
                "session_id": str(session.session_uuid),
                "registration_id": registration.pk,
                "state": session.monitor_state,
                "architecture": "shared_tournament_monitor",
            },
        })
    except Exception:
        logger.exception("Tournament LiveKit token generation failed for registration %s", registration_id)
        TournamentLiveSession.objects.filter(
            pk=session.pk, status=TournamentLiveSession.Status.ACTIVE
        ).update(status=TournamentLiveSession.Status.ENDED, ended_at=timezone.now())
        return JsonResponse({"error": "LiveKit token could not be created. Check server logs and LiveKit credentials."}, status=503)



@login_required
@require_GET
def leaderboard_live_tokens(request, tournament_id):
    """Issue subscribe-only tokens for active gameplay streams to verified tournament entrants."""
    tournament = get_object_or_404(Tournament, pk=tournament_id)
    viewer_is_eligible = Registration.objects.filter(
        tournament=tournament,
        player=request.user,
        payment_verified=True,
        refund_processed=False,
        status__in=[
            Registration.Status.CONFIRMED,
            Registration.Status.WAITING_READY,
            Registration.Status.READY,
        ],
    ).exists()
    if not viewer_is_eligible:
        return JsonResponse({"error": "Live gameplay sirf isi tournament ke verified players dekh sakte hain."}, status=403)

    url, key, secret = _livekit_config()
    if not url:
        return JsonResponse({"error": "LiveKit configuration is unavailable."}, status=503)

    sessions = TournamentLiveSession.objects.filter(
        tournament=tournament,
        status=TournamentLiveSession.Status.ACTIVE,
        registration__status=Registration.Status.READY,
        registration__payment_verified=True,
        registration__refund_processed=False,
    ).exclude(registration__player=request.user).select_related(
        "registration", "registration__player"
    ).order_by("started_at")

    streams = []
    for session in sessions:
        identity = f"ffarena-viewer-{request.user.pk}-{session.session_uuid.hex[:12]}"
        token = (
            api.AccessToken(key, secret)
            .with_identity(identity)
            .with_name(request.user.get_username()[:64])
            .with_ttl(timedelta(minutes=10))
            .with_grants(api.VideoGrants(
                room_join=True,
                room=session.room_name,
                can_publish=False,
                can_subscribe=True,
            ))
            .to_jwt()
        )
        streams.append({
            "registration_id": session.registration_id,
            "player": session.registration.player.get_username(),
            "uid": session.registration.free_fire_uid,
            "url": url,
            "token": token,
        })
    return JsonResponse({"tournament_id": tournament.pk, "streams": streams})


@login_required
@require_GET
def admin_tournament_live_tokens(request, tournament_id):
    """Issue per-player monitor tokens for audio/video subscribe and staff audio talkback."""
    if not request.user.is_staff:
        return JsonResponse({"error": "Staff access required."}, status=403)
    url, key, secret = _livekit_config()
    if not url:
        return JsonResponse({"error": "LiveKit configuration is unavailable."}, status=503)
    tournament = get_object_or_404(Tournament, pk=tournament_id)
    if tournament.status != Tournament.Status.LIVE:
        return JsonResponse({"tournament_id": tournament.pk, "streams": [], "completed": tournament.status == Tournament.Status.COMPLETED})
    sessions = list(TournamentLiveSession.objects.filter(
        tournament=tournament,
        status=TournamentLiveSession.Status.ACTIVE,
        registration__status=Registration.Status.READY,
        registration__payment_verified=True,
        registration__refund_processed=False,
    ).select_related("registration", "registration__player").order_by("-started_at", "-pk"))
    # Never publish two monitor feeds for the same in-game UID. Close older duplicates;
    # their session metadata remains available from the separate history page.
    unique_sessions = []
    seen_uids = set()
    for session in sessions:
        uid = str(session.registration.free_fire_uid or "").strip()
        if uid in seen_uids:
            TournamentLiveSession.objects.filter(
                pk=session.pk, status=TournamentLiveSession.Status.ACTIVE
            ).update(status=TournamentLiveSession.Status.ENDED, ended_at=timezone.now(), updated_at=timezone.now())
            continue
        seen_uids.add(uid)
        unique_sessions.append(session)
    sessions = unique_sessions
    registration_ids = [session.registration_id for session in sessions]
    verified_counts = dict(
        LiveKillEvent.objects.filter(
            tournament=tournament,
            registration_id__in=registration_ids,
            status=LiveKillEvent.Status.VERIFIED,
        ).values("registration_id").annotate(total=Count("id")).values_list("registration_id", "total")
    )
    pending_counts = dict(
        LiveKillEvent.objects.filter(
            tournament=tournament,
            registration_id__in=registration_ids,
            status=LiveKillEvent.Status.REVIEW,
        ).values("registration_id").annotate(
            total=Count("id")
        ).values_list("registration_id", "total")
    )
    recent_events = list(
        LiveKillEvent.objects.filter(
            tournament=tournament,
            registration_id__in=[session.registration_id for session in sessions],
        ).select_related("registration").order_by("-detected_at")[:150]
    )
    events_by_registration = {}
    for event in recent_events:
        bucket = events_by_registration.setdefault(event.registration_id, [])
        if len(bucket) >= 5:
            continue
        image_url = ""
        if event.evidence_image and event.evidence_image.name:
            try:
                image_url = event.evidence_image.url
            except (OSError, ValueError):
                image_url = ""
        bucket.append({
            "id": event.pk,
            "status": event.status,
            "killer_name": event.attributed_player_name or "",
            "detected_text": event.detected_text[:700],
            "confidence": str(event.confidence),
            "detected_at": event.detected_at.isoformat(),
            "image_url": image_url,
        })

    streams = []
    for session in sessions:
        identity = f"ffarena-admin-{request.user.pk}-{session.session_uuid.hex[:12]}"
        token = (
            api.AccessToken(key, secret)
            .with_identity(identity)
            .with_name("FF Arena Admin Monitor")
            .with_ttl(timedelta(minutes=10))
            .with_grants(api.VideoGrants(
                room_join=True,
                room=session.room_name,
                # Staff can publish microphone audio back to this one player's room.
                can_publish=True,
                can_subscribe=True,
            ))
            .to_jwt()
        )
        streams.append({
            "registration_id": session.registration_id,
            "player": session.registration.player.get_username(),
            "uid": session.registration.free_fire_uid,
            "session_id": str(session.session_uuid),
            "room_name": session.room_name,
            "token": token,
            "url": url,
            "state": session.monitor_state,
            "identity_verified": bool(session.identity_verified_at),
            "identity_confidence": str(session.identity_ocr_confidence),
            "approved_kills": verified_counts.get(session.registration_id, 0),
            "pending_kills": pending_counts.get(session.registration_id, 0),
            "recent_kill_events": events_by_registration.get(session.registration_id, []),
            "reward_preview": rewards_for_tournament(
                tournament, verified_counts.get(session.registration_id, 0)
            ) if verified_counts.get(session.registration_id, 0) >= 2 else [],
            "frames_seen": session.monitor_frames_seen,
            "detections_seen": session.monitor_detections_seen,
            "last_heartbeat": session.monitor_last_heartbeat_at.isoformat() if session.monitor_last_heartbeat_at else None,
            "monitor_error": session.monitor_last_error,
            "background_warnings": session.background_warning_count,
        })
    return JsonResponse({"tournament_id": tournament.pk, "streams": streams})


@login_required
@require_POST
def admin_send_live_message(request, registration_id):
    """Persist a private staff-to-player message for the active tournament session."""
    if not request.user.is_staff:
        return JsonResponse({"error": "Staff access required."}, status=403)
    registration = get_object_or_404(
        Registration.objects.select_related("tournament", "player"),
        pk=registration_id,
        status=Registration.Status.READY,
        payment_verified=True,
        refund_processed=False,
    )
    if registration.tournament.status != Tournament.Status.LIVE:
        return JsonResponse({"error": "Messages are available only during a LIVE tournament."}, status=409)
    if not TournamentLiveSession.objects.filter(
        registration=registration, status=TournamentLiveSession.Status.ACTIVE
    ).exists():
        return JsonResponse({"error": "Player Live session is not connected."}, status=409)
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except (UnicodeDecodeError, json.JSONDecodeError):
        return JsonResponse({"error": "Invalid message payload."}, status=400)
    body = str(payload.get("message", "")).strip()
    if not body or len(body) > 500:
        return JsonResponse({"error": "Message 1 se 500 characters ke beech hona chahiye."}, status=400)
    message = TournamentLiveMessage.objects.create(
        registration=registration, sender=request.user, body=body
    )
    return JsonResponse({
        "success": True,
        "message_id": message.pk,
        "created_at": message.created_at.isoformat(),
        "message": "Private message player ko bhej diya gaya.",
    }, status=201)


@login_required
@require_GET
def player_live_messages(request, registration_id):
    """Return only unread staff messages for the authenticated registration owner."""
    registration = get_object_or_404(
        Registration.objects.select_related("tournament"),
        pk=registration_id,
        player=request.user,
        status=Registration.Status.READY,
        payment_verified=True,
        refund_processed=False,
    )
    if registration.tournament.status != Tournament.Status.LIVE or not TournamentLiveSession.objects.filter(
        registration=registration, status=TournamentLiveSession.Status.ACTIVE
    ).exists():
        return JsonResponse({"messages": []})
    try:
        after = max(0, int(request.GET.get("after", "0")))
    except (TypeError, ValueError):
        after = 0
    rows = list(
        TournamentLiveMessage.objects.filter(
            registration=registration,
            sender__is_staff=True,
            pk__gt=after,
        ).select_related("sender").order_by("created_at")[:50]
    )
    if rows:
        now = timezone.now()
        TournamentLiveMessage.objects.filter(
            pk__in=[row.pk for row in rows], read_at__isnull=True
        ).update(read_at=now)
    return JsonResponse({
        "messages": [
            {"id": row.pk, "message": row.body, "sender": row.sender.get_username(),
             "created_at": row.created_at.isoformat()}
            for row in rows
        ]
    })

@login_required
@require_POST
def tournament_live_end(request, registration_id):
    """Idempotently end the player's session; no reward or registration state is changed."""
    with transaction.atomic():
        # A registration can have several historical sessions after a player
        # retries Live. Select only the current active row; querying by
        # registration_id alone raises MultipleObjectsReturned on retries.
        sessions = TournamentLiveSession.objects.select_for_update().select_related("registration")
        session = sessions.filter(
            registration_id=registration_id,
            status=TournamentLiveSession.Status.ACTIVE,
        ).order_by("-started_at").first()
        if session is None:
            latest = sessions.filter(registration_id=registration_id).order_by("-started_at").first()
            if latest is None:
                return JsonResponse({"error": "Live session not found."}, status=404)
            if latest.registration.player_id != request.user.pk and not request.user.is_staff:
                return JsonResponse({"error": "Not allowed."}, status=403)
            return JsonResponse({"success": True, "message": "Live session was already ended."})
        if session.registration.player_id != request.user.pk and not request.user.is_staff:
            return JsonResponse({"error": "Not allowed."}, status=403)
        # Staff can mark a BR player eliminated only after the required two kills
        # have been independently approved. A player may still end their own stream.
        if request.user.is_staff and session.tournament.mode == "BR":
            approved_kills = LiveKillEvent.objects.filter(
                tournament=session.tournament,
                registration=session.registration,
                status=LiveKillEvent.Status.VERIFIED,
            ).count()
            if approved_kills < 2:
                return JsonResponse({
                    "error": f"BR elimination cannot be finalized yet: {approved_kills}/2 Admin-confirmed kills. Review and approve at least 2 kills first."
                }, status=409)
        session.status = TournamentLiveSession.Status.ENDED
        session.ended_at = timezone.now()
        session.save(update_fields=("status", "ended_at", "updated_at"))
        room_name = session.room_name
        player_identity = session.participant_identity

    url, key, secret = _livekit_config()
    if url:
        try:
            async def remove_player_from_room():
                async with api.LiveKitAPI(url, key, secret) as lkapi:
                    await lkapi.room.remove_participant(
                        api.RoomParticipantIdentity(room=room_name, identity=player_identity)
                    )

            async_to_sync(remove_player_from_room)()
        except Exception:
            logger.exception("Could not disconnect eliminated player from LiveKit room %s", room_name)
    return JsonResponse({"success": True, "message": "Live session ended; player stream disconnect requested."})

@login_required
@require_POST
def tournament_live_warning(request, registration_id):
    """Record a background-app warning without banning or removing the player."""
    session = get_object_or_404(
        TournamentLiveSession.objects.select_related("registration"),
        registration_id=registration_id,
        status=TournamentLiveSession.Status.ACTIVE,
    )
    if session.registration.player_id != request.user.pk:
        return JsonResponse({"error": "Not allowed."}, status=403)
    TournamentLiveSession.objects.filter(pk=session.pk).update(
        background_warning_count=F("background_warning_count") + 1,
        updated_at=timezone.now(),
    )
    session.refresh_from_db(fields=("background_warning_count",))
    return JsonResponse({
        "success": True,
        "warning_count": session.background_warning_count,
        "message": "App background warning recorded. You are not banned or removed.",
    })
