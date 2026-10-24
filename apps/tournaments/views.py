```python
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import RegistrationForm
from .models import Registration, Tournament
from .services import mark_not_playing_and_refund


def tournament_list(request):
    tournaments = Tournament.objects.all().order_by("start_time")

    return render(
        request,
        "tournaments/list.html",
        {"tournaments": tournaments},
    )


@login_required
def tournament_register(request, tournament_id):
    tournament = get_object_or_404(Tournament, pk=tournament_id)

    if tournament.status != Tournament.Status.UPCOMING:
        messages.error(
            request,
            "Ye tournament abhi registration ke liye available nahi hai.",
        )
        return redirect("tournaments:list")

    if tournament.is_full:
        messages.error(request, "Tournament mein jagah full hai.")
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

    if request.method == "POST":
        form = RegistrationForm(request.POST)

        if form.is_valid():
            try:
                with transaction.atomic():
                    # Lock tournament to reduce simultaneous over-registration.
                    locked_tournament = Tournament.objects.select_for_update().get(
                        pk=tournament.pk
                    )

                    if locked_tournament.is_full:
                        messages.error(
                            request,
                            "Tournament mein jagah full hai.",
                        )
                        return redirect("tournaments:list")

                    if Registration.objects.filter(
                        tournament=locked_tournament,
                        player=request.user,
                    ).exists():
                        messages.info(
                            request,
                            "Aap pehle se registered hain.",
                        )
                        return redirect("tournaments:list")

                    registration = form.save(commit=False)
                    registration.tournament = locked_tournament
                    registration.player = request.user
                    registration.entry_fee_paid = 0
                    registration.payment_verified = False
                    registration.status = (
                        Registration.Status.PENDING_PAYMENT
                    )
                    registration.save()

                messages.success(
                    request,
                    "Registration record ban gaya. Payment verify hone ke baad "
                    "hi registration confirm hogi.",
                )
                return redirect("tournaments:list")

            except IntegrityError:
                messages.error(
                    request,
                    "Aapki registration pehle se maujood hai.",
                )
                return redirect("tournaments:list")
    else:
        form = RegistrationForm()

    return render(
        request,
        "tournaments/register.html",
        {
            "form": form,
            "tournament": tournament,
        },
    )


@login_required
def confirm_playing(request, registration_id):
    if request.method != "POST":
        return redirect("tournaments:list")

    expired = False

    with transaction.atomic():
        registration = get_object_or_404(
            Registration.objects.select_for_update(),
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

        if registration.refund_processed:
            messages.error(
                request,
                "Is registration ka refund pehle hi process ho chuka hai.",
            )
            return redirect("tournaments:list")

        if not registration.room_details_sent:
            messages.error(
                request,
                "Room details abhi available nahi hain.",
            )
            return redirect("tournaments:list")

        if (
            not registration.ready_deadline
            or timezone.now() >= registration.ready_deadline
        ):
            expired = True
        else:
            registration.status = Registration.Status.READY
            registration.ready_confirmed_at = timezone.now()
            registration.save(
                update_fields=[
                    "status",
                    "ready_confirmed_at",
                    "updated_at",
                ]
            )

    if expired:
        mark_not_playing_and_refund(registration_id)
        messages.error(
            request,
            "Confirmation ka time khatam ho gaya. Refund status wallet mein check karein.",
        )
        return redirect("tournaments:list")

    messages.success(
        request,
        "Tumhari participation confirm ho gayi!",
    )
    return redirect("tournaments:player_room", registration_id=registration_id)


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

        deadline = timezone.now() + timedelta(seconds=60)

        registrations = Registration.objects.select_for_update().filter(
            tournament=tournament,
            status=Registration.Status.CONFIRMED,
            payment_verified=True,
            refund_processed=False,
        )

        for registration in registrations:
            registration.room_details_sent = True
            registration.ready_deadline = deadline
            registration.status = Registration.Status.WAITING_READY
            registration.save(
                update_fields=[
                    "room_details_sent",
                    "ready_deadline",
                    "status",
                    "updated_at",
                ]
            )

    messages.success(
        request,
        "Room details set ho gayi hain. Eligible players ko 60 seconds "
        "mein confirmation dena hoga.",
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

    if (
        registration.status == Registration.Status.WAITING_READY
        and registration.ready_deadline
        and timezone.now() >= registration.ready_deadline
    ):
        mark_not_playing_and_refund(registration.id)
        registration.refresh_from_db()

        messages.warning(
            request,
            "Confirmation ka time khatam ho gaya. Room access band kar diya gaya hai.",
        )

    can_view_room = (
        registration.room_details_sent
        and registration.status
        in (
            Registration.Status.WAITING_READY,
            Registration.Status.READY,
        )
        and registration.payment_verified
        and not registration.refund_processed
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
        Registration.objects
        .filter(tournament=tournament)
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
        "refunded_players": registrations.filter(
            refund_processed=True
        ).count(),
    }

    return render(
        request,
        "tournaments/admin_dashboard.html",
        context,
    )
```
