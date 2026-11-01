"""Regression tests for the single advisory Live AI Assessment."""
from types import SimpleNamespace
from unittest import TestCase

from apps.tournaments.management.commands.live_ai_payment_worker import build_payment_assessment


class SingleAIAssessmentRulesTests(TestCase):
    def make_event(self, *, mode="BR", confidence="0.90", refunded=False, status="ready"):
        tournament = SimpleNamespace(
            status="live",
            mode=mode,
            is_diwali_offer=False,
            is_free_fan_tournament=False,
            br_format="solo",
        )
        player = SimpleNamespace(free_fire_uid="9876543210", uid_verified=True)
        registration = SimpleNamespace(
            player=player,
            pk=7,
            free_fire_uid="9876543210",
            status=status,
            payment_verified=True,
            refund_processed=refunded,
        )
        session = SimpleNamespace(registration_id=7, status="active", identity_verified_at=object(), observed_player_nickname="RegisteredNick")
        return SimpleNamespace(
            tournament=tournament,
            registration=registration,
            registration_id=7,
            session=session,
            confidence=confidence,
            detected_text="Enemy eliminated",
            match_id="MATCH-001",
            kill_at=object(),
            attributed_player_name="RegisteredNick",
            evidence_image="kill.jpg",
        )

    def test_first_valid_kill_waits_for_minimum_two(self):
        event = self.make_event()
        result = build_payment_assessment(event, prior_count=0)
        self.assertTrue(result["eligible"])
        self.assertEqual(result["proposed_kills"], 1)
        self.assertEqual(result["proposed_rewards"], [])
        self.assertIn("more Admin-verified kill", result["decision_reason"])

    def test_second_valid_kill_proposes_br_diamonds_without_crediting_wallet(self):
        event = self.make_event()
        result = build_payment_assessment(event, prior_count=1)
        self.assertTrue(result["eligible"])
        self.assertEqual(result["proposed_kills"], 2)
        self.assertEqual(result["proposed_rewards"], [
            {"currency": "diamonds", "quantity": 10, "label": "Diamonds"}
        ])
        self.assertNotIn("wallet", result)
        self.assertTrue(result["checks"]["kill_signal_present"])
        self.assertTrue(result["checks"]["evidence_image_present"])
        self.assertNotIn("two_analysis_agents", result["checks"])

    def test_training_ground_or_unsupported_mode_is_held(self):
        event = self.make_event(mode="TRAINING")
        result = build_payment_assessment(event)
        self.assertFalse(result["eligible"])
        self.assertFalse(result["checks"]["supported_mode"])
        self.assertEqual(result["proposed_rewards"], [])

    def test_assessment_requires_saved_kill_screenshot(self):
        event = self.make_event()
        event.evidence_image = None
        result = build_payment_assessment(event)
        self.assertFalse(result["eligible"])
        self.assertFalse(result["checks"]["evidence_image_present"])

    def test_uid_verification_is_required(self):
        event = self.make_event()
        event.session.identity_verified_at = None
        result = build_payment_assessment(event)
        self.assertFalse(result["eligible"])
        self.assertFalse(result["checks"]["live_identity_verified"])


    def test_profile_nickname_binding_is_required(self):
        event = self.make_event()
        event.session.observed_player_nickname = ""
        result = build_payment_assessment(event)
        self.assertFalse(result["eligible"])
        self.assertFalse(result["checks"]["profile_nickname_bound"])

    def test_low_confidence_or_refunded_player_is_held(self):
        low_confidence = build_payment_assessment(self.make_event(confidence="0.40"))
        refunded = build_payment_assessment(self.make_event(refunded=True))
        self.assertFalse(low_confidence["eligible"])
        self.assertFalse(refunded["eligible"])
