from django.db.models import Q
from django.utils import timezone
from django.shortcuts import render

from apps.tournaments.models import Tournament


def home(request):
    now = timezone.now()
    tournaments = Tournament.objects.filter(
        Q(status=Tournament.Status.UPCOMING, start_time__gte=now)
        | Q(status=Tournament.Status.LIVE)
    ).order_by("start_time")[:6]
    return render(request, "pages/home.html", {"featured_tournaments": tournaments})
