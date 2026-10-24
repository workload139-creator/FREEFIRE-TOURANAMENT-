
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from datetime import timedelta
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .models import Tournament, Registration

from .forms import RegistrationForm
from .models import Registration, Tournament


def tournament_list(request):
    tournaments = Tournament.objects.all().order_by("start_time")

    return render(
        request,
        "tournaments/list.html",
        {"tournaments": tournaments},
    )


@login_required
def tournament_register(request, tournament_id):
    tournament = get_object_or_404(
        Tournament,
        pk=tournament_id,
    )

    if tournament.status != Tournament.Status.UPCOMING:
        messages.error(request, "Ye tournament abhi registration ke liye available nahi hai.")
        return redirect("tournaments:list")

    if tournament.is_full:
        messages.error(request, "Tournament mein players ki jagah full hai.")
        return redirect("tournaments:list")

    if Registration.objects.filter(
        tournament=tournament,
        player=request.user,
    ).exists():
        messages.info(request, "Aap pehle se is tournament mein registered hain.")
        return redirect("tournaments:list")

    if request.method == "POST":
        form = RegistrationForm(request.POST)

        if form.is_valid():
            try:
                with transaction.atomic():
                    registration = form.save(commit=False)
                    registration.tournament = tournament
                    registration.player = request.user
                    registration.entry_fee_paid = 0
                    registration.payment_verified = False
                    registration.status = Registration.Status.PENDING_PAYMENT
                    registration.save()

                messages.success(
                    request,
                    "Registration record ban gaya. Entry fee payment abhi verify nahi hui hai.",
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

    registration = get_object_or_404(
        Registration,
        pk=registration_id,
        player=request.user,
    )

    if not registration.room_details_sent:
        messages.error(request, "Room details abhi available nahi hain.")
        return redirect("tournaments:list")

    if not registration.ready_deadline:
        messages.error(request, "Confirmation deadline set nahi hai.")
        return redirect("tournaments:list")

    if timezone.now() > registration.ready_deadline:
        registration.status = Registration.Status.NOT_PLAYING
        registration.save(update_fields=["status"])
        messages.error(request, "Confirmation ka time khatam ho gaya.")
        return redirect("tournaments:list")

    if registration.status != Registration.Status.WAITING_READY:
        messages.error(request, "Is registration ki confirmation available nahi hai.")
        return redirect("tournaments:list")

    registration.status = Registration.Status.READY
    registration.ready_confirmed_at = timezone.now()
    registration.save(
        update_fields=["status", "ready_confirmed_at"]
    )

    messages.success(request, "Tumhari participation confirm ho gayi!"
                    
                    
                    
                    )


@login_required
@user_passes_test(lambda user: user.is_staff)
def send_room_details(request, tournament_id):
    tournament = get_object_or_404(Tournament, pk=tournament_id)

    if request.method != "POST":
        return redirect("tournaments:list")

    room_id = request.POST.get("room_id", "").strip()
    room_password = request.POST.get("room_password", "").strip()

    if not room_id or not room_password:
        messages.error(request, "Room ID aur password dono bharo.")
        return redirect("tournaments:list")

    if tournament.status != Tournament.Status.UPCOMING:
        messages.error(request, "Sirf upcoming tournament ke liye room details bhej sakte ho.")
        return redirect("tournaments:list")

    tournament.room_id = room_id
    tournament.room_password = room_password
    tournament.save(update_fields=["room_id", "room_password"])

    deadline = timezone.now() + timedelta(seconds=60)

    registrations = Registration.objects.filter(
        tournament=tournament,
        status=Registration.Status.CONFIRMED,
        payment_verified=True,
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
            ]
        )

    messages.success(
        request,
        "Room details set ho gayi hain. Eligible players ko 60-second confirmation milega.",
    )
    return redirect("tournaments:list")
    
    return redirect("tournaments:list")



@login_required
@user_passes_test(lambda user: user.is_staff)
def admin_room_page(request, tournament_id):
    tournament = get_object_or_404(Tournament, pk=tournament_id)

    return render(
        request,
        "tournaments/admin_room.html",
        {"tournament": tournament},
    )




