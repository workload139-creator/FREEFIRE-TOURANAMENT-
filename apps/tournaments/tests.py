
from decimal import Decimal

from django.test import SimpleTestCase

from .kill_services import (
    calculate_proposed_reward,
    calculate_approved_reward,
)


class KillRewardTests(SimpleTestCase):

    def test_zero_kills_reward_is_zero(self):
        self.assertEqual(
            calculate_proposed_reward(0),
            Decimal("0.00"),
        )

    def test_five_kills_reward_is_twenty_five(self):
        self.assertEqual(
            calculate_proposed_reward(5),
            Decimal("25.00"),
        )

    def test_admin_must_approve_reward(self):
        with self.assertRaises(ValueError):
            calculate_approved_reward(5, admin_approved=False)

    def test_approved_kills_reward(self):
        self.assertEqual(
            calculate_approved_reward(3, admin_approved=True),
            Decimal("15.00"),
        )

    def test_negative_kills_are_rejected(self):
        with self.assertRaises(ValueError):
            calculate_proposed_reward(-1)
