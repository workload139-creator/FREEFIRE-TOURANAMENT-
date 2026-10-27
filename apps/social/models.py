from django.conf import settings
from django.db import models
from django.db.models import Q


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
    payment_screenshot = models.ImageField(upload_to="ff_tick_payments/", blank=True, null=True)
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
