
from decimal import Decimal, InvalidOperation


REWARD_PER_KILL = Decimal("5.00")


def calculate_proposed_reward(kills):
    """Calculate a proposed reward; this does not authorize a payout."""
    try:
        kills = int(kills)
    except (TypeError, ValueError, InvalidOperation):
        raise ValueError("Kill count must be a whole number.")

    if kills < 0:
        raise ValueError("Kill count cannot be negative.")

    return REWARD_PER_KILL * kills


def calculate_approved_reward(approved_kills, admin_approved=False):
    """Return a reward only after an explicit admin approval."""
    if not admin_approved:
        raise ValueError("Admin approval is required before finalizing reward.")

    return calculate_proposed_reward(approved_kills)
