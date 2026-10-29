import logging
import os
from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_POST

from livekit import api

from .party_models import PartyRoom, PartyRoomMembership


logger = logging.getLogger(__name__)


@login_required
@require_POST
def party_voice_token(request, room_id):
    """Issue a short-lived LiveKit token only to a current member of this party room."""
    room = get_object_or_404(PartyRoom, pk=room_id)
    if not PartyRoomMembership.objects.filter(room=room, user=request.user).exists():
        return JsonResponse({"error": "Join this party room before connecting voice."}, status=403)

    livekit_url = os.getenv("LIVEKIT_URL", "").strip()
    api_key = os.getenv("LIVEKIT_API_KEY", "").strip()
    api_secret = os.getenv("LIVEKIT_API_SECRET", "").strip()
    if not (livekit_url and api_key and api_secret):
        return JsonResponse(
            {"error": "Live voice is not configured. Set LIVEKIT_URL, LIVEKIT_API_KEY and LIVEKIT_API_SECRET in Render Environment."},
            status=503,
        )
    if not livekit_url.startswith(("wss://", "ws://")):
        return JsonResponse(
            {"error": "LIVEKIT_URL must be the LiveKit WebSocket URL beginning with wss:// (or ws:// for local testing)."},
            status=503,
        )

    try:
        room_name = f"ffarena-party-{room.pk}"
        token = (
            api.AccessToken(api_key, api_secret)
            .with_identity(f"user-{request.user.pk}")
            .with_name(request.user.get_username()[:64])
            .with_ttl(timedelta(minutes=45))
            .with_grants(api.VideoGrants(
                room_join=True,
                room=room_name,
                can_publish=True,
                can_subscribe=True,
            ))
            .to_jwt()
        )
        return JsonResponse({"url": livekit_url, "token": token, "room_name": room_name})
    except Exception:
        logger.exception("LiveKit party token generation failed for room %s", room.pk)
        return JsonResponse(
            {"error": "The server could not create a LiveKit token. Check the Render logs and LiveKit API key/secret."},
            status=500,
        )
