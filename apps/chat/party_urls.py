from django.urls import path
from . import party_views, party_voice_views, party_game

urlpatterns = [
    path("party/", party_views.party_home, name="party"),
    path("party/create-room/", party_views.create_party_room, name="party_create_room"),
    path("party/room/<int:room_id>/", party_views.party_room, name="party_room"),
    path("party/room/<int:room_id>/poll/", party_views.party_poll, name="party_poll"),
    path("party/room/<int:room_id>/game/state/", party_game.party_game_state, name="party_game_state"),
    path("party/room/<int:room_id>/game/answer/", party_game.party_game_answer, name="party_game_answer"),
    path("party/room/<int:room_id>/game/decision/", party_game.party_game_decision, name="party_game_decision"),
    path("party/room/<int:room_id>/game/restart-draw/", party_game.party_game_restart_draw, name="party_game_restart_draw"),
    path("party/room/<int:room_id>/voice-token/", party_voice_views.party_voice_token, name="party_voice_token"),
    path("party/create-tournament/", party_views.create_community_tournament, name="party_create_tournament"),
    path("party/tournament/<int:tournament_id>/join/", party_views.join_community_tournament, name="party_join_tournament"),
]
