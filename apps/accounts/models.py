
from decimal import Decimal
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.utils import timezone


class User(AbstractUser):
    phone_number = models.CharField(
        max_length=15, unique=True, null=True, blank=True
    )
    phone_verified = models.BooleanField(default=False)
    profile_photo = models.ImageField(upload_to="player_profiles/", blank=True, null=True)

    free_fire_uid = models.CharField(
        max_length=32, unique=True, null=True, blank=True
    )
    uid_verified = models.BooleanField(default=False)

    upi_id = models.CharField(max_length=100, blank=True)
    upi_verified = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_seen = models.DateTimeField(null=True, blank=True, db_index=True)

    @property
    def is_online(self):
        return self.last_seen is not None and timezone.now() - self.last_seen <= timedelta(minutes=2)

    def __str__(self):
        return self.username


class Wallet(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="wallet",
    )
    balance = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def wallet_id(self):
        """Player wallet ID derived from the player's profile/user ID, not a UPI address."""
        return f"FFW-{self.user_id:06d}" if self.user_id else "FFW-PENDING"

    def __str__(self):
        return f"{self.wallet_id} · {self.user} - ₹{self.balance}"


class WalletTransaction(models.Model):
    class TransactionType(models.TextChoices):
        DEPOSIT = "deposit", "Deposit"
        WITHDRAWAL = "withdrawal", "Withdrawal"
        ENTRY_FEE = "entry_fee", "Tournament Entry Fee"
        REFUND = "refund", "Refund"
        PRIZE = "prize", "Tournament Prize"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    wallet = models.ForeignKey(
        Wallet,
        on_delete=models.PROTECT,
        related_name="transactions",
    )
    transaction_type = models.CharField(
        max_length=20,
        choices=TransactionType.choices,
    )
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    status = models.CharField(
        max_length=12,
        choices=Status.choices,
        default=Status.PENDING,
    )
    reference = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        unique=True,
    )
    description = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return (
            f"{self.wallet.user} - "
            f"{self.transaction_type} - ₹{self.amount}"
        )


class DepositRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending Verification"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    wallet = models.ForeignKey(
        Wallet,
        on_delete=models.PROTECT,
        related_name="deposit_requests",
    )
    amount = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        validators=[
            MinValueValidator(Decimal("10.00")),
            MaxValueValidator(Decimal("5000.00")),
        ],
    )
    payment_reference = models.CharField(max_length=100, blank=True)
    status = models.CharField(
        max_length=12,
        choices=Status.choices,
        default=Status.PENDING,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.wallet.user} - ₹{self.amount} - {self.status}"


class AdminWallet(models.Model):
    name = models.CharField(
        max_length=50,
        unique=True,
        default="Main Admin Wallet",
    )
    balance = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def wallet_id(self):
        """Internal admin ledger ID; not a UPI ID or bank account."""
        return f"FFADMIN-{self.pk:04d}" if self.pk else "FFADMIN-PENDING"

    def __str__(self):
        return f"{self.wallet_id} · {self.name} - ₹{self.balance}"


class AdminWalletTransaction(models.Model):
    class TransactionType(models.TextChoices):
        ENTRY_FEE = "entry_fee", "Demo Entry Fee"
        PRIZE = "prize", "Demo Prize"
        REFUND = "refund", "Demo Refund"
        ADJUSTMENT = "adjustment", "Demo Adjustment"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    admin_wallet = models.ForeignKey(
        AdminWallet,
        on_delete=models.PROTECT,
        related_name="transactions",
    )
    transaction_type = models.CharField(
        max_length=20,
        choices=TransactionType.choices,
    )
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    status = models.CharField(
        max_length=12,
        choices=Status.choices,
        default=Status.PENDING,
    )
    reference = models.CharField(max_length=100, blank=True)
    description = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return (
            f"{self.admin_wallet.name} - "
            f"{self.transaction_type} - ₹{self.amount}"
        )

class WithdrawalRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending Manual Payout"
        PAID = "paid", "Paid"
        REJECTED = "rejected", "Rejected and Refunded"

    wallet = models.ForeignKey(
        Wallet,
        on_delete=models.PROTECT,
        related_name="withdrawal_requests",
    )
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("10.00"))],
    )
    upi_id = models.CharField(max_length=100)
    status = models.CharField(
        max_length=12,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    payout_reference = models.CharField(max_length=100, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.wallet.user} - ₹{self.amount} - {self.status}"

