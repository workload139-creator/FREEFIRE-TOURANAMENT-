"""Business services for player accounts."""

from decimal import Decimal

from django.db import transaction
from django.core.exceptions import ValidationError

from .models import Wallet, WalletTransaction


@transaction.atomic
def credit_verified_deposit(
    *,
    user,
    amount,
    payment_reference,
):
    """
    Sirf trusted payment-provider verification ke baad call karein.
    Ye function khud payment verify nahi karta.
    """

    amount = Decimal(str(amount))

    if amount < Decimal("10.00"):
        raise ValidationError("Minimum deposit ₹10 hai.")

    if not payment_reference:
        raise ValidationError("Payment reference required hai.")

    wallet = Wallet.objects.select_for_update().get(user=user)

    if WalletTransaction.objects.filter(
        reference=payment_reference
    ).exists():
        raise ValidationError("Ye payment reference pehle use ho chuka hai.")

    if wallet.balance + amount > Decimal("5000.00"):
        raise ValidationError("Wallet balance ₹5000 se zyada nahi ho sakta.")

    wallet.balance += amount
    wallet.save(update_fields=["balance", "updated_at"])

    WalletTransaction.objects.create(
        wallet=wallet,
        transaction_type=WalletTransaction.TransactionType.DEPOSIT,
        amount=amount,
        status=WalletTransaction.Status.COMPLETED,
        reference=payment_reference,
        description="Verified deposit",
    )

    return wallet
