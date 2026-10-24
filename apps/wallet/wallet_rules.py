
from decimal import Decimal, InvalidOperation

MINIMUM_DEPOSIT = Decimal("10.00")
MAXIMUM_WALLET_BALANCE = Decimal("5000.00")
MINIMUM_WITHDRAWAL = Decimal("10.00")


class WalletRuleError(ValueError):
    pass


def _amount(value):
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise WalletRuleError("Amount valid number hona chahiye.")

    if not amount.is_finite():
        raise WalletRuleError("Amount valid number hona chahiye.")

    if amount <= 0:
        raise WalletRuleError("Amount zero se zyada hona chahiye.")

    return amount


def check_deposit(amount, current_balance):
    amount = _amount(amount)
    balance = Decimal(str(current_balance))

    if amount < MINIMUM_DEPOSIT:
        raise WalletRuleError("Minimum deposit ₹10 hai.")

    if balance < 0 or balance + amount > MAXIMUM_WALLET_BALANCE:
        raise WalletRuleError("Wallet balance ₹5000 se zyada nahi ho sakta.")

    return amount


def check_withdrawal(amount, current_balance):
    amount = _amount(amount)
    balance = Decimal(str(current_balance))

    if balance < 0:
        raise WalletRuleError("Wallet balance galat hai.")

    if amount < MINIMUM_WITHDRAWAL:
        raise WalletRuleError("Minimum withdrawal ₹10 hai.")

    if amount > balance:
        raise WalletRuleError("Wallet mein sufficient balance nahi hai.")

    return amount
