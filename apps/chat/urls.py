from django.urls import path

from . import views

app_name = "chat"

urlpatterns = [
    path("", views.chat_home, name="home"),
    path("with/<int:user_id>/", views.open_chat, name="open"),
    path("<int:conversation_id>/", views.conversation_detail, name="conversation"),
    path("<int:conversation_id>/poll/", views.poll_messages, name="poll"),
    path("party/", __import__("apps.chat.party_views", fromlist=["party_home"]).party_home, name="party"),
    path("party/create-room/", __import__("apps.chat.party_views", fromlist=["create_party_room"]).create_party_room, name="party_create_room"),
    path("party/room/<int:room_id>/", __import__("apps.chat.party_views", fromlist=["party_room"]).party_room, name="party_room"),
    path("party/room/<int:room_id>/poll/", __import__("apps.chat.party_views", fromlist=["party_poll"]).party_poll, name="party_poll"),
    path("party/create-tournament/", __import__("apps.chat.party_views", fromlist=["create_community_tournament"]).create_community_tournament, name="party_create_tournament"),
    path("party/tournament/<int:tournament_id>/join/", __import__("apps.chat.party_views", fromlist=["join_community_tournament"]).join_community_tournament, name="party_join_tournament"),
]
