
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404, redirect, render

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
