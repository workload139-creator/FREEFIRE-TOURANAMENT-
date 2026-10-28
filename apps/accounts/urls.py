from django.urls import path
from django.contrib.auth.decorators import login_required
from django.views.generic import TemplateView

from .email_otp import email_otp_view

from . import view as views

app_name = "accounts"

urlpatterns = [
    path("register/", views.register_view, name="register"),
    path("email-otp/", email_otp_view, name="email_otp"),
    path("profile/", views.profile_view, name="profile"),
    path("settings/", login_required(TemplateView.as_view(template_name="accounts/settings.html")), name="settings"),
    path("profile/edit/", views.profile_edit_view, name="profile_edit"),
    path("password/change/", views.password_change_view, name="password_change"),
    path("wallet/", views.wallet_view, name="wallet"),
    path("wallet/deposit/", views.deposit_view, name="deposit"),
    path("wallet/deposit/automatic/", views.cashfree_deposit_view, name="cashfree_deposit"),
    path("wallet/deposit/cashfree/return/", views.cashfree_return_view, name="cashfree_return"),
    path("wallet/deposit/cashfree/webhook/", views.cashfree_webhook_view, name="cashfree_webhook"),
    path("wallet/withdraw/", views.withdrawal_view, name="withdraw"),
]
