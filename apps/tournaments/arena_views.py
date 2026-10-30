from django.db.models import Case, IntegerField, Value, When
from django.shortcuts import render

from .constants import PLAYER_CONFIRMATION_TIMEOUT_SECONDS
from .models import Tournament
from .services import process_expired_ready_registrations


PUBLIC_STATUSES = (
    Tournament.Status.UPCOMING,
    Tournament.Status.LIVE,
    Tournament.Status.COMPLETED,
)


def _one_event_per_format(queryset, format_field, formats):
    """Show one current event card per format; keep all older records and URLs intact."""
    priority = Case(
        When(status=Tournament.Status.LIVE, then=Value(0)),
        When(status=Tournament.Status.UPCOMING, then=Value(1)),
        default=Value(2),
        output_field=IntegerField(),
    )
    events = []
    for format_code in formats:
        event = queryset.filter(**{format_field: format_code}).order_by(
            priority, "-created_at", "-pk"
        ).first()
        if event is not None:
            events.append(event)
    return events


def battle_royale_list(request):
    process_expired_ready_registrations()
    tournaments = Tournament.objects.filter(
        mode=Tournament.Mode.BR,
        is_free_fan_tournament=False,
        is_diwali_offer=False,
        is_unlimited_br=False,
        gender_category__in=(
            Tournament.GenderCategory.OPEN,
            Tournament.GenderCategory.BOYS,
            Tournament.GenderCategory.GIRLS,
        ),
        status__in=PUBLIC_STATUSES,
    )
    events = _one_event_per_format(tournaments, "br_format", ("solo", "duo", "squad"))
    return render(request, "tournaments/battle_royale_list.html", {"tournaments": events})



def diwali_offer_list(request):
    """Dedicated public page for the date-free 1-Diamond Solo BR Diwali offer."""
    process_expired_ready_registrations()
    events = Tournament.objects.filter(
        mode=Tournament.Mode.BR,
        br_format=Tournament.BRFormat.SOLO,
        is_diwali_offer=True,
        is_free_fan_tournament=False,
        status__in=PUBLIC_STATUSES,
    ).order_by(Case(
        When(status=Tournament.Status.LIVE, then=Value(0)),
        When(status=Tournament.Status.UPCOMING, then=Value(1)),
        default=Value(2),
        output_field=IntegerField(),
    ), "-created_at", "-pk")
    return render(request, "tournaments/diwali_offer_list.html", {"tournaments": events})

def clash_squad_list(request):
    process_expired_ready_registrations()
    tournaments = Tournament.objects.filter(
        mode=Tournament.Mode.VS,
        is_free_fan_tournament=False,
        gender_category__in=(
            Tournament.GenderCategory.OPEN,
            Tournament.GenderCategory.BOYS,
            Tournament.GenderCategory.GIRLS,
        ),
        status__in=PUBLIC_STATUSES,
    )
    events = _one_event_per_format(tournaments, "vs_format", ("1v1", "2v2", "3v3", "4v4"))
    return render(request, "tournaments/clash_squad_list.html", {"tournaments": events})


def girls_vs_boys_list(request):
    """Dedicated public page for Girls vs Boys tournaments across BR and VS modes."""
    process_expired_ready_registrations()
    tournaments = Tournament.objects.filter(
        gender_category=Tournament.GenderCategory.GIRLS_VS_BOYS,
        is_free_fan_tournament=False,
        is_diwali_offer=False,
        is_unlimited_br=False,
        status__in=PUBLIC_STATUSES,
    ).order_by(
        Case(
            When(status=Tournament.Status.LIVE, then=Value(0)),
            When(status=Tournament.Status.UPCOMING, then=Value(1)),
            default=Value(2),
            output_field=IntegerField(),
        ),
        "mode", "br_format", "vs_format", "-created_at", "-pk",
    )
    return render(request, "tournaments/girls_vs_boys_list.html", {"tournaments": tournaments})
