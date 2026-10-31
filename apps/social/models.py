from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.core.storage import PrivateMediaStorage


class FriendRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACCEPTED = "accepted", "Accepted"
        REJECTED = "rejected", "Rejected"

    requester = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="sent_friend_requests",
    )
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="received_friend_requests",
    )
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(fields=("requester", "recipient"), name="social_unique_friend_request_direction"),
            models.CheckConstraint(condition=~Q(requester=models.F("recipient")), name="social_no_self_friend_request"),
        ]

    def __str__(self):
        return f"{self.requester} → {self.recipient} ({self.status})"


class UserBlock(models.Model):
    blocker = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="blocked_users",
    )
    blocked = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="blocked_by_users",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(fields=("blocker", "blocked"), name="social_unique_user_block"),
            models.CheckConstraint(condition=~Q(blocker=models.F("blocked")), name="social_no_self_block"),
        ]

    def __str__(self):
        return f"{self.blocker} blocked {self.blocked}"


class UserReport(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        REVIEWING = "reviewing", "Reviewing"
        RESOLVED = "resolved", "Resolved"
        DISMISSED = "dismissed", "Dismissed"

    class Reason(models.TextChoices):
        HARASSMENT = "harassment", "Harassment or abuse"
        SPAM = "spam", "Spam"
        SCAM = "scam", "Scam or fraud"
        INAPPROPRIATE = "inappropriate", "Inappropriate content"
        OTHER = "other", "Other"

    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="submitted_user_reports",
    )
    reported_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="received_user_reports",
    )
    reason = models.CharField(max_length=20, choices=Reason.choices)
    details = models.TextField(blank=True, max_length=1000)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.OPEN)
    admin_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return f"Report #{self.pk}: {self.reporter} → {self.reported_user}"


class Follow(models.Model):
    follower = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="following_links",
    )
    following = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="follower_links",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(fields=("follower", "following"), name="social_unique_follow"),
            models.CheckConstraint(condition=~Q(follower=models.F("following")), name="social_no_self_follow"),
        ]

    def __str__(self):
        return f"{self.follower} follows {self.following}"


class PhotoPost(models.Model):
    """Image-only community post."""
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="photo_posts")
    photo = models.ImageField(upload_to="community_posts/")
    caption = models.CharField(max_length=180, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_hidden = models.BooleanField(default=False)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return f"Photo post #{self.pk} by {self.author}"


class FFTickSubscription(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending admin verification"
        ACTIVE = "active", "Active"
        REJECTED = "rejected", "Rejected"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="ff_tick_subscriptions")
    amount = models.DecimalField(max_digits=7, decimal_places=2, default=100)
    duration_months = models.PositiveSmallIntegerField(default=3)
    payment_reference = models.CharField(max_length=100, blank=True)
    payment_screenshot = models.ImageField(upload_to="ff_tick_payments/", storage=PrivateMediaStorage(), blank=True, null=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    submitted_at = models.DateTimeField(auto_now_add=True)
    verified_at = models.DateTimeField(blank=True, null=True)
    expires_at = models.DateTimeField(blank=True, null=True)
    verified_by = models.ForeignKey(settings.AUTH_USER_MODEL, blank=True, null=True, on_delete=models.SET_NULL, related_name="verified_ff_tick_payments")
    admin_note = models.CharField(max_length=250, blank=True)

    class Meta:
        ordering = ("-submitted_at",)

    def __str__(self):
        return f"FF Tick - {self.user} - {self.status}"


class PlayerShopWallet(models.Model):
    """Separate non-cash balances; never mixed with the INR wallet."""
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="shop_wallet")
    diamonds = models.PositiveIntegerField(default=0)
    coins = models.PositiveIntegerField(default=0)
    fan_tokens = models.PositiveIntegerField(default=0, help_text="Non-cash tokens earned for every 10 followers; cannot be withdrawn.")
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user} · {self.diamonds} diamonds / {self.coins} coins / {self.fan_tokens} Fan Tokens"


