from django.urls import path

from . import views

app_name = "social"

urlpatterns = [
    path("", views.friends_home, name="home"),
    path("feed/", views.community_feed, name="feed"),
    path("ff-tick/", views.ff_tick_view, name="ff_tick"),\n    path("shop/", views.shop_view, name="shop"),
    path("follow/<int:user_id>/", views.toggle_follow, name="toggle_follow"),
    path("player/<int:user_id>/", views.player_profile, name="player_profile"),
    path("followers/", views.follow_lists, {"list_type": "followers"}, name="followers"),
    path("following/", views.follow_lists, {"list_type": "following"}, name="following"),
    path("request/<int:user_id>/send/", views.send_friend_request, name="send_request"),
    path("request/<int:request_id>/<str:action>/", views.handle_friend_request, name="handle_request"),
    path("request/<int:request_id>/cancel/", views.cancel_friend_request, name="cancel_request"),
    path("friend/<int:user_id>/remove/", views.remove_friend, name="remove_friend"),
    path("user/<int:user_id>/block/", views.block_user, name="block_user"),
    path("user/<int:user_id>/unblock/", views.unblock_user, name="unblock_user"),
    path("user/<int:user_id>/report/", views.report_user, name="report_user"),
]
