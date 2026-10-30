
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

    class BRFormat(models.TextChoices):
        SOLO = "solo", "Solo"
        DUO = "duo", "Duo"
        SQUAD = "squad", "Squad"

    class VSFormat(models.TextChoices):
        ONE_V_ONE = "1v1", "1 vs 1"
        TWO_V_TWO = "2v2", "2 vs 2"
        THREE_V_THREE = "3v3", "3 vs 3"
        FOUR_V_FOUR = "4v4", "4 vs 4"

    class GenderCategory(models.TextChoices):
        OPEN = "open", "Open to All"
        BOYS = "boys", "Boys Only"
        GIRLS = "girls", "Girls Only"
        GIRLS_VS_BOYS = "girls_vs_boys", "Girls vs Boys"

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

    br_format = models.CharField(max_length=8, choices=BRFormat.choices, blank=True, default="", help_text="Battle Royale format: Solo, Duo or Squad.")

    vs_format = models.CharField(
        max_length=3,
        choices=VSFormat.choices,
        blank=True,
        default="",
    )

    gender_category = models.CharField(
        max_length=20, choices=GenderCategory.choices, default=GenderCategory.OPEN,
        db_index=True, help_text="Choose Open, Boys Only, Girls Only, or Girls vs Boys event."
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

    # Unlimited BR series: each format-sized round gets its own leaderboard.
    is_unlimited_br = models.BooleanField(default=False)
    # Dedicated no-date free arena: one entry per player per rolling 24 hours.
    is_free_fan_tournament = models.BooleanField(default=False, db_index=True)
    winner_coins_prize = models.PositiveIntegerField(default=20, help_text="Non-cash Coins paid to the winner of the free fan tournament.")
    free_winner_coins_awarded = models.BooleanField(default=False)
    auto_start_at_capacity = models.BooleanField(default=False)
    auto_reopen = models.BooleanField(default=False)
    live_notification_sent_at = models.DateTimeField(null=True, blank=True)
    live_notification_status = models.CharField(max_length=20, default="pending", db_index=True)
    series_root = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="series_rounds",
    )

    # Admin-selected winner receives the admin-configured prize_pool into their internal wallet once.
    winner_uid = models.CharField(max_length=30, blank=True, default="")
    winner_team_uids = models.TextField(blank=True, default="", help_text="BR winning team ke registered Free Fire UIDs; har line ya comma mein ek UID. Har eligible player ko 10 Fan Tokens + 50 Coins.")
    winner_prize_paid = models.BooleanField(default=False)
    winner_prize_reference = models.CharField(max_length=100, blank=True, default="")

    # Kill-based prize batch is an internal ledger distribution, not a bank transfer.
    kill_prize_distributed = models.BooleanField(default=False)
    kill_prize_pool = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    kill_prize_reference = models.CharField(max_length=100, blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["start_time"]

    def __str__(self):
        return self.title

    @property
    def confirmed_players_count(self):
        from django.db.models import Q

        return self.registrations.filter(
            Q(
                status=Registration.Status.PENDING_PAYMENT,
                entry_fee_paid__gt=0,
            )
            | Q(
                status__in=[
                    Registration.Status.CONFIRMED,
                    Registration.Status.WAITING_READY,
                    Registration.Status.READY,
                ],
                payment_verified=True,
            )
        ).count()

    @property
    def paid_players_count(self):
        return self.registrations.filter(
            payment_verified=True,
            status__in=[
                Registration.Status.CONFIRMED,
                Registration.Status.WAITING_READY,
                Registration.Status.READY,
            ],
        ).count()

    @property
    def is_full(self):
        return self.confirmed_players_count >= self.max_players


class UnlimitedTournament(Tournament):
    """Separate admin section for the repeating 49-player paid BR series."""

    class Meta:
        proxy = True
        verbose_name = "BR Unlimited Tournament"
        verbose_name_plural = "BR Unlimited Tournaments"


class FreeFanTournament(Tournament):
    """Separate admin section for the recurring free 49-player fan-currency arena."""

    class Meta:
        proxy = True
        verbose_name = "Free Fan Tournament"
        verbose_name_plural = "Free Fan Tournaments"


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

    # Required at form level for Girls vs Boys events; visible to admins only.
    verification_photo = models.ImageField(upload_to="tournament_verification/", blank=True, null=True, help_text="Private registration selfie for admin review in Girls vs Boys tournaments.")

    entry_fee_paid = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )

    payment_verified = models.BooleanField(default=False)
    payment_method = models.CharField(
        max_length=12,
        choices=(("upi", "UPI payment"), ("diamonds", "Diamonds"), ("coins", "Coins"), ("fan_tokens", "Fan Tokens"), ("free", "Free entry")),
        default="upi",
        db_index=True,
    )
    currency_amount = models.PositiveIntegerField(default=0, help_text="Amount of Diamonds, Coins, or Fan Tokens consumed for entry.")
    # Player-entered UPI UTR; registration stays pending until admin checks actual receipt.
    payment_reference = models.CharField(max_length=100, blank=True, default="", db_index=True)
    payment_submitted_at = models.DateTimeField(null=True, blank=True)

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING_PAYMENT,
        db_index=True,
    )

    room_details_sent = models.BooleanField(default=False)
    # Server-assigned team slots are filled when the admin creates/releases the room.
    team_number = models.PositiveSmallIntegerField(null=True, blank=True, db_index=True)
    team_position = models.PositiveSmallIntegerField(null=True, blank=True)

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


