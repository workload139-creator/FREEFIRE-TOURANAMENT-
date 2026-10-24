
from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q


class Wallet(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="wallet",
        null=True,
        blank=True,
    )
    is_admin_wallet = models.BooleanField(default=False)
    balance = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["is_admin_wallet"],
                condition=Q(is_admin_wallet=True),
                name="one_admin_wallet_only",
            ),
        ]

    def __str__(self):
        return (
            "Admin Wallet"
            if self.is_admin_wallet
            else f"Wallet: {self.user}"
        )


class WalletTransaction(models.Model):
    class Type(models.TextChoices):
        DEPOSIT = "DEPOSIT", "Deposit"
        ENTRY_FEE = "ENTRY_FEE", "Tournament Entry Fee"
        REFUND = "REFUND", "Entry Fee Refund"
        PRIZE = "PRIZE", "Prize Payout"
        WITHDRAWAL = "WITHDRAWAL", "Withdrawal"
        ADJUSTMENT = "ADJUSTMENT", "Admin Adjustment"

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        COMPLETED = "COMPLETED", "Completed"
        FAILED = "FAILED", "Failed"

    wallet = models.ForeignKey(
        Wallet,
        on_delete=models.PROTECT,
        related_name="transactions",
    )
    transaction_type = models.CharField(
        max_length=20,
        choices=Type.choices,
    )
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0.01)],
    )
    status = models.CharField(
        max_length=12,
        choices=Status.choices,
        default=Status.PENDING,
    )
    reference = models.CharField(max_length=100, unique=True)
    description = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return (
            f"{self.transaction_type} "
            f"₹{self.amount} - {self.status}"
        )
