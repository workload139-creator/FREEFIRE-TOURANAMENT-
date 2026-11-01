from django.contrib import messages
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
import logging
from decimal import Decimal

logger = logging.getLogger(__name__)
from urllib.parse import quote
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm
from django.db import IntegrityError, transaction
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .forms import PlayerRegistrationForm, ProfileUpdateForm, WithdrawalRequestForm


def register_view(request):
    if request.user.is_authenticated:
        return redirect("accounts:profile")

    verified_email = request.session.get("email_otp_verified")
    if not verified_email:
        messages.info(request, "Account banane se pehle email OTP verify karein.")
        return redirect("accounts:email_otp")

    if request.method == "POST":
        form = PlayerRegistrationForm(request.POST, request.FILES)
        if form.is_valid() and form.cleaned_data["email"].lower() != verified_email.lower():
            form.add_error("email", "Wahi email use karein jise abhi OTP se verify kiya hai.")
        if form.is_valid():
            try:
                requested_username = request.POST.get("username", "").strip()
                final_username = form.cleaned_data["username"]
                with transaction.atomic():
                    user = form.save(commit=False)
                    user.phone_verified = False
                    user.uid_verified = False
                    user.save()

                request.session.pop("email_otp_verified", None)
                request.session.pop("email_otp_verified_at", None)
                login(request, user)

                if requested_username.lower() != final_username.lower():
                    messages.info(
                        request,
                        f"Username pehle se use ho raha tha, isliye aapka unique username {final_username} rakha gaya. Ise login ke liye note kar lein.",
                    )
                messages.success(
                    request,
                    f"Account successfully created! Aapka username: {final_username}. Email verified hai; Free Fire UID tournament registration ke waqt verify hogi.",
                )
                return redirect("accounts:profile")
            except IntegrityError:
                form.add_error(None, "These account details already exist. Please try again.")
    else:
        form = PlayerRegistrationForm(initial={"email": verified_email})

    return render(request, "accounts/register.html", {"form": form, "verified_email": verified_email})


