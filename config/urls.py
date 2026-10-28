from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.http import HttpResponseForbidden
from django.urls import include, path, re_path
from django.views.static import serve

from apps.core.views import health_check, terms, privacy_policy, refund_policy, fair_play, about

from apps.accounts.auth_views import login_view
from apps.accounts.view import logout_view
from apps.core.views import home
from apps.core.assistant import assistant_view


# Evidence/payment files must not be exposed to unauthenticated visitors.
_PRIVATE_MEDIA_PREFIXES = (
    "kill-evidence/",
    "currency_withdrawal_qr/",
    "player_upi_qr/",
    "shop_payments/",
    "tournament_verification/",
    "ff_tick_payments/",
)


def media_file_serve(request, path):
    """Serve uploaded media in production; protect payout/payment/evidence uploads."""
    normalized_path = path.replace("\\\\", "/").lstrip("/")
    if normalized_path.startswith(_PRIVATE_MEDIA_PREFIXES):
        if not request.user.is_authenticated or not request.user.is_staff:
            return HttpResponseForbidden("Admin login required to view this verification file.")
    return serve(request, normalized_path, document_root=settings.MEDIA_ROOT)


urlpatterns = [
    # Profile pictures are public profile media; keep their existing route.
    re_path(
        r"^media/player_profiles/(?P<path>.*)$",
        serve,
        {"document_root": settings.MEDIA_ROOT / "player_profiles"},
    ),
    # Production DEBUG=False still needs a media route. Sensitive uploads above
    # are served only to logged-in staff; ordinary uploaded media uses this route.
    re_path(r"^media/(?P<path>.*)$", media_file_serve, name="media_file"),
    path("health/", health_check, name="health_check"),
    path("terms/", terms, name="terms"),
    path("privacy/", privacy_policy, name="privacy_policy"),
    path("refund-policy/", refund_policy, name="refund_policy"),
    path("fair-play/", fair_play, name="fair_play"),
    path("about/", about, name="about"),
    path("admin/", admin.site.urls),
    path("accounts/", include("apps.accounts.urls")),
    path("login/", login_view, name="login"),
    path("logout/", logout_view, name="logout"),
    path(
        "password-reset/",
        auth_views.PasswordResetView.as_view(
            template_name="registration/password_reset_form.html",
            email_template_name="registration/password_reset_email.txt",
            subject_template_name="registration/password_reset_subject.txt",
            success_url="/password-reset/done/",
        ),
        name="password_reset",
    ),
    path(
        "password-reset/done/",
        auth_views.PasswordResetDoneView.as_view(
            template_name="registration/password_reset_done.html"
        ),
        name="password_reset_done",
    ),
    path(
        "reset/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            template_name="registration/password_reset_confirm.html",
            success_url="/reset/done/",
        ),
        name="password_reset_confirm",
    ),
    path(
        "reset/done/",
        auth_views.PasswordResetCompleteView.as_view(
            template_name="registration/password_reset_complete.html"
        ),
        name="password_reset_complete",
    ),
    path("tournaments/", include("apps.tournaments.urls")),
    path("friends/", include("apps.social.urls")),
    path("chat/", include("apps.chat.urls")),
    path("assistant/", assistant_view, name="assistant"),
    path("", home, name="home"),
]


if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
