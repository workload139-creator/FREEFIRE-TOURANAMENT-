import os
from unittest.mock import patch

from django.test import SimpleTestCase

from apps.tournaments.live_ai_rewards import (
    approve_live_kill_event,
    live_ai_reward_settlement_enabled,
)


class LiveAIRewardSettlementGateTests(SimpleTestCase):
    def test_wallet_settlement_is_disabled_when_flag_is_missing(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("LIVE_AI_REWARD_SETTLEMENT_ENABLED", None)
            self.assertFalse(live_ai_reward_settlement_enabled())
            approved, reason = approve_live_kill_event(999999999, None)

        self.assertFalse(approved)
        self.assertIn("disabled", reason.lower())

    def test_wallet_settlement_requires_explicit_truthy_opt_in(self):
        for value in ("1", "true", "yes", "on"):
            with self.subTest(value=value), patch.dict(
                os.environ, {"LIVE_AI_REWARD_SETTLEMENT_ENABLED": value}
            ):
                self.assertTrue(live_ai_reward_settlement_enabled())

        for value in ("", "0", "false", "no", "off"):
            with self.subTest(value=value), patch.dict(
                os.environ, {"LIVE_AI_REWARD_SETTLEMENT_ENABLED": value}
            ):
                self.assertFalse(live_ai_reward_settlement_enabled())
