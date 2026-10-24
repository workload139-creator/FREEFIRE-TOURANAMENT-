
from decimal import Decimal


MINIMUM_DEPOSIT = Decimal("10.00")
MAXIMUM_WALLET_BALANCE = Decimal("5000.00")
MINIMUM_WITHDRAWAL = Decimal("10.00")


class WalletOperationError(Exception):
    """Raised when a wallet operation is invalid."""


def validate_deposit(amount, current_balance):
    amount = Decimal(str(amount))
    current_balance = Decimal(str(current_balance))

    if amount < MINIMUM_DEPOSIT:
        raise WalletOperationError(
            "Minimum deposit ₹10 hai."
        )

    if current_balance + amount > MAXIMUM_WALLET_BALANCE:
        raise WalletOperationError(
            "Wallet balance ₹5000 se zyada nahi ho sakta."
        )

    return amount


def validate_withdrawal(amount, current_balance):
    amount = Decimal(str(amount))
    current_balance = Decimal(str(current_balance))

    if amount < MINIMUM_WITHDRAWAL:
        raise WalletOperationError(
            "Minimum withdrawal ₹10 hai."
        )

    if amount > current_balance:
        raise WalletOperationError(
            "Wallet mein itna balance nahi hai."
        )

    return amount


def calculate_kill_reward(approved_kills):
    if isinstance(approved_kills, bool):
        raise WalletOperationError("Kills ki sankhya galat hai.")

    try:
        kills = int(approved_kills)
    except (TypeError, ValueError):
        raise WalletOperationError("Kills ki sankhya galat hai.")

    if kills < 0 or str(kills) != str(approved_kills).strip():
        raise WalletOperationError("Kills ki sankhya galat hai.")

    return Decimal(kills) * Decimal("5.00")
