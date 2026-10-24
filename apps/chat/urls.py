from django.urls import path

from . import views

app_name = "chat"

urlpatterns = [
    path("", views.chat_home, name="home"),
    path("with/<int:user_id>/", views.open_chat, name="open"),
    path("<int:conversation_id>/", views.conversation_detail, name="conversation"),
    path("<int:conversation_id>/poll/", views.poll_messages, name="poll"),
]