class TournamentLedgerEntry(models.Model):
    """Immutable-style audit trail for entry payments, Diamond rewards and refunds per tournament."""
    class EntryType(models.TextChoices):
        ENTRY = "entry", "Entry Payment"
        REWARD = "reward", "AI / Tournament Reward"
        REFUND = "refund", "Refund"
        ADJUSTMENT = "adjustment", "Admin Adjustment"

    class Currency(models.TextChoices):
        INR = "inr", "INR"
        DIAMONDS = "diamonds", "Diamonds"
        COINS = "coins", "Coins"
        FAN_TOKENS = "fan_tokens", "Fan Tokens"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        COMPLETED = "completed", "Completed"
        REJECTED = "rejected", "Rejected"

    tournament = models.ForeignKey(Tournament, on_delete=models.PROTECT, related_name="ledger_entries")
    player = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="tournament_ledger_entries")
    registration = models.ForeignKey(Registration, on_delete=models.PROTECT, null=True, blank=True, related_name="ledger_entries")
    entry_type = models.CharField(max_length=12, choices=EntryType.choices, db_index=True)
    currency = models.CharField(max_length=12, choices=Currency.choices)
    quantity = models.PositiveIntegerField(default=0)
    amount_inr = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.COMPLETED, db_index=True)
    reference = models.CharField(max_length=100, blank=True, db_index=True)
    description = models.CharField(max_length=250, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("-created_at", "-pk")

    def __str__(self):
        return f"{self.tournament} · {self.player} · {self.get_entry_type_display()} · {self.quantity} {self.currency}"

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
    ai_confidence = models.CharField(max_length=10, blank=True, default="")
    ai_uid_matches = models.BooleanField(null=True, blank=True)
    ai_review_notes = models.TextField(blank=True)
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
    payout_reference = models.CharField(
        max_length=100, blank=True, default="",
        help_text="After sending prize manually to the player's UPI ID/QR, enter the real UPI transaction reference here and use the admin action to mark it paid.",
    )
    class PayoutStatus(models.TextChoices):
        PENDING = "pending", "Pending Manual UPI Payout"
        PAID = "paid", "Paid by UPI"
    payout_status = models.CharField(max_length=10, choices=PayoutStatus.choices, default=PayoutStatus.PENDING, db_index=True)
    payout_paid_at = models.DateTimeField(null=True, blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-submitted_at"]

    def __str__(self):
        return f"{self.player} - {self.tournament} - {self.status}"

