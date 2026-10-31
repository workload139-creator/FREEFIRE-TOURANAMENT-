import uuid

from django.conf import settings
from django.db import models


def generate_event_key():
    return uuid.uuid4().hex


class PlayerActivityEvent(models.Model):
    """Append-only activity and integrity audit for player-facing workflows."""

    class Category(models.TextChoices):
        PROFILE = "profile", "Profile"
        WALLET = "wallet", "Wallet"
        SHOP = "shop", "Shop"
        WITHDRAWAL = "withdrawal", "Withdrawal"
        TOURNAMENT = "tournament", "Tournament"
        SOCIAL = "social", "Social"
        KILL_REVIEW = "kill_review", "Kill Review"
        SYSTEM = "system", "System"

    class Risk(models.TextChoices):
        INFO = "info", "Info"
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"
        CRITICAL = "critical", "Critical"

    event_key = models.CharField(max_length=32, unique=True, default=generate_event_key)
    player = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="activity_ai_events",
    )
    category = models.CharField(max_length=20, choices=Category.choices, db_index=True)
    event_type = models.CharField(max_length=100, db_index=True)
    object_type = models.CharField(max_length=100, blank=True, db_index=True)
    object_id = models.CharField(max_length=40, blank=True, db_index=True)
    object_status = models.CharField(max_length=32, blank=True, db_index=True)
    summary = models.CharField(max_length=255)
    metadata = models.JSONField(default=dict, blank=True)
    assessment_state = models.CharField(max_length=16, default="queued", db_index=True)
    assessment_summary = models.TextField(blank=True)
    agent_state = models.CharField(max_length=16, default="queued", db_index=True)
    agent_summary = models.TextField(blank=True)
    risk_level = models.CharField(max_length=12, choices=Risk.choices, default=Risk.INFO, db_index=True)
    risk_score = models.PositiveSmallIntegerField(default=0)
    requires_admin_review = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="resolved_activity_ai_events",
    )
    admin_note = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ("-created_at", "-pk")
        indexes = [
            models.Index(fields=("category", "created_at"), name="core_act_cat_created"),
            models.Index(fields=("requires_admin_review", "risk_level", "created_at"), name="core_act_review_risk"),
            models.Index(fields=("player", "created_at"), name="core_act_player_created"),
            models.Index(fields=("object_type", "object_id"), name="core_act_object"),
        ]

    def __str__(self):
        return f"{self.event_type} · {self.object_type} #{self.object_id}"
