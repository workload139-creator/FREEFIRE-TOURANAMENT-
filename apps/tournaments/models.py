
from decimal import Decimal

from django.conf import settings
from django.core.validators import (
    MinValueValidator,
    MaxValueValidator,
)
from django.db import models
from django.db.models import Q


class Tournament(models.Model):

    class Mode(models.TextChoices):
        BR = "BR", "Battle Royale"
        VS = "VS", "Clash Squad VS"

    class VSFormat(models.TextChoices):
        ONE_V_ONE = "1v1", "1 vs 1"
        TWO_V_TWO = "2v2", "2 vs 2"
        THREE_V_THREE = "3v3", "3 vs 3"
        FOUR_V_FOUR = "4v4", "4 vs 4"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        UPCOMING = "upcoming", "Upcoming"
        LIVE = "live", "Live"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    title = models.CharField(max_length=120)

    mode = models.CharField(
        max_length=2,
        choices=Mode.choices,
        default=Mode.BR,
        db_index=True,
    )

    vs_format = models.CharField(
        max_length=3,
        choices=VSFormat.choices,
        blank=True,
        default="",
    )

    description = models.TextField(blank=True)

    entry_fee = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=Decimal("10.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )

    prize_pool = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )

    max_players = models.PositiveSmallIntegerField(
        default=49,
        validators=[
            MinValueValidator(1),
            MaxValueValidator(49),
        ],
    )

    start_time = models.DateTimeField()

    status = models.CharField(
        max_length=15,
        choices=Status.choices,
        default=Status.DRAFT,
        db_index=True,
    )

    room_id = models.CharField(max_length=100, blank=True)
    room_password = models.CharField(max_length=100, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["start_time"]

    def __str__(self):
        return self.title

    @property
    def confirmed_players_count(self):
        return self.registrations.filter(
            status__in=[
                Registration.Status.CONFIRMED,
                Registration.Status.WAITING_READY,
                Registration.Status.READY,
            ],
            payment_verified=True,
        ).count()

    @property
    def is_full(self):
        return self.confirmed_players_count >= self.max_players


class Registration(models.Model):

    class Status(models.TextChoices):
        PENDING_PAYMENT = "pending_payment", "Pending Payment"
        CONFIRMED = "confirmed", "Confirmed"
        WAITING_READY = "waiting_ready", "Waiting for Confirmation"
        READY = "ready", "Ready to Play"
        NOT_PLAYING = "not_playing", "Not Playing"
        CANCELLED = "cancelled", "Cancelled"
        REFUNDED = "refunded", "Refunded"

    tournament = models.ForeignKey(
        Tournament,
        on_delete=models.PROTECT,
        related_name="registrations",
    )

    player = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="tournament_registrations",
    )

    free_fire_uid = models.CharField(max_length=30)

    entry_fee_paid = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )

    payment_verified = models.BooleanField(default=False)

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING_PAYMENT,
        db_index=True,
    )

    room_details_sent = models.BooleanField(default=False)

    ready_deadline = models.DateTimeField(null=True, blank=True)
    ready_confirmed_at = models.DateTimeField(null=True, blank=True)

    refund_processed = models.BooleanField(default=False)
    refund_processed_at = models.DateTimeField(null=True, blank=True)
    refund_reference = models.CharField(
        max_length=100,
        blank=True,
        default="",
    )

    registered_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["registered_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["tournament", "player"],
                name="unique_player_tournament_registration",
            ),
            models.CheckConstraint(
                condition=Q(entry_fee_paid__gte=0),
                name="registration_entry_fee_nonnegative",
            ),
        ]

    def __str__(self):
        return f"{self.player.username} - {self.tournament.title}"

class KillSubmission(models.Model):
    """Evidence submitted by a player; a human admin must approve the final kill count."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending Admin Review"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    registration = models.ForeignKey(
        Registration,
        on_delete=models.PROTECT,
        related_name="kill_submissions",
    )
    player = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="kill_submissions",
    )
    tournament = models.ForeignKey(
        Tournament,
        on_delete=models.PROTECT,
        related_name="kill_submissions",
    )
    registered_uid = models.CharField(max_length=32)
    free_fire_uid = models.CharField(max_length=32)
    history_video = models.FileField(upload_to="kill-evidence/videos/")
    history_image_one = models.ImageField(upload_to="kill-evidence/images/")
    history_image_two = models.ImageField(upload_to="kill-evidence/images/")
    ai_proposed_kills = models.PositiveSmallIntegerField(null=True, blank=True)
    approved_kills = models.PositiveSmallIntegerField(null=True, blank=True)
    proposed_reward = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0.00")
    )
    approved_reward = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0.00")
    )
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    admin_notes = models.TextField(blank=True)
    payout_reference = models.CharField(max_length=100, blank=True, default="")
    submitted_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-submitted_at"]

    def __str__(self):
        return f"{self.player} - {self.tournament} - {self.status}"

