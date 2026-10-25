from django.urls import path

from .email_otp import email_otp_view

from . import view as views

app_name = "accounts"

urlpatterns = [
    path("register/", views.register_view, name="register"),
    path("email-otp/", email_otp_view, name="email_otp"),
    path("profile/", views.profile_view, name="profile"),
    path("profile/edit/", views.profile_edit_view, name="profile_edit"),
    path("password/change/", views.password_change_view, name="password_change"),
    path("wallet/", views.wallet_view, name="wallet"),
    path("wallet/deposit/", views.deposit_view, name="deposit"),
    path("wallet/withdraw/", views.withdrawal_view, name="withdraw"),
    path("wallet/cashfree/return/", views.cashfree_return_view, name="cashfree_return"),
    path("wallet/cashfree/webhook/", views.cashfree_webhook_view, name="cashfree_webhook"),
]
