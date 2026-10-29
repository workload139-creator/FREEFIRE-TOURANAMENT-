from django.urls import path

from . import views, party_views

app_name = "chat"

urlpatterns = [
    path("", views.chat_home, name="home"),
    path("with/<int:user_id>/", views.open_chat, name="open"),
    path("<int:conversation_id>/", views.conversation_detail, name="conversation"),
    path("<int:conversation_id>/poll/", views.poll_messages, name="poll"),
    path("party/", party_views.party_home, name="party"),
    path("party/create-room/", party_views.create_party_room, name="party_create_room"),
    path("party/room/<int:room_id>/", party_views.party_room, name="party_room"),
    path("party/room/<int:room_id>/poll/", party_views.party_poll, name="party_poll"),
    path("party/create-tournament/", party_views.create_community_tournament, name="party_create_tournament"),
    path("party/tournament/<int:tournament_id>/join/", party_views.join_community_tournament, name="party_join_tournament"),
]
