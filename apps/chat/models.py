from django.conf import settings
from django.db import models
from django.db.models import Q


class Conversation(models.Model):
    user_one = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="conversations_as_user_one"
    )
    user_two = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="conversations_as_user_two"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-updated_at",)
        constraints = [
            models.UniqueConstraint(fields=("user_one", "user_two"), name="chat_unique_conversation_pair"),
            models.CheckConstraint(condition=~Q(user_one=models.F("user_two")), name="chat_no_self_conversation"),
        ]

    def __str__(self):
        return f"Chat #{self.pk}: {self.user_one} / {self.user_two}"

    def includes(self, user):
        return user.pk in (self.user_one_id, self.user_two_id)

    def other_user(self, user):
        if self.user_one_id == user.pk:
            return self.user_two
        if self.user_two_id == user.pk:
            return self.user_one
        return None


class Message(models.Model):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="messages")
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="sent_chat_messages")
    body = models.CharField(max_length=2000)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    read_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        ordering = ("created_at", "pk")

    def __str__(self):
        return f"Message #{self.pk} by {self.sender}"