def login_view(request):
    next_url = request.POST.get("next") or request.GET.get("next", "")
    if request.user.is_authenticated:
        if next_url and url_has_allowed_host_and_scheme(
            next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
        ):
            return redirect(next_url)
        return redirect("accounts:profile")

    if request.method == "POST":
        form = AuthenticationForm(request=request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            messages.success(request, "Login successful!")
            if next_url and url_has_allowed_host_and_scheme(
                next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
            ):
                return redirect(next_url)
            return redirect("accounts:profile")
    else:
        form = AuthenticationForm(request=request)

    return render(
        request,
        "registration/login.html",
        {"form": form, "next": next_url},
    )

@login_required
def profile_view(request):
    from apps.social.models import Follow

    return render(request, "accounts/profile.html", {
        "player": request.user,
        "active_tick": __import__("apps.social.models", fromlist=["FFTickSubscription"]).FFTickSubscription.objects.filter(user=request.user, status="active", expires_at__gt=__import__("django.utils.timezone", fromlist=["now"]).now()).first(),
        "followers_count": Follow.objects.filter(following=request.user).count(),
        "following_count": Follow.objects.filter(follower=request.user).count(),
    })


@login_required
def profile_edit_view(request):
    next_url = request.POST.get("next") or request.GET.get("next", "")
    if request.method == "POST":
        form = ProfileUpdateForm(request.POST, request.FILES, instance=request.user)
        if form.is_valid():
            try:
                form.save()
            except Exception:
                logger.exception(
                    "Profile update failed for user_id=%s; photo_uploaded=%s",
                    request.user.pk,
                    bool(request.FILES.get("profile_photo")),
                )
                messages.error(
                    request,
                    "Profile save nahi ho payi. Photo upload/storage mein dikkat aa sakti hai. "
                    "Photo ko JPG/PNG/WebP aur 2 MB se kam rakhein; agar phir bhi error aaye "
                    "to admin ko batayein.",
                )
                return render(
                    request,
                    "accounts/profile_edit.html",
                    {"form": form, "player": request.user, "next": next_url},
                    status=200,
                )
            messages.success(request, "Player profile update ho gayi.")
            if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
                return redirect(next_url)
            return redirect("accounts:profile")
    else:
        form = ProfileUpdateForm(instance=request.user)
    return render(request, "accounts/profile_edit.html", {"form": form, "player": request.user, "next": next_url})



@login_required
def password_change_view(request):
    if request.method == "POST":
        form = PasswordChangeForm(user=request.user, data=request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, "Password successfully change ho gaya.")
            return redirect("accounts:profile")
    else:
        form = PasswordChangeForm(user=request.user)
    return render(request, "registration/password_change_form.html", {"form": form})


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

from .models import Wallet, WalletTransaction, WithdrawalRequest


@login_required
def wallet_view(request):
    wallet, _created = Wallet.objects.get_or_create(user=request.user)
    from apps.social.models import PlayerShopWallet

    shop_wallet, _ = PlayerShopWallet.objects.get_or_create(user=request.user)
    return render(request, "accounts/wallet.html", {
        "wallet": wallet,
        "shop_wallet": shop_wallet,
    })


@login_required
def wallet_history_view(request):
    wallet, _created = Wallet.objects.get_or_create(user=request.user)
    from apps.social.models import (
        PlayerShopWalletTransaction, ShopPaymentRequest, FanTokenAward, CurrencyGift
    )
    from apps.tournaments.models import Registration, TournamentLedgerEntry
    from django.db.models import Q

    return render(request, "accounts/wallet_history.html", {
        "wallet": wallet,
        "transactions": wallet.transactions.all().order_by("-created_at")[:100],
        "withdrawal_requests": WithdrawalRequest.objects.filter(wallet=wallet).order_by("-created_at")[:50],
        "deposit_requests": wallet.deposit_requests.all().order_by("-created_at")[:50],
        "registration_history": Registration.objects.filter(
            player=request.user
        ).select_related("tournament").order_by("-registered_at")[:100],
        "shop_wallet_transactions": PlayerShopWalletTransaction.objects.filter(
            user=request.user
        ).select_related("wallet").order_by("-created_at")[:100],
        "shop_payment_requests": ShopPaymentRequest.objects.filter(
            user=request.user
        ).order_by("-created_at")[:50],
        "fan_token_awards": FanTokenAward.objects.filter(user=request.user).order_by("-created_at")[:50],
        "fan_token_gifts": CurrencyGift.objects.filter(
            Q(sender=request.user) | Q(recipient=request.user)
        ).select_related("sender", "recipient").order_by("-created_at")[:100],
        "tournament_ledger_entries": TournamentLedgerEntry.objects.filter(
            player=request.user
        ).select_related("tournament", "registration").order_by("-created_at")[:100],
    })



from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import redirect, render

from .forms import DepositRequestForm
from .models import DepositRequest, Wallet, WalletTransaction


@login_required
def deposit_view(request):
    """Create a manual UPI deposit request; credit only after admin verifies bank receipt."""
    import base64
    import io
    import os
    import re
    from urllib.parse import urlencode

    import qrcode

    wallet, _ = Wallet.objects.get_or_create(user=request.user)
    upi_id = os.getenv("FF_ARENA_UPI_ID", "").strip()
    deposit = None
    upi_uri = ""
    qr_data_uri = ""
    submitted_for_verification = False
    form = DepositRequestForm(request.POST or None)

    if request.method == "POST" and request.POST.get("confirm_payment") == "1":
        deposit_id = request.POST.get("deposit_id", "").strip()
        utr = request.POST.get("utr", "").strip()
        deposit = DepositRequest.objects.filter(
            pk=deposit_id, wallet=wallet, status=DepositRequest.Status.PENDING
        ).first()
        if deposit is None:
            messages.error(request, "Pending deposit request nahi mila. Nayi request banayein.")
            form = DepositRequestForm()
        elif not re.fullmatch(r"[A-Za-z0-9-]{6,40}", utr):
            messages.error(request, "UPI app ka valid UTR/transaction reference (6–40 characters) enter karein.")
        elif DepositRequest.objects.filter(payment_reference=utr).exclude(pk=deposit.pk).exists() or WalletTransaction.objects.filter(reference=utr).exists():
            messages.error(request, "Ye UTR pehle use ho chuka hai. Apna naya transaction reference enter karein.")
        else:
            deposit.payment_reference = utr
            deposit.save(update_fields=["payment_reference"])
            submitted_for_verification = True
            messages.success(request, "UTR submit ho gaya. Admin actual bank statement se verify karega; verification se pehle wallet credit nahi hoga.")

    elif request.method == "POST":
        if not upi_id:
            form.add_error(None, "UPI deposit abhi configure nahi hai. Admin se FF_ARENA_UPI_ID set karwayein.")
        if form.is_valid():
            amount = form.cleaned_data["amount"]
            with transaction.atomic():
                wallet = Wallet.objects.select_for_update().get(pk=wallet.pk)
                pending_total = sum(
                    DepositRequest.objects.filter(
                        wallet=wallet, status=DepositRequest.Status.PENDING
                    ).values_list("amount", flat=True),
                    start=Decimal("0.00"),
                )
                if wallet.balance + pending_total + amount > Decimal("5000.00"):
                    form.add_error("amount", "Wallet limit ₹5000 hai. Pending requests bhi limit mein count hongi.")
                else:
                    deposit = DepositRequest.objects.create(wallet=wallet, amount=amount)
                    upi_uri = "upi://pay?" + urlencode({
                        "pa": upi_id,
                        "pn": "FF Arena",
                        "am": f"{amount:.2f}",
                        "cu": "INR",
                        "tn": f"{wallet.wallet_id} deposit {deposit.pk}",
                    })
    if deposit and upi_id and not submitted_for_verification and not deposit.payment_reference:
        upi_uri = "upi://pay?" + urlencode({
            "pa": upi_id, "pn": "FF Arena", "am": f"{deposit.amount:.2f}",
            "cu": "INR", "tn": f"{wallet.wallet_id} deposit {deposit.pk}",
        })
        qr = qrcode.make(upi_uri)
        buffer = io.BytesIO()
        qr.save(buffer, format="PNG")
        qr_data_uri = "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")

    return render(request, "accounts/deposit.html", {
        "form": form, "wallet": wallet, "deposit": deposit, "upi_id": upi_id,
        "upi_uri": upi_uri, "qr_data_uri": qr_data_uri,
        "submitted_for_verification": submitted_for_verification,
    })


