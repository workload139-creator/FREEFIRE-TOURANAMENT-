from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from .forms import PlayerRegistrationForm


def register_view(request):
    if request.user.is_authenticated:
        return redirect("accounts:profile")

    if request.method == "POST":
        form = PlayerRegistrationForm(request.POST)

        if form.is_valid():
            user = form.save(commit=False)

            # Registration alone does not verify phone or UID.
            user.phone_verified = False
            user.uid_verified = False

            user.save()

            messages.success(
                request,
                "Account ban gaya! Phone verification abhi pending hai.",
            )

            login(request, user)

            return redirect("accounts:profile")
    else:
        form = PlayerRegistrationForm()

    return render(
        request,
        "accounts/register.html",
        {"form": form},
    )


@login_required
def profile_view(request):
    return render(
        request,
        "accounts/profile.html",
        {"player": request.user},
    )