class FanTokenAward(models.Model):
    """One auditable award per follower milestone, preventing repeat farming."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="fan_token_awards")
    follower_milestone = models.PositiveIntegerField(help_text="Follower count milestone, in multiples of 10.")
    quantity = models.PositiveSmallIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(fields=("user", "follower_milestone"), name="social_unique_fan_token_milestone"),
        ]

    def __str__(self):
        return f"{self.user} · {self.quantity} Fan Token(s) at {self.follower_milestone} followers"


class ShopPaymentRequest(models.Model):
    class Product(models.TextChoices):
        DIAMONDS = "diamonds", "Diamonds"
        COINS = "coins", "Coins"
    class Status(models.TextChoices):
        PENDING = "pending", "Pending verification"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="shop_payment_requests")
    product = models.CharField(max_length=12, choices=Product.choices)
    quantity = models.PositiveIntegerField()
    amount = models.DecimalField(max_digits=8, decimal_places=2)
    payment_reference = models.CharField(max_length=100)
    payment_screenshot = models.ImageField(upload_to="shop_payments/", storage=PrivateMediaStorage())
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="reviewed_shop_payments")
    admin_note = models.CharField(max_length=250, blank=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.user} · {self.quantity} {self.product} · {self.status}"


class CurrencyGift(models.Model):
    class Currency(models.TextChoices):
        DIAMONDS = "diamonds", "Diamonds"
        COINS = "coins", "Coins"
        FAN_TOKENS = "fan_tokens", "Fan Tokens"

    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="sent_currency_gifts")
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="received_currency_gifts")
    currency = models.CharField(max_length=12, choices=Currency.choices)
    quantity = models.PositiveIntegerField()
    conversation_id = models.PositiveBigIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.sender} gifted {self.quantity} {self.currency} to {self.recipient}"


class CurrencyWithdrawalRequest(models.Model):
    class Currency(models.TextChoices):
        DIAMONDS = "diamonds", "Diamonds"
        COINS = "coins", "Coins"
    class Status(models.TextChoices):
        PENDING = "pending", "Pending manual UPI payout"
        PAID = "paid", "Paid"
        REJECTED = "rejected", "Rejected and refunded"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="currency_withdrawals")
    currency = models.CharField(max_length=12, choices=Currency.choices)
    quantity = models.PositiveIntegerField()
    amount_inr = models.DecimalField(max_digits=8, decimal_places=2)
    upi_id = models.CharField(max_length=100)
    upi_qr_code = models.ImageField(upload_to="currency_withdrawal_qr/", storage=PrivateMediaStorage(), blank=True, null=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True)
    payout_reference = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    processed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="processed_currency_withdrawals")

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.user} · {self.quantity} {self.currency} · {self.status}"


class DailySpin(models.Model):
    """Auditable daily free reward; one reward record per successful spin."""
    class Currency(models.TextChoices):
        DIAMONDS = "diamonds", "Diamonds"
        COINS = "coins", "Coins"
        FAN_TOKENS = "fan_tokens", "Fan Currency"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="daily_spins")
    currency = models.CharField(max_length=12, choices=Currency.choices)
    quantity = models.PositiveSmallIntegerField()
    spun_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("-spun_at",)

    def __str__(self):
        return f"{self.user} · {self.quantity} {self.currency} · {self.spun_at}"

class PlayerShopWalletTransaction(models.Model):
    """Immutable audit record for every Diamond/Coin/Fan Token balance change."""
    class Currency(models.TextChoices):
        DIAMONDS = "diamonds", "Diamonds"
        COINS = "coins", "Coins"
        FAN_TOKENS = "fan_tokens", "Fan Tokens"

    class Direction(models.TextChoices):
        CREDIT = "credit", "Credit"
        DEBIT = "debit", "Debit"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="shop_wallet_transactions")
    wallet = models.ForeignKey(PlayerShopWallet, on_delete=models.PROTECT, related_name="transactions")
    currency = models.CharField(max_length=12, choices=Currency.choices)
    direction = models.CharField(max_length=8, choices=Direction.choices)
    quantity = models.PositiveIntegerField()
    balance_after = models.PositiveIntegerField()
    source = models.CharField(max_length=32)
    reference = models.CharField(max_length=100, blank=True)
    idempotency_key = models.CharField(max_length=160, unique=True)
    description = models.CharField(max_length=250, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("-created_at", "-pk")

    def __str__(self):
        return f"{self.user} · {self.direction} {self.quantity} {self.currency} · {self.source}"

