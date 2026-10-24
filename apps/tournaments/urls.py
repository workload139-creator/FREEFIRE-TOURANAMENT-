```python
from django.urls import path
from . import views

app_name = "tournaments"

urlpatterns = [
    # Tournament list
    path("", views.tournament_list, name="list"),

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

    # Player room
    path(
        "registration/<int:registration_id>/room/",
        views.player_room,
        name="player_room",
    ),
]
```
