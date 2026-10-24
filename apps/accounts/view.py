from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.db import IntegrityError, transaction
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

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
                    user.phone_verified = False
                    user.uid_verified = False
                    user.save()

                login(request, user)

                messages.success(
                    request,
                    "Account successfully created. "
                    "Phone and Free Fire UID verification are pending.",
                )

                return redirect("accounts:profile")

            except IntegrityError:
                form.add_error(
                    None,
                    "These account details already exist. Please try again.",
                )
    else:
        form = PlayerRegistrationForm()

    return render(
        request,
        "accounts/register.html",
        {"form": form},
    )


def login_view(request):
    if request.user.is_authenticated:
        return redirect("accounts:profile")

    if request.method == "POST":
        form = AuthenticationForm(
            request=request,
            data=request.POST,
        )

        if form.is_valid():
            user = form.get_user()
            login(request, user)

            messages.success(
                request,
                "Login successful!",
            )

            return redirect("accounts:profile")
    else:
        form = AuthenticationForm(request=request)

    return render(
        request,
        "accounts/login.html",
        {"form": form},
    )


@login_required
def profile_view(request):
    return render(
        request,
        "accounts/profile.html",
        {"player": request.user},
    )


@require_POST
@login_required
def logout_view(request):
    logout(request)

    messages.success(
        request,
        "You have been logged out successfully.",
    )

    return redirect("home")







from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from .models import Wallet


@login_required
def wallet_view(request):
    wallet, created = Wallet.objects.get_or_create(
        user=request.user,
    )

    transactions = wallet.transactions.all()[:50]

    return render(
        request,
        "accounts/wallet.html",
        {
            "wallet": wallet,
            "transactions": transactions,
        },
    )



from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import redirect, render

from .forms import DepositRequestForm
from .models import DepositRequest, Wallet


@login_required
def deposit_view(request):
    wallet, _ = Wallet.objects.get_or_create(user=request.user)

    if request.method == "POST":
        form = DepositRequestForm(request.POST)

        if form.is_valid():
            with transaction.atomic():
                wallet = Wallet.objects.select_for_update().get(
                    pk=wallet.pk
                )
                pending_total = sum(
                    DepositRequest.objects.filter(
                        wallet=wallet,
                        status=DepositRequest.Status.PENDING,
                    ).values_list("amount", flat=True),
                    start=0,
                )

                if wallet.balance + pending_total + form.cleaned_data["amount"] > Decimal("5000.00"):
                    form.add_error(
                        "amount",
                        "Wallet limit ₹5000 hai. Pending requests bhi limit mein count hongi.",
                    )
                else:
                    deposit = form.save(commit=False)
                    deposit.wallet = wallet
                    deposit.save()

                    messages.success(
                        request,
                        "Deposit request submit ho gayi. Verification ke baad hi balance update hoga.",
                    )
                    return redirect("accounts:wallet")
    else:
        form = DepositRequestForm()

    return render(
        request,
        "accounts/deposit.html",
        {"form": form, "wallet": wallet},
    )
