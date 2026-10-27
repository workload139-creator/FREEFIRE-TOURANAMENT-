
from django.urls import path

from . import views

app_name = "tournaments"

urlpatterns = [
    # Tournament list
    path(
        "",
        views.tournament_list,
        name="list",
    ),

    # Public results page
    path("results/", views.results, name="results"),

    # Tournament details
    path(
        "<int:tournament_id>/",
        views.tournament_detail,
        name="detail",
    ),

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
    path("admin/kill-review/", views.admin_kill_review, name="admin_kill_review"),
    path("admin/kill-review/<int:submission_id>/retry-ai/", views.retry_ai_kill_review, name="retry_ai_kill_review"),
    path("admin/kill-review/<int:submission_id>/", views.review_kill_submission, name="review_kill_submission"),
]
