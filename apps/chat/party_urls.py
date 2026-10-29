from django.urls import path
from . import party_views

urlpatterns = [
    path("party/", party_views.party_home, name="party"),
    path("party/create-room/", party_views.create_party_room, name="party_create_room"),
    path("party/room/<int:room_id>/", party_views.party_room, name="party_room"),
    path("party/room/<int:room_id>/poll/", party_views.party_poll, name="party_poll"),
    path("party/create-tournament/", party_views.create_community_tournament, name="party_create_tournament"),
    path("party/tournament/<int:tournament_id>/join/", party_views.join_community_tournament, name="party_join_tournament"),
]
