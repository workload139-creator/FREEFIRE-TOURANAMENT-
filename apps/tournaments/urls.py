```python
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

    # Registration
    path(
        "<int:tournament_id>/register/",
        views.tournament_register,
        name="register",
    ),

    # Player confirmation and room
    path(
        "registration/<int:registration_id>/confirm/",
        views.confirm_playing,
        name="confirm_playing",
    ),
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

    # Admin dashboard
    path(
        "admin/tournament/<int:tournament_id>/dashboard/",
        views.admin_tournament_dashboard,
        name="admin_tournament_dashboard",
    ),
]
```
