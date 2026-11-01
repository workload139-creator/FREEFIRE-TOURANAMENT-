from django.urls import path
from django.contrib.auth.decorators import login_required
from django.views.generic import TemplateView

from .email_otp import email_otp_view

from . import view as views
from . import native_api

app_name = "accounts"

urlpatterns = [
    path("api/me/", native_api.native_profile_api, name="native_profile_api"),
    path("api/wallet/", native_api.native_wallet_api, name="native_wallet_api"),
    path("register/", views.register_view, name="register"),
    path("email-otp/", email_otp_view, name="email_otp"),
    path("profile/", views.profile_view, name="profile"),
    path("settings/", login_required(TemplateView.as_view(template_name="accounts/settings.html")), name="settings"),
    path("profile/edit/", views.profile_edit_view, name="profile_edit"),
    path("password/change/", views.password_change_view, name="password_change"),
    path("wallet/", views.wallet_view, name="wallet"),
    path("wallet/history/", views.wallet_history_view, name="wallet_history"),
    path("wallet/deposit/", views.deposit_view, name="deposit"),
    path("wallet/withdraw/", views.withdrawal_view, name="withdraw"),
]
