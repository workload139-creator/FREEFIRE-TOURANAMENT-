
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

    def _result(self, kills=4, uid="1234567890"):
        return {
            "proposed_kills": kills, "confidence": "high",
            "uid_matches": True, "observed_uid": uid,
            "history_consistent": True, "evidence_complete": True, "tampering_suspected": False,
            "match_mode": "Battle Royale", "match_date": "2026-10-30",
            "match_id": "match-123", "evidence_notes": "UID and personal kills are readable.",
            "reason": "Evidence is clear.",
        }

    @patch("apps.tournaments.ai_review.verify_evidence_integrity")
    @patch("apps.tournaments.ai_review._analyze_with_provider")
    def test_four_independent_passes_must_agree(self, review, integrity):
        review.side_effect = [self._result(), self._result(), self._result(), self._result()]
        result = analyze_kill_evidence(SimpleNamespace(registered_uid="1234567890"))
        self.assertEqual(review.call_count, 4)
        self.assertTrue(result["four_way_agreement"])
        self.assertEqual(len(result["reviewer_reports"]), 4)
        self.assertEqual(result["proposed_kills"], 4)

    @patch("apps.tournaments.ai_review.verify_evidence_integrity")
    @patch("apps.tournaments.ai_review._analyze_with_provider")
    def test_one_reviewer_failure_is_recorded_and_does_not_stop_others(self, review, integrity):
        review.side_effect = [AIReviewError("OpenAI unavailable"), self._result(), self._result(), self._result()]
        result = analyze_kill_evidence(SimpleNamespace(registered_uid="1234567890"))
        self.assertEqual(review.call_count, 4)
        self.assertFalse(result["four_way_agreement"])
        self.assertEqual(list(result["reviewer_reports"].values())[0]["status"], "FAILED")

    @patch("apps.tournaments.ai_review.verify_evidence_integrity")
    @patch("apps.tournaments.ai_review._analyze_with_provider")
    def test_kill_disagreement_blocks_four_way_agreement(self, review, integrity):
        review.side_effect = [self._result(4), self._result(4), self._result(5), self._result(4)]
        result = analyze_kill_evidence(SimpleNamespace(registered_uid="1234567890"))
        self.assertFalse(result["four_way_agreement"])
        self.assertEqual(result["confidence"], "low")

    @patch("apps.tournaments.ai_review.verify_evidence_integrity")
    @patch("apps.tournaments.ai_review._analyze_with_provider")
    def test_uid_mismatch_blocks_four_way_agreement(self, review, integrity):
        review.side_effect = [self._result(), self._result(), self._result(uid="9999999999"), self._result()]
        result = analyze_kill_evidence(SimpleNamespace(registered_uid="1234567890"))
        self.assertFalse(result["four_way_agreement"])

    @patch("apps.tournaments.ai_review.verify_evidence_integrity")
    @patch("apps.tournaments.ai_review._analyze_with_provider")
    def test_low_confidence_or_incomplete_evidence_blocks_agreement(self, review, integrity):
        incomplete = self._result()
        incomplete["evidence_complete"] = False
        review.side_effect = [self._result(), self._result(), incomplete, self._result()]
        result = analyze_kill_evidence(SimpleNamespace(registered_uid="1234567890"))
        self.assertFalse(result["four_way_agreement"])


class NoAutomaticAIPayoutTests(SimpleTestCase):

    def test_ai_never_credits_reward_without_admin_action(self):
        paid, reason = finalize_dual_ai_reward(SimpleNamespace(), {
            "four_way_agreement": True, "dual_agreement": True,
            "confidence": "high", "uid_matches": True,
            "history_consistent": True, "evidence_complete": True,
            "observed_uid": "1234567890", "proposed_kills": 20,
        })
        self.assertFalse(paid)
        self.assertIn("Admin", reason)
