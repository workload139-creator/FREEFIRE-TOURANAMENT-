from decimal import Decimal, InvalidOperation


def rewards_for_tournament(tournament, kills):
    """Return every wallet currency reward for approved kills."""
    try:
        kills = int(kills)
    except (TypeError, ValueError, InvalidOperation):
        raise ValueError("Kill count must be a whole number.")
    if kills < 0:
        raise ValueError("Kill count cannot be negative.")
    if tournament.mode == "VS":
        return [("coins", kills * 2, "Coins")]
    if getattr(tournament, "is_diwali_offer", False):
        quantity = kills * 5
        return [("coins", quantity, "Coins")] if quantity else []
    if tournament.is_free_fan_tournament:
        quantity = kills // 2
        return [("fan_tokens", quantity, "Fan Tokens")] if quantity else []
    if tournament.mode == "BR":
        rewards = [("diamonds", kills * 5, "Diamonds")]
        if tournament.br_format in ("duo", "squad"):
            rewards.append(("coins", kills * 2, "Coins"))
        return [item for item in rewards if item[1] > 0]
    return [("coins", kills * 2, "Coins")]


def reward_for_tournament(tournament, kills):
    """Backward-compatible primary reward tuple for existing callers."""
    rewards = rewards_for_tournament(tournament, kills)
    if rewards:
        return rewards[0]
    if tournament.is_free_fan_tournament:
        return "fan_tokens", 0, "Fan Tokens"
    if tournament.mode == "VS":
        return "coins", 0, "Coins"
    return "diamonds", 0, "Diamonds"


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

def finalize_dual_ai_reward(submission, result):
    """Legacy compatibility guard: AI is never allowed to approve or credit rewards."""
    return False, "Automatic AI payout is disabled. An Admin must inspect the evidence and approve the final kill count."
