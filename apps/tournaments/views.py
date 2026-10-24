
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import RegistrationForm
from .models import Registration, Tournament


def tournament_list(request):
    tournaments = Tournament.objects.all().order_by("start_time")

    return render(
        request,
        "tournaments/list.html",
        {"tournaments": tournaments},
    )


def tournament_detail(request, tournament_id):
    tournament = get_object_or_404(Tournament, pk=tournament_id)

    return render(
        request,
        "tournaments/detail.html",
        {"tournament": tournament},
    )


@login_required
def tournament_register(request, tournament_id):
    if request.method != "POST":
        return redirect("tournaments:list")

    form = RegistrationForm(request.POST)

    if not form.is_valid():
        messages.error(
            request,
            "Free Fire UID check karo. UID sirf numbers mein honi chahiye.",
        )
        return redirect("tournaments:detail", tournament_id=tournament_id)

    try:
        with transaction.atomic():
            tournament = get_object_or_404(
                Tournament.objects.select_for_update(),
                pk=tournament_id,
            )

            if tournament.status != Tournament.Status.UPCOMING:
                messages.error(
                    request,
                    "Ye tournament registration ke liye available nahi hai.",
                )
                return redirect("tournaments:list")

            if tournament.start_time <= timezone.now():
                messages.error(
                    request,
                    "Tournament ka start time nikal chuka hai.",
                )
                return redirect("tournaments:list")

            if tournament.is_full:
                messages.error(
                    request,
                    "Tournament mein jagah full hai.",
                )
                return redirect("tournaments:list")

            if Registration.objects.filter(
                tournament=tournament,
                player=request.user,
            ).exists():
                messages.info(
                    request,
                    "Aap pehle se is tournament mein registered hain.",
                )
                return redirect("tournaments:list")

            registration = Registration.objects.create(
                tournament=tournament,
                player=request.user,
                free_fire_uid=form.cleaned_data["free_fire_uid"],
                entry_fee_paid=0,
                payment_verified=False,
                status=Registration.Status.PENDING_PAYMENT,
            )

    except IntegrityError:
        messages.error(
            request,
            "Registration nahi ho saki. Aap pehle se registered ho sakte hain.",
        )
        return redirect("tournaments:list")

    messages.success(
        request,
        "Registration record ban gaya. Payment verify hone ke baad hi "
        "registration confirm hogi.",
    )
    return redirect("tournaments:list")


@login_required
def confirm_playing(request, registration_id):
    if request.method != "POST":
        return redirect("tournaments:list")

    with transaction.atomic():
        registration = get_object_or_404(
            Registration.objects.select_for_update().select_related(
                "tournament"
            ),
            pk=registration_id,
            player=request.user,
        )

        if registration.status != Registration.Status.WAITING_READY:
            messages.error(
                request,
                "Is registration ki confirmation available nahi hai.",
            )
            return redirect("tournaments:list")

        if not registration.payment_verified:
            messages.error(request, "Payment verify nahi hui hai.")
            return redirect("tournaments:list")

        if not registration.tournament.room_id:
            messages.error(
                request,
                "Room details abhi available nahi hain.",
            )
            return redirect("tournaments:list")

        registration.status = Registration.Status.READY
        registration.ready_confirmed_at = timezone.now()
        registration.save(
            update_fields=["status", "ready_confirmed_at", "updated_at"]
        )

    messages.success(request, "Tumhari participation confirm ho gayi!")
    return redirect(
        "tournaments:player_room",
        registration_id=registration_id,
    )


@login_required
@user_passes_test(lambda user: user.is_staff)
def send_room_details(request, tournament_id):
    if request.method != "POST":
        return redirect("tournaments:list")

    room_id = request.POST.get("room_id", "").strip()
    room_password = request.POST.get("room_password", "").strip()

    if not room_id or not room_password:
        messages.error(request, "Room ID aur password dono bharo.")
        return redirect(
            "tournaments:admin_room_page",
            tournament_id=tournament_id,
        )

    with transaction.atomic():
        tournament = get_object_or_404(
            Tournament.objects.select_for_update(),
            pk=tournament_id,
        )

        if tournament.status != Tournament.Status.UPCOMING:
            messages.error(
                request,
                "Sirf upcoming tournament ke liye room details set kar sakte ho.",
            )
            return redirect(
                "tournaments:admin_room_page",
                tournament_id=tournament_id,
            )

        tournament.room_id = room_id
        tournament.room_password = room_password
        tournament.save(update_fields=["room_id", "room_password"])

        registrations = Registration.objects.select_for_update().filter(
            tournament=tournament,
            status=Registration.Status.CONFIRMED,
            payment_verified=True,
        )

        registrations.update(status=Registration.Status.WAITING_READY)

    messages.success(
        request,
        "Room details save ho gayi. Eligible players confirmation de sakte hain.",
    )
    return redirect(
        "tournaments:admin_room_page",
        tournament_id=tournament_id,
    )


@login_required
@user_passes_test(lambda user: user.is_staff)
def admin_room_page(request, tournament_id):
    tournament = get_object_or_404(Tournament, pk=tournament_id)

    return render(
        request,
        "tournaments/admin_room.html",
        {"tournament": tournament},
    )


@login_required
def player_room(request, registration_id):
    registration = get_object_or_404(
        Registration.objects.select_related("tournament"),
        pk=registration_id,
        player=request.user,
    )

    can_view_room = (
        registration.status == Registration.Status.READY
        and registration.payment_verified
        and bool(registration.tournament.room_id)
    )

    return render(
        request,
        "tournaments/player_room.html",
        {
            "registration": registration,
            "tournament": registration.tournament,
            "can_view_room": can_view_room,
        },
    )


@login_required
@user_passes_test(lambda user: user.is_staff)
def admin_tournament_dashboard(request, tournament_id):
    tournament = get_object_or_404(Tournament, pk=tournament_id)

    registrations = (
        Registration.objects.filter(tournament=tournament)
        .select_related("player")
        .order_by("-registered_at")
    )

    context = {
        "tournament": tournament,
        "registrations": registrations,
        "total_players": registrations.count(),
        "verified_payments": registrations.filter(
            payment_verified=True
        ).count(),
        "waiting_players": registrations.filter(
            status=Registration.Status.WAITING_READY
        ).count(),
        "ready_players": registrations.filter(
            status=Registration.Status.READY
        ).count(),
        "not_playing_players": registrations.filter(
            status=Registration.Status.NOT_PLAYING
        ).count(),
    }

    return render(
        request,
        "tournaments/admin_dashboard.html",
        context,
    )
