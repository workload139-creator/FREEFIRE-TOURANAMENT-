"""
Central configuration for FF Tournament.

This file stores project-level options.
Sensitive business operations remain inside their respective Django apps.
"""

import os


def get_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in {"1", "true", "yes", "on"}


WEBSITE = {
    "name": os.getenv("SITE_NAME", "FF Tournament"),
    "currency": os.getenv("SITE_CURRENCY", "INR"),
}

LIMITS = {
    "max_players_per_tournament": int(
        os.getenv("MAX_PLAYERS_PER_TOURNAMENT", "49")
    ),
    "minimum_deposit": int(os.getenv("MINIMUM_DEPOSIT", "10")),
    "max_player_wallet_balance": int(
        os.getenv("MAX_PLAYER_WALLET_BALANCE", "5000")
    ),
    "minimum_withdrawal": int(
        os.getenv("MINIMUM_WITHDRAWAL", "10")
    ),
    "reward_per_approved_kill": int(
        os.getenv("REWARD_PER_APPROVED_KILL", "5")
    ),
    "minimum_verified_kills": int(
        os.getenv("MINIMUM_VERIFIED_KILLS", "2")
    ),
}

FEATURES = {
    "accounts": True,
    "tournaments": True,
    "wallet": True,
    "payments": True,
    "rewards": True,
    "results": True,
    "kill_verification": True,
    "notifications": True,
    "audit": True,
}


def validate_configuration() -> None:
    """Fail early when core financial or tournament settings are invalid."""

    if LIMITS["max_players_per_tournament"] < 1:
        raise ValueError("Tournament capacity must be at least 1.")

    if LIMITS["minimum_deposit"] < 1:
        raise ValueError("Minimum deposit must be positive.")

    if LIMITS["max_player_wallet_balance"] < LIMITS["minimum_deposit"]:
        raise ValueError(
            "Player wallet limit must be at least the minimum deposit."
        )

    if LIMITS["minimum_withdrawal"] < 1:
        raise ValueError("Minimum withdrawal must be positive.")

    if LIMITS["reward_per_approved_kill"] < 0:
        raise ValueError("Reward per kill cannot be negative.")

    if LIMITS["minimum_verified_kills"] < 1:
        raise ValueError("Minimum verified kills must be at least 1.")
