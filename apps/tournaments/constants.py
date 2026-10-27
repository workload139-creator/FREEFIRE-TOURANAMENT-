
from decimal import Decimal


# Tournament rules
DEFAULT_MAX_PLAYERS = 49

# Player wallet rules
MINIMUM_DEPOSIT = Decimal("10.00")
MAXIMUM_WALLET_BALANCE = Decimal("5000.00")
MINIMUM_WITHDRAWAL = Decimal("10.00")

# Tournament rewards
REWARD_PER_APPROVED_KILL = Decimal("5.00")

# Player confirmation
PLAYER_CONFIRMATION_TIMEOUT_SECONDS = 600

# Evidence upload rules
MINIMUM_HISTORY_SCREENSHOTS = 2
EXPECTED_HISTORY_VIDEO_SECONDS = 20

# Allowed tournament entry fee
MINIMUM_ENTRY_FEE = Decimal("0.00")
