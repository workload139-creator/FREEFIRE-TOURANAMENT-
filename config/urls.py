from django.contrib import admin
from django.urls import include, path

from apps.accounts.view import login_view, logout_view
from apps.core.views import home

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("apps.accounts.urls")),
    path("login/", login_view, name="login"),
    path("logout/", logout_view, name="logout"),
    path("tournaments/", include("apps.tournaments.urls")),
    path("", home, name="home"),
]
