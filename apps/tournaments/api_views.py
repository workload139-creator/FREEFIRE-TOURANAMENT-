from django.http import JsonResponse
from django.views.decorators.http import require_GET
from django.utils import timezone

from .models import Tournament


def _serialize_tournament(tournament):
    return {
        "id": tournament.id,
        "title": tournament.title,
        "mode": tournament.mode,
        "vs_format": tournament.vs_format,
        "gender_category": tournament.gender_category,
        "description": tournament.description,
        "entry_fee": str(tournament.entry_fee),
        "prize_pool": str(tournament.prize_pool),
        "max_players": tournament.max_players,
        "players_joined": tournament.confirmed_players_count,
        "start_time": tournament.start_time.isoformat(),
        "status": tournament.status,
        "is_full": tournament.is_full,
        # Any admin edit updates this timestamp and triggers an app refresh.
        "updated_at": tournament.updated_at.isoformat(),
    }


@require_GET
def public_tournament_list_api(request):
    """Read-only JSON API used by the Android app to detect admin changes."""
    queryset = Tournament.objects.filter(
        status__in=[
            Tournament.Status.UPCOMING,
            Tournament.Status.LIVE,
            Tournament.Status.COMPLETED,
        ]
    ).order_by("start_time", "pk")

    mode = request.GET.get("mode", "").upper()
    if mode in (Tournament.Mode.BR, Tournament.Mode.VS):
        queryset = queryset.filter(mode=mode)

    status = request.GET.get("status", "").lower()
    if status in dict(Tournament.Status.choices):
        queryset = queryset.filter(status=status)

    try:
        limit = min(max(int(request.GET.get("limit", "30")), 1), 50)
    except (TypeError, ValueError):
        limit = 30

    now = timezone.now()
    items = [_serialize_tournament(t) for t in queryset[:limit]]
    response = JsonResponse({
        "success": True,
        "server_time": now.isoformat(),
        "count": len(items),
        "results": items,
    })
    response["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response["Pragma"] = "no-cache"
    return response
