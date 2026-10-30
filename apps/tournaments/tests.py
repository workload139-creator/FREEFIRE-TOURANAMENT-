
from decimal import Decimal

from django.test import SimpleTestCase
from types import SimpleNamespace
from unittest.mock import patch
import os

from .ai_review import AIReviewError, analyze_kill_evidence

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

class DualAIReviewTests(SimpleTestCase):

    def _result(self, kills=4, uid="1234567890"):
        return {
            "proposed_kills": kills,
            "confidence": "high",
            "uid_matches": True,
            "observed_uid": uid,
            "history_consistent": True,
            "evidence_complete": True,
            "match_mode": "Battle Royale",
            "match_date": "2026-10-30",
            "match_id": "match-123",
            "evidence_notes": "UID and personal kills are readable.",
            "reason": "Evidence is clear.",
        }

    @patch.dict(os.environ, {
        "KILL_REVIEW_PROVIDER": "dual",
        "OPENAI_KILL_REVIEW_MODEL": "primary-test",
        "OLLAMA_KILL_REVIEW_MODEL": "agent-test",
    })
    @patch("apps.tournaments.ai_review._analyze_with_provider")
    def test_ai_agent_runs_even_if_primary_fails(self, review):
        review.side_effect = [AIReviewError("primary unavailable"), self._result()]
        result = analyze_kill_evidence(SimpleNamespace(registered_uid="1234567890"))
        self.assertEqual(review.call_count, 2)
        self.assertFalse(result["dual_agreement"])
        self.assertEqual(result["confidence"], "low")
        self.assertIn("Admin Review required", result["reason"])

    @patch.dict(os.environ, {
        "KILL_REVIEW_PROVIDER": "dual",
        "OPENAI_KILL_REVIEW_MODEL": "primary-test",
        "OLLAMA_KILL_REVIEW_MODEL": "agent-test",
    })
    @patch("apps.tournaments.ai_review._analyze_with_provider")
    def test_dual_agreement_requires_matching_uid_and_kills(self, review):
        review.side_effect = [self._result(), self._result(uid="9999999999")]
        result = analyze_kill_evidence(SimpleNamespace(registered_uid="1234567890"))
        self.assertFalse(result["dual_agreement"])
        self.assertEqual(result["confidence"], "low")

    @patch.dict(os.environ, {"KILL_REVIEW_PROVIDER": "dual"})
    @patch("apps.tournaments.ai_review._analyze_with_provider")
    def test_incomplete_evidence_never_passes_dual_review(self, review):
        first = self._result()
        second = self._result()
        second["evidence_complete"] = False
        review.side_effect = [first, second]
        result = analyze_kill_evidence(SimpleNamespace(registered_uid="1234567890"))
        self.assertFalse(result["dual_agreement"])
        self.assertFalse(result["evidence_complete"])
