from django.db import DatabaseError, connection
from django.db.models import Q
from django.utils import timezone
from django.http import JsonResponse
from django.shortcuts import render

from apps.tournaments.models import Tournament


def home(request):
    now = timezone.now()
    tournaments = Tournament.objects.filter(
        Q(status=Tournament.Status.UPCOMING, start_time__gte=now)
        | Q(status=Tournament.Status.LIVE)
    ).order_by("start_time")[:6]
    return render(request, "pages/home.html", {"featured_tournaments": tournaments})



def health_check(request):
    """Lightweight Render health endpoint; never expose internal error details."""
    try:
        connection.ensure_connection()
    except DatabaseError:
        return JsonResponse(
            {"status": "unhealthy", "database": "unavailable"},
            status=503,
        )
    return JsonResponse({"status": "ok", "database": "ok"})
