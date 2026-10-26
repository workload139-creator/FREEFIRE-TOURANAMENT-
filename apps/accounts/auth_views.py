from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth import get_user_model
from django.shortcuts import redirect, render
from django.urls import reverse
from urllib.parse import quote
from django.utils.http import url_has_allowed_host_and_scheme


def login_view(request):
    next_url = request.POST.get("next") or request.GET.get("next", "")

    if request.user.is_authenticated:
        if not (request.user.upi_id or "").strip() and not request.user.upi_qr_code:
            messages.info(request, "Prize receive karne ke liye apni UPI ID ya QR code profile mein add karein.")
            target = reverse("accounts:profile_edit")
            if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
                target += "?next=" + quote(next_url, safe="")
            return redirect(target)
        if next_url and url_has_allowed_host_and_scheme(
            next_url,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            return redirect(next_url)
        return redirect("accounts:profile")

    if request.method == "POST":
        data = request.POST.copy()
        identifier = data.get("username", "").strip()

        # Let players sign in with either their username or registered email.
        if "@" in identifier:
            User = get_user_model()
            user = User.objects.filter(email__iexact=identifier).first()
            if user:
                data["username"] = user.get_username()

        form = AuthenticationForm(request=request, data=data)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            messages.success(request, "Login successful! Welcome back to FF Arena.")
            if not (user.upi_id or "").strip() and not user.upi_qr_code:
                messages.info(request, "Prize receive karne ke liye apni UPI ID ya QR code profile mein add karein.")
                target = reverse("accounts:profile_edit")
                if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
                    target += "?next=" + quote(next_url, safe="")
                return redirect(target)
            if next_url and url_has_allowed_host_and_scheme(
                next_url,
                allowed_hosts={request.get_host()},
                require_https=request.is_secure(),
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
