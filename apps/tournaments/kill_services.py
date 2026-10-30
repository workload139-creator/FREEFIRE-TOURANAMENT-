from decimal import Decimal, InvalidOperation


def reward_for_tournament(tournament, kills):
    """Return (currency, quantity, label) for an approved BR kill reward."""
    try:
        kills = int(kills)
    except (TypeError, ValueError, InvalidOperation):
        raise ValueError("Kill count must be a whole number.")
    if kills < 0:
        raise ValueError("Kill count cannot be negative.")
    if tournament.mode == "VS":
        return "coins", kills * 2, "Coins"
    if tournament.is_free_fan_tournament:
        return "fan_tokens", kills // 2, "Fan Tokens"
    if tournament.mode == "BR":
        return "diamonds", kills * 5, "Diamonds"
    return "coins", kills * 2, "Coins"


def calculate_proposed_reward(kills):
    """Legacy helper retained for callers that use the default Diamond rate."""
    try:
        kills = int(kills)
    except (TypeError, ValueError, InvalidOperation):
        raise ValueError("Kill count must be a whole number.")
    if kills < 0:
        raise ValueError("Kill count cannot be negative.")
    return Decimal("5.00") * kills


def calculate_approved_reward(approved_kills, admin_approved=False):
    if not admin_approved:
        raise ValueError("Admin approval is required before finalizing reward.")
    return calculate_proposed_reward(approved_kills)
