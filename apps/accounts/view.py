from django.contrib import messages
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from decimal import Decimal
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
        form = PlayerRegistrationForm(request.POST)
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
                    f"Account successfully created! Aapka username: {final_username}. Email verified hai; phone aur Free Fire UID verification abhi pending hain.",
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
            "deposit_requests": wallet.deposit_requests.all()[:10],
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
def cashfree_deposit_view(request):
    """Start a server-created Cashfree order; never credit on browser redirect alone."""
    import os
    import uuid

    from .cashfree import CashfreeError, _config, create_order

    wallet, _ = Wallet.objects.get_or_create(user=request.user)
    form = DepositRequestForm(request.POST or None)
    if request.method == "POST":
        try:
            _app_id, _secret, mode, _base = _config()
        except CashfreeError as exc:
            form.add_error(
                None,
                "Automatic payment abhi setup nahi hai. Admin ko Cashfree sandbox keys Render Environment mein add karni hongi.",
            )
            return render(request, "accounts/deposit.html", {
                "form": form,
                "wallet": wallet,
                "gateway_only": True,
                "gateway_configured": False,
            })

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
                    return render(request, "accounts/deposit.html", {
                        "form": form,
                        "wallet": wallet,
                        "gateway_only": True,
                        "gateway_configured": True,
                    })
                order_id = f"ffw_{request.user.pk}_{uuid.uuid4().hex[:24]}"
                deposit = DepositRequest.objects.create(
                    wallet=wallet,
                    amount=amount,
                    payment_reference=order_id,
                )

            try:
                order = create_order(
                    order_id=order_id,
                    amount=amount,
                    user=request.user,
                    return_url=request.build_absolute_uri(
                        reverse("accounts:cashfree_return")
                    ),
                    notify_url=request.build_absolute_uri(
                        reverse("accounts:cashfree_webhook")
                    ),
                )
                payment_session_id = order.get("payment_session_id", "")
                if not payment_session_id:
                    raise CashfreeError("Cashfree ne payment session return nahi kiya.")
            except CashfreeError:
                deposit.status = DepositRequest.Status.REJECTED
                deposit.save(update_fields=["status"])
                form.add_error(
                    None,
                    "Cashfree order nahi ban saka. Keys, sender account aur sandbox setup check karein; wallet se paisa nahi kata.",
                )
                return render(request, "accounts/deposit.html", {
                    "form": form,
                    "wallet": wallet,
                    "gateway_only": True,
                    "gateway_configured": True,
                })

            return render(request, "accounts/cashfree_checkout.html", {
                "amount": amount,
                "order_id": order_id,
                "payment_session_id": payment_session_id,
                "cashfree_mode": "production" if mode == "production" else "sandbox",
            })

    return render(request, "accounts/deposit.html", {
        "form": form,
        "wallet": wallet,
        "gateway_only": True,
        "gateway_configured": True,
    })


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
