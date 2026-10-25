from django.urls import path

from . import view as views

app_name = "accounts"

urlpatterns = [
    path("register/", views.register_view, name="register"),
    path("email-otp/", __import__("apps.accounts.email_otp", fromlist=["email_otp_view"]).email_otp_view, name="email_otp"),
    path("profile/", views.profile_view, name="profile"),
    path("password/change/", views.password_change_view, name="password_change"),
    path("wallet/", views.wallet_view, name="wallet"),
    path("wallet/deposit/", views.deposit_view, name="deposit"),
    path("wallet/withdraw/", views.withdrawal_view, name="withdraw"),
]
