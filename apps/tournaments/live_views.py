"""Authenticated LiveKit access for tournament screen-sharing sessions.

LiveKit room media is streamed only; this module does not enable recording or egress.
"""
import logging
import os
import uuid
from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.db.models import F
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_POST

from livekit import api

from .models import Registration, Tournament, TournamentLiveSession

logger = logging.getLogger(__name__)

# One isolated logical Live agent slot per eligible player; media processing is shared.
MAX_LIVE_PLAYER_AGENTS_PER_TOURNAMENT = 50


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

        session = TournamentLiveSession.objects.filter(
            registration=registration, status=TournamentLiveSession.Status.ACTIVE
        ).first()
        if session is None:
            active_agents = TournamentLiveSession.objects.filter(
                tournament=tournament,
                status=TournamentLiveSession.Status.ACTIVE,
            ).count()
            if active_agents >= MAX_LIVE_PLAYER_AGENTS_PER_TOURNAMENT:
                return JsonResponse({
                    "error": "This tournament has reached its 50-player Live AI session limit.",
                    "agent_capacity": MAX_LIVE_PLAYER_AGENTS_PER_TOURNAMENT,
                    "active_agent_sessions": active_agents,
                }, status=409)
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
            "player_agent": {
                "session_id": str(session.session_uuid),
                "registration_id": registration.pk,
                "state": "awaiting_android_stream",
                "scope": "one_isolated_agent_slot_per_player",
                "active_sessions": TournamentLiveSession.objects.filter(
                    tournament=tournament,
                    status=TournamentLiveSession.Status.ACTIVE,
                ).count(),
                "capacity": MAX_LIVE_PLAYER_AGENTS_PER_TOURNAMENT,
            },
        })
    except Exception:
        logger.exception("Tournament LiveKit token generation failed for registration %s", registration_id)
        TournamentLiveSession.objects.filter(
            pk=session.pk, status=TournamentLiveSession.Status.ACTIVE
        ).update(status=TournamentLiveSession.Status.ENDED, ended_at=timezone.now())
        return JsonResponse({"error": "LiveKit token could not be created. Check server logs and LiveKit credentials."}, status=503)


@login_required
@require_POST
def tournament_live_end(request, registration_id):
    """Idempotently end the player's session; no reward or registration state is changed."""
    with transaction.atomic():
        session = get_object_or_404(
            TournamentLiveSession.objects.select_for_update().select_related("registration"),
            registration_id=registration_id,
        )
        if session.registration.player_id != request.user.pk and not request.user.is_staff:
            return JsonResponse({"error": "Not allowed."}, status=403)
        if session.status == TournamentLiveSession.Status.ENDED:
            return JsonResponse({"success": True, "message": "Live session was already ended."})
        session.status = TournamentLiveSession.Status.ENDED
        session.ended_at = timezone.now()
        session.save(update_fields=("status", "ended_at", "updated_at"))
    return JsonResponse({"success": True, "message": "Live session ended."})

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
