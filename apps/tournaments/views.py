from django.shortcuts import render
from .models import Tournament


def tournament_list(request):
    tournaments = Tournament.objects.all().order_by("start_time")

    return render(
        request,
        "tournaments/list.html",
        {"tournaments": tournaments},
    )
