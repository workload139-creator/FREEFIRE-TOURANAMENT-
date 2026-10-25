import hashlib
import hmac
import secrets
import time

from django.conf import settings
from django.contrib import messages
from django.core.mail import send_mail
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods


OTP_TTL_SECONDS = 600
OTP_RESEND_SECONDS = 60
OTP_MAX_ATTEMPTS = 5


def _otp_digest(email, code):
    value = f"{email.lower()}:{code}".encode("utf-8")
    return hmac.new(settings.SECRET_KEY.encode("utf-8"), value, hashlib.sha256).hexdigest()


@require_http_methods(["GET", "POST"])
def email_otp_view(request):
    if request.user.is_authenticated:
        return redirect("accounts:profile")

    now = int(time.time())
    error = ""
    email = request.POST.get("email", "").strip().lower() if request.method == "POST" else ""
    action = request.POST.get("action", "send") if request.method == "POST" else ""

    if request.method == "POST" and action == "send":
        from django.contrib.auth import get_user_model
        User = get_user_model()

        if not email or "@" not in email or "." not in email.rsplit("@", 1)[-1]:
            error = "Sahi email address enter karein."
        elif User.objects.filter(email__iexact=email).exists():
            error = "Is email se account pehle se hai. Login karein."
        elif now - int(request.session.get("email_otp_last_sent", 0)) < OTP_RESEND_SECONDS:
            error = "Naya code bhejne se pehle 60 seconds wait karein."
        else:
            code = f"{secrets.randbelow(1_000_000):06d}"
            try:
                sent = send_mail(
                    subject="Your FF Arena email verification code",
                    message=(
                        f"Your FF Arena verification code is {code}. "
                        "It expires in 10 minutes. Do not share this code with anyone."
                    ),
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[email],
                    fail_silently=False,
                )
                if sent:
                    request.session["email_otp_email"] = email
                    request.session["email_otp_digest"] = _otp_digest(email, code)
                    request.session["email_otp_expires"] = now + OTP_TTL_SECONDS
                    request.session["email_otp_last_sent"] = now
                    request.session["email_otp_attempts"] = 0
                    request.session.modified = True
                    messages.success(request, "Email par OTP bhej diya hai. Spam/Junk folder bhi check karein.")
                    return render(request, "accounts/email_otp.html", {"email": email, "code_sent": True})
                error = "Email nahi bhej paye. SMTP settings check karke dobara try karein."
            except Exception:
                error = "Email send nahi ho saka. Render ki SMTP environment settings check karein."

    elif request.method == "POST" and action == "verify":
        stored_email = request.session.get("email_otp_email", "")
        stored_digest = request.session.get("email_otp_digest", "")
        expires = int(request.session.get("email_otp_expires", 0))
        attempts = int(request.session.get("email_otp_attempts", 0))
        code = request.POST.get("code", "").strip()

        if not stored_email or email != stored_email:
            error = "Pehle isi email par OTP bhejein."
        elif now > expires:
            error = "OTP expire ho gaya. Naya code mangwayein."
        elif attempts >= OTP_MAX_ATTEMPTS:
            error = "Bahut attempts ho gaye. Naya OTP mangwayein."
        elif not code.isdigit() or len(code) != 6 or not hmac.compare_digest(stored_digest, _otp_digest(email, code)):
            request.session["email_otp_attempts"] = attempts + 1
            error = "OTP galat hai. Dobara check karein."
        else:
            request.session["email_otp_verified"] = stored_email
            request.session["email_otp_verified_at"] = now
            for key in ("email_otp_email", "email_otp_digest", "email_otp_expires", "email_otp_attempts"):
                request.session.pop(key, None)
            request.session.modified = True
            messages.success(request, "Email verify ho gaya. Ab account registration complete karein.")
            return redirect("accounts:register")

    return render(request, "accounts/email_otp.html", {
        "email": email or request.session.get("email_otp_email", ""),
        "code_sent": bool(request.session.get("email_otp_digest")),
        "error": error,
    })