@login_required
def withdrawal_view(request):
    messages.info(request, "INR withdrawals are temporarily disabled.")
    return redirect("accounts:wallet")
    wallet, _ = Wallet.objects.get_or_create(user=request.user)
    if request.method == "POST":
        form = WithdrawalRequestForm(request.POST)
        if form.is_valid():
            amount = form.cleaned_data["amount"]
            upi_id = form.cleaned_data["upi_id"]
            with transaction.atomic():
                wallet = Wallet.objects.select_for_update().get(pk=wallet.pk)
                if amount < Decimal("10.00"):
                    form.add_error("amount", "Minimum withdrawal ₹10 hai.")
                elif amount > wallet.balance:
                    form.add_error("amount", "Wallet mein itna available balance nahi hai.")
                elif WithdrawalRequest.objects.filter(
                    wallet=wallet, status=WithdrawalRequest.Status.PENDING,
                ).exists():
                    form.add_error(None, "Aapki ek redeem/withdrawal request pehle se pending hai. Uske complete hone ka wait karein.")
                else:
                    withdrawal = WithdrawalRequest.objects.create(
                        wallet=wallet,
                        amount=amount,
                        upi_id=upi_id,
                    )
                    wallet.balance -= amount
                    wallet.save(update_fields=["balance", "updated_at"])
                    WalletTransaction.objects.create(
                        wallet=wallet,
                        transaction_type=WalletTransaction.TransactionType.WITHDRAWAL,
                        amount=amount,
                        status=WalletTransaction.Status.PENDING,
                        reference=f"WITHDRAW-REQ-{withdrawal.pk}",
                        description=f"Withdrawal request to {upi_id}; awaiting manual UPI payout",
                    )
                    messages.success(request, "Withdrawal request submit ho gayi. Admin UPI transfer verify karke status update karega.")
                    return redirect("accounts:wallet")
    else:
        form = WithdrawalRequestForm(initial={"upi_id": request.user.upi_id})
    withdrawal_requests = WithdrawalRequest.objects.filter(wallet=wallet)[:10]
    return render(request, "accounts/withdrawal.html", {
        "form": form, "wallet": wallet, "withdrawal_requests": withdrawal_requests,
    })
