from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.shortcuts import redirect, render

from .forms import PlayerRegistrationForm


def register_view(request):
    if request.user.is_authenticated:
        return redirect("accounts:profile")

    if request.method == "POST":
        form = PlayerRegistrationForm(request.POST)

        if form.is_valid():
            try:
                with transaction.atomic():
                    user = form.save(commit=False)

                    # Verification is pending until a real
                    # verification process has been completed.
                    user.phone_verified = False
                    user.uid_verified = False

                    user.save()

                login(request, user)

                messages.success(
                    request,
                    "Account created successfully. "
                    "Phone and Free Fire UID verification are pending.",
                )

                return redirect("accounts:profile")

            except IntegrityError:
                form.add_error(
                    None,
                    "Account details already exist. Please check and try again.",
                )
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
