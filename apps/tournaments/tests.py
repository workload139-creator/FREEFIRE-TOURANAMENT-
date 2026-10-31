
from decimal import Decimal

from django.test import SimpleTestCase
from types import SimpleNamespace
from unittest.mock import patch
import os

from .ai_review import AIReviewError, analyze_kill_evidence

from .kill_services import (
    calculate_proposed_reward,
    calculate_approved_reward,
    finalize_dual_ai_reward,
    rewards_for_tournament,
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

class FourAIReviewTests(SimpleTestCase):
    def _submission(self):
        return SimpleNamespace(
            registered_uid="1234567890",
            free_fire_uid="1234567890",
            history_image_one=SimpleNamespace(name="history-one.png"),
            history_image_two=SimpleNamespace(name="history-two.png"),
            history_video=SimpleNamespace(name="history.mp4"),
        )

    def _text(self, kills=4, uid="1234567890"):
        return f"Free Fire UID: {uid} Battle Royale Kills: {kills} 30/10/2026"

    @patch("apps.tournaments.ai_review.verify_evidence_integrity", return_value={})
    @patch("apps.tournaments.ai_review._bytes", side_effect=[b"image-one", b"image-two"])
    @patch("apps.tournaments.ai_review._frames", return_value=([(10, b"frame")], ""))
    @patch("apps.tournaments.ai_review._ocr")
    def test_local_review_reports_cross_media_agreement(self, ocr, frames, read_bytes, integrity):
        ocr.side_effect = [
            (self._text(), ""),
            (self._text(), ""),
            (self._text(), ""),
        ]
        result = analyze_kill_evidence(self._submission())
        self.assertTrue(result["dual_agreement"])
        self.assertEqual(result["proposed_kills"], 4)
        self.assertEqual(len(result["reviewer_reports"]), 4)
        self.assertFalse(result["four_way_agreement"])

    @patch("apps.tournaments.ai_review.verify_evidence_integrity", return_value={})
    @patch("apps.tournaments.ai_review._bytes", side_effect=[b"image-one", b"image-two"])
    @patch("apps.tournaments.ai_review._frames", return_value=([(10, b"frame")], ""))
    @patch("apps.tournaments.ai_review._ocr")
    def test_uid_mismatch_blocks_cross_media_agreement(self, ocr, frames, read_bytes, integrity):
        ocr.side_effect = [
            (self._text(), ""),
            (self._text(), ""),
            (self._text(uid="9999999999"), ""),
        ]
        result = analyze_kill_evidence(self._submission())
        self.assertFalse(result["dual_agreement"])
        self.assertIsNone(result["proposed_kills"])

    @patch("apps.tournaments.ai_review.verify_evidence_integrity", return_value={})
    @patch("apps.tournaments.ai_review._bytes", side_effect=[b"image-one", b"image-two"])
    @patch("apps.tournaments.ai_review._frames", return_value=([], "FFmpeg unavailable"))
    @patch("apps.tournaments.ai_review._ocr")
    def test_missing_video_evidence_keeps_review_advisory(self, ocr, frames, read_bytes, integrity):
        ocr.side_effect = [
            (self._text(), ""),
            (self._text(), ""),
        ]
        result = analyze_kill_evidence(self._submission())
        self.assertFalse(result["dual_agreement"])
        self.assertIsNone(result["proposed_kills"])
        self.assertEqual(result["confidence"], "low")

class TournamentSpecificRewardTests(SimpleTestCase):

    def test_br_solo_rewards_diamonds_per_kill(self):
        tournament = SimpleNamespace(mode="BR", is_diwali_offer=False, is_free_fan_tournament=False, br_format="solo")
        self.assertEqual(rewards_for_tournament(tournament, 4), [("diamonds", 20, "Diamonds")])

    def test_br_duo_rewards_diamonds_and_coins(self):
        tournament = SimpleNamespace(mode="BR", is_diwali_offer=False, is_free_fan_tournament=False, br_format="duo")
        self.assertEqual(rewards_for_tournament(tournament, 4), [("diamonds", 20, "Diamonds"), ("coins", 8, "Coins")])

    def test_vs_rewards_coins(self):
        tournament = SimpleNamespace(mode="VS", is_diwali_offer=False, is_free_fan_tournament=False, br_format="")
        self.assertEqual(rewards_for_tournament(tournament, 4), [("coins", 8, "Coins")])

    def test_diwali_rewards_coins(self):
        tournament = SimpleNamespace(mode="BR", is_diwali_offer=True, is_free_fan_tournament=False, br_format="solo")
        self.assertEqual(rewards_for_tournament(tournament, 4), [("coins", 20, "Coins")])

    def test_free_fan_rewards_one_token_per_two_kills(self):
        tournament = SimpleNamespace(mode="BR", is_diwali_offer=False, is_free_fan_tournament=True, br_format="solo")
        self.assertEqual(rewards_for_tournament(tournament, 5), [("fan_tokens", 2, "Fan Tokens")])

    def test_negative_tournament_kills_are_rejected(self):
        tournament = SimpleNamespace(mode="BR", is_diwali_offer=False, is_free_fan_tournament=False, br_format="solo")
        with self.assertRaises(ValueError):
            rewards_for_tournament(tournament, -1)
