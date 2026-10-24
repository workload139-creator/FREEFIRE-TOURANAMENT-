from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("register/", views.register_view, name="register"),
    path("profile/", views.profile_view, name="profile"),
    path("wallet/", views.wallet_view, name="wallet"),
    path("wallet/deposit/", views.deposit_view, name="deposit"),
]
