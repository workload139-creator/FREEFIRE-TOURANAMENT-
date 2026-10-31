"""Persistent state for the separate Live Kill and Reward AI agent pools."""
import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.core.storage import PrivateMediaStorage


class LiveAIAgentSlot(models.Model):
    """One lightweight per-player logical slot; compute is supplied by shared workers."""

    class Kind(models.TextChoices):
        LIVE = "live", "Live Kill AI"
        PAYMENT = "payment", "Payment & Reward AI"

    class State(models.TextChoices):
        WAITING = "waiting", "Waiting for stream"
        CONNECTED = "connected", "Connected"
        PROCESSING = "processing", "Processing"
        DEGRADED = "degraded", "Worker issue"
        STOPPED = "stopped", "Stopped"

    tournament = models.ForeignKey("tournaments.Tournament", on_delete=models.PROTECT, related_name="live_ai_slots")
    registration = models.ForeignKey("tournaments.Registration", on_delete=models.PROTECT, related_name="live_ai_slots")
    session = models.ForeignKey("tournaments.TournamentLiveSession", on_delete=models.PROTECT, related_name="ai_slots")
    kind = models.CharField(max_length=12, choices=Kind.choices)
    slot_number = models.PositiveSmallIntegerField()
    state = models.CharField(max_length=12, choices=State.choices, default=State.WAITING, db_index=True)
    last_heartbeat_at = models.DateTimeField(null=True, blank=True)
    frames_seen = models.PositiveBigIntegerField(default=0)
    detections_seen = models.PositiveIntegerField(default=0)
    last_error = models.CharField(max_length=250, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("tournament_id", "kind", "slot_number")
        constraints = [
            models.UniqueConstraint(fields=("session", "kind"), name="unique_live_ai_kind_per_session"),
            models.UniqueConstraint(fields=("tournament", "kind", "slot_number"), name="unique_live_ai_slot_per_tournament"),
            models.CheckConstraint(condition=Q(slot_number__gte=1) & Q(slot_number__lte=50), name="live_ai_slot_number_1_50"),
        ]

    def __str__(self):
        return f"{self.get_kind_display()} #{self.slot_number} · registration {self.registration_id}"


class LiveKillEvent(models.Model):
    """A single candidate kill. OCR detections are evidence, never proof by themselves."""

    class Status(models.TextChoices):
        REVIEW = "review", "Needs Admin Review"
        VERIFIED = "verified", "Verified"
        REJECTED = "rejected", "Rejected"

    event_uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    tournament = models.ForeignKey("tournaments.Tournament", on_delete=models.PROTECT, related_name="live_kill_events")
    registration = models.ForeignKey("tournaments.Registration", on_delete=models.PROTECT, related_name="live_kill_events")
    session = models.ForeignKey("tournaments.TournamentLiveSession", on_delete=models.PROTECT, related_name="kill_events")
    event_fingerprint = models.CharField(max_length=64, unique=True)
    match_id = models.CharField(max_length=100, blank=True, db_index=True)
    kill_at = models.DateTimeField(null=True, blank=True, db_index=True)
    detected_text = models.TextField(blank=True)
    confidence = models.DecimalField(max_digits=5, decimal_places=4, default=0)
    evidence_image = models.ImageField(upload_to="live-kill-candidates/", storage=PrivateMediaStorage(), blank=True, null=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.REVIEW, db_index=True)
    review_reason = models.CharField(max_length=250, blank=True)
    reward_reference = models.CharField(max_length=120, blank=True, unique=True, null=True)
    reward_payload = models.JSONField(default=dict, blank=True)
    detected_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="reviewed_live_kill_events")

    class Meta:
        ordering = ("-detected_at",)
        indexes = [
            models.Index(fields=("tournament", "registration", "status"), name="live_kill_review_idx"),
        ]

    def __str__(self):
        return f"Live kill candidate {self.event_uuid} · {self.registration.free_fire_uid}"
