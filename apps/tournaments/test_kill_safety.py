from datetime import datetime, timezone as datetime_timezone
from types import SimpleNamespace

from django.test import SimpleTestCase

from .kill_safety import validate_match_dates, get_match_id


REVIEWER_KEYS = (
    "ff_arena_assessment_openai",
    "ff_arena_assessment_ollama",
    "ff_arena_agent_openai",
    "ff_arena_agent_ollama",
)


def reports_for(date_value="31/10/2026", match_id="match-123"):
    return {
        key: {
            "status": "COMPLETED",
            "match_date": date_value,
            "match_id": match_id,
        }
        for key in REVIEWER_KEYS
    }


class KillEvidenceSafetyTests(SimpleTestCase):
    def setUp(self):
        self.tournament = SimpleNamespace(
            start_time=datetime(2026, 10, 31, 18, 0, tzinfo=datetime_timezone.utc)
        )

    def test_all_reviewers_same_tournament_date_pass(self):
        valid, _ = validate_match_dates(reports_for(), self.tournament)
        self.assertTrue(valid)

    def test_next_calendar_day_is_allowed_for_midnight_rollover(self):
        valid, _ = validate_match_dates(reports_for("01/11/2026"), self.tournament)
        self.assertTrue(valid)

    def test_pre_tournament_history_date_is_rejected(self):
        valid, _ = validate_match_dates(reports_for("30/10/2026"), self.tournament)
        self.assertFalse(valid)

    def test_old_history_date_is_rejected(self):
        valid, reason = validate_match_dates(reports_for("20/10/2026"), self.tournament)
        self.assertFalse(valid)
        self.assertIn("outside the allowed", reason)

    def test_unreadable_or_missing_date_is_rejected(self):
        reports = reports_for()
        reports[REVIEWER_KEYS[0]]["match_date"] = ""
        valid, _ = validate_match_dates(reports, self.tournament)
        self.assertFalse(valid)

    def test_reviewers_must_agree_on_date(self):
        reports = reports_for()
        reports[REVIEWER_KEYS[-1]]["match_date"] = "01/11/2026"
        valid, _ = validate_match_dates(reports, self.tournament)
        self.assertFalse(valid)

    def test_match_id_requires_four_way_agreement(self):
        self.assertEqual(get_match_id(reports_for()), "match-123")
        reports = reports_for()
        reports[REVIEWER_KEYS[-1]]["match_id"] = "different"
        self.assertEqual(get_match_id(reports), "")
