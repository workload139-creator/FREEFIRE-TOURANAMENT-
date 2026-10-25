from django.contrib import messages
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from decimal import Decimal
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm
from django.db import IntegrityError, transaction
from django.shortcuts import redirect, render
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
        form = PlayerRegistrationForm(request.POST)
        if form.is_valid() and form.cleaned_data["email"].lower() != verified_email.lower():
            form.add_error("email", "Wahi email use karein jise abhi OTP se verify kiya hai.")
        if form.is_valid():
            try:
                with transaction.atomic():
                    user = form.save(commit=False)
                    user.phone_verified = False
                    user.uid_verified = False
                    user.save()

                request.session.pop("email_otp_verified", None)
                request.session.pop("email_otp_verified_at", None)
                login(request, user)

                messages.success(
                    request,
                    "Account successfully created. Email verified hai; phone aur Free Fire UID verification abhi pending hain.",
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
        "followers_count": Follow.objects.filter(following=request.user).count(),
        "following_count": Follow.objects.filter(follower=request.user).count(),
    })


@login_required
def profile_edit_view(request):
    if request.method == "POST":
        form = ProfileUpdateForm(request.POST, request.FILES, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Player profile update ho gayi.")
            return redirect("accounts:profile")
    else:
        form = ProfileUpdateForm(instance=request.user)
    return render(request, "accounts/profile_edit.html", {"form": form, "player": request.user})



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
    wallet, created = Wallet.objects.get_or_create(
        user=request.user,
    )

    transactions = wallet.transactions.all()[:50]
    withdrawal_requests = WithdrawalRequest.objects.filter(wallet=wallet)[:10]

    return render(
        request,
        "accounts/wallet.html",
        {
            "wallet": wallet,
            "transactions": transactions,
            "withdrawal_requests": withdrawal_requests,
        },
    )



from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import redirect, render

from .forms import DepositRequestForm
from .models import DepositRequest, Wallet, WalletTransaction


@login_required
def deposit_view(request):
    import os
    import uuid
    from django.urls import reverse
    from .cashfree import CashfreeError, create_order

    wallet, _ = Wallet.objects.get_or_create(user=request.user)

    if request.method == "POST":
        form = DepositRequestForm(request.POST)
        if form.is_valid():
            amount = form.cleaned_data["amount"]
            with transaction.atomic():
                wallet = Wallet.objects.select_for_update().get(pk=wallet.pk)
                pending_total = sum(
                    DepositRequest.objects.filter(
                        wallet=wallet,
                        status=DepositRequest.Status.PENDING,
                    ).values_list("amount", flat=True),
                    start=Decimal("0.00"),
                )
                if wallet.balance + pending_total + amount > Decimal("5000.00"):
                    form.add_error(
                        "amount",
                        "Wallet limit ₹5000 hai. Pending requests bhi limit mein count hongi.",
                    )
                    return render(request, "accounts/deposit.html", {"form": form, "wallet": wallet})

                order_id = "ffdep_" + uuid.uuid4().hex
                deposit = form.save(commit=False)
                deposit.wallet = wallet
                deposit.payment_reference = order_id
                deposit.save()

            return_url = request.build_absolute_uri(reverse("accounts:cashfree_return")) + "?order_id={order_id}"
            notify_url = request.build_absolute_uri(reverse("accounts:cashfree_webhook"))
            try:
                order = create_order(
                    order_id=order_id,
                    amount=amount,
                    user=request.user,
                    return_url=return_url,
                    notify_url=notify_url,
                )
                session_id = order.get("payment_session_id")
                if not session_id:
                    raise CashfreeError("Cashfree ne payment session nahi diya.")
            except CashfreeError as exc:
                deposit.status = DepositRequest.Status.REJECTED
                deposit.save(update_fields=["status"])
                messages.error(request, str(exc))
                return redirect("accounts:deposit")

            return render(request, "accounts/cashfree_checkout.html", {
                "amount": amount,
                "order_id": order_id,
                "payment_session_id": session_id,
                "cashfree_mode": os.getenv("CASHFREE_MODE", "sandbox").strip().lower(),
            })
    else:
        form = DepositRequestForm()

    return render(request, "accounts/deposit.html", {"form": form, "wallet": wallet})


def _finalize_cashfree_deposit(order_id):
    from django.core.exceptions import ValidationError
    from .cashfree import CashfreeError, verify_paid_order
    from .services import credit_verified_deposit

    deposit = DepositRequest.objects.select_related("wallet", "wallet__user").filter(
        payment_reference=order_id
    ).first()
    if deposit is None:
        return "unknown"
    if deposit.status == DepositRequest.Status.APPROVED:
        return "paid"

    if not verify_paid_order(order_id, deposit.amount):
        return "pending"

    with transaction.atomic():
        deposit = DepositRequest.objects.select_for_update().select_related(
            "wallet", "wallet__user"
        ).get(pk=deposit.pk)
        if deposit.status == DepositRequest.Status.APPROVED:
            return "paid"

        existing = WalletTransaction.objects.filter(reference=order_id).first()
        if existing:
            if (
                existing.wallet_id == deposit.wallet_id
                and existing.amount == deposit.amount
                and existing.status == WalletTransaction.Status.COMPLETED
            ):
                deposit.status = DepositRequest.Status.APPROVED
                deposit.save(update_fields=["status"])
                return "paid"
            raise CashfreeError("Payment reference pehle se kisi doosre transaction mein use hai.")

        try:
            credit_verified_deposit(
                user=deposit.wallet.user,
                amount=deposit.amount,
                payment_reference=order_id,
            )
        except ValidationError as exc:
            raise CashfreeError(str(exc)) from exc
        deposit.status = DepositRequest.Status.APPROVED
        deposit.save(update_fields=["status"])
        return "paid"


@login_required
def cashfree_return_view(request):
    from django.shortcuts import render
    from .cashfree import CashfreeError

    order_id = request.GET.get("order_id", "").strip()
    status_message = "Payment pending hai. Bank/Cashfree confirmation aane par wallet update hoga."
    if not order_id or len(order_id) > 50:
        status_message = "Order ID valid nahi hai."
    else:
        deposit = DepositRequest.objects.filter(
            payment_reference=order_id, wallet__user=request.user
        ).first()
        if deposit is None:
            status_message = "Yeh order aapke account se match nahi hua."
        elif deposit.status == DepositRequest.Status.APPROVED:
            status_message = "Payment verified hai. Wallet credit ho chuka hai."
        else:
            try:
                result = _finalize_cashfree_deposit(order_id)
                if result == "paid":
                    status_message = "Payment verified hai. Wallet credit ho chuka hai."
                elif result == "pending":
                    status_message = "Payment abhi confirm nahi hua. Kuch der baad wallet dobara check karein."
                else:
                    status_message = "Payment order nahi mila. Support se contact karein."
            except CashfreeError:
                status_message = "Payment abhi verify nahi ho saka. Wallet balance tabhi badhega jab Cashfree confirmation mil jayegi."
    return render(request, "accounts/cashfree_result.html", {
        "order_id": order_id,
        "status_message": status_message,
    })


@csrf_exempt
@require_POST
def cashfree_webhook_view(request):
    import json
    from .cashfree import CashfreeError, verify_webhook_signature

    signature = request.headers.get("x-webhook-signature", "")
    timestamp = request.headers.get("x-webhook-timestamp", "")
    try:
        if not verify_webhook_signature(request.body, timestamp, signature):
            return HttpResponse("Invalid signature", status=400)
        payload = json.loads(request.body.decode("utf-8"))
        order_id = payload.get("data", {}).get("order", {}).get("order_id", "")
        if not order_id:
            return HttpResponse("Ignored", status=200)
        _finalize_cashfree_deposit(order_id)
        return HttpResponse("OK", status=200)
    except (ValueError, UnicodeDecodeError):
        return HttpResponse("Invalid payload", status=400)
    except CashfreeError:
        return HttpResponse("Verification temporarily failed", status=500)



@login_required
def withdrawal_view(request):
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
