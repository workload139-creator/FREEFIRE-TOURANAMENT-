from django.utils import timezone
from django.shortcuts import render

from apps.tournaments.models import Tournament


def home(request):
    tournaments = Tournament.objects.filter(
        status__in=[Tournament.Status.UPCOMING, Tournament.Status.LIVE],
        start_time__gte=timezone.now(),
    ).order_by("start_time")[:6]
    return render(request, "pages/home.html", {"featured_tournaments": tournaments})
