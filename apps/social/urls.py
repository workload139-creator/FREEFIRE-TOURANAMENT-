from django.urls import path

from . import views

app_name = "social"

urlpatterns = [
    path("", views.friends_home, name="home"),
    path("request/<int:user_id>/send/", views.send_friend_request, name="send_request"),
    path("request/<int:request_id>/<str:action>/", views.handle_friend_request, name="handle_request"),
    path("friend/<int:user_id>/remove/", views.remove_friend, name="remove_friend"),
    path("user/<int:user_id>/block/", views.block_user, name="block_user"),
    path("user/<int:user_id>/unblock/", views.unblock_user, name="unblock_user"),
    path("user/<int:user_id>/report/", views.report_user, name="report_user"),
]
