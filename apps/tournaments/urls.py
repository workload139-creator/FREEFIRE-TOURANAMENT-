from django.urls import path

from . import views, api_views, self_refund, arena_views

app_name = "tournaments"

urlpatterns = [
    path("api/", api_views.public_tournament_list_api, name="api_list"),
    # Tournament list
    path(
        "",
        views.tournament_list,
        name="list",
    ),

    path("battle-royale/", arena_views.battle_royale_list, name="battle_royale_list"),
    path("diwali-offer/", arena_views.diwali_offer_list, name="diwali_offer_list"),
    path("clash-squad/", arena_views.clash_squad_list, name="clash_squad_list"),

    # Dedicated date-free tournament pages
    path("free-tournament/", views.free_fan_tournament_list, name="free_fan_list"),
    path("unlimited/", views.unlimited_tournament_list, name="unlimited_list"),

    # Public results page
    path("results/", views.results, name="results"),

    # Tournament details
    path(
        "<int:tournament_id>/",
        views.tournament_detail,
        name="detail",
    ),

    # Player self-refund: only available during the final hour before start.
    path("registration/<int:registration_id>/refund/", self_refund.request_tournament_diamond_refund, name="self_refund"),

    # Player registration
    path(
        "<int:tournament_id>/register/",
        views.tournament_register,
        name="register",
    ),

    # Player confirmation
    path(
        "registration/<int:registration_id>/confirm/",
        views.confirm_playing,
        name="confirm_playing",
    ),

    # Player declines the ready check
    path("registration/<int:registration_id>/decline/", views.decline_playing, name="decline_playing"),

    # Player room
    path(
        "registration/<int:registration_id>/room/",
        views.player_room,
        name="player_room",
    ),

    # Admin room management
    path(
        "admin/tournament/<int:tournament_id>/send-room/",
        views.send_room_details,
        name="send_room_details",
    ),
    path(
        "admin/tournament/<int:tournament_id>/room-form/",
        views.admin_room_page,
        name="admin_room_page",
    ),

    # Admin dashboard and kill evidence review
    path(
        "admin/tournament/<int:tournament_id>/dashboard/",
        views.admin_tournament_dashboard,
        name="admin_tournament_dashboard",
    ),
    path("my-registrations/", views.my_registrations, name="my_registrations"),
    path("registration/<int:registration_id>/kill-evidence/", views.kill_submission, name="kill_submission"),
    path("leaderboard/<int:tournament_id>/", views.leaderboard, name="leaderboard"),
    path("admin/ai-assessments/", views.ai_assessment_dashboard, name="admin_ai_assessments"),
    path("admin/ai-sources/", views.ai_source_settings, name="admin_ai_sources"),
    path("admin/kill-review/", views.admin_kill_review, name="admin_kill_review"),
    path("admin/kill-review/<int:submission_id>/retry-ai/", views.retry_ai_kill_review, name="retry_ai_kill_review"),
    path("admin/kill-review/<int:submission_id>/", views.review_kill_submission, name="review_kill_submission"),
]
