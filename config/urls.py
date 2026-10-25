from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path, re_path
from django.views.static import serve

from apps.core.views import health_check

from apps.accounts.auth_views import login_view
from apps.accounts.view import logout_view
from apps.core.views import home
from apps.core.assistant import assistant_view

urlpatterns = [
    re_path(
        r"^media/player_profiles/(?P<path>.*)$",
        serve,
        {"document_root": settings.MEDIA_ROOT / "player_profiles"},
    ),
    path("health/", health_check, name="health_check"),
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
