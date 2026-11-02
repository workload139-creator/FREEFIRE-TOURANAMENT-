from unittest.mock import patch

from django.test import SimpleTestCase

from apps.tournaments.live_ai_killfeed import (
    live_kill_detection_enabled,
    scan_full_frame_for_kill_text,
)


class LiveKillfeedOCRTests(SimpleTestCase):
    def test_only_battle_royale_mode_is_enabled(self):
        self.assertTrue(live_kill_detection_enabled("BR"))
        self.assertFalse(live_kill_detection_enabled("VS"))
        self.assertFalse(live_kill_detection_enabled("CS"))
        self.assertFalse(live_kill_detection_enabled(""))
        self.assertFalse(live_kill_detection_enabled("TRAINING_GROUND"))
        self.assertFalse(live_kill_detection_enabled("CUSTOM"))

    @patch("apps.tournaments.live_ai_killfeed.pytesseract.image_to_data")
    def test_scans_words_without_assuming_a_fixed_screen_region(self, ocr):
        ocr.return_value = {
            "text": ["RAVIBHIOP", "ELIMINATED", "PLAYER123"],
            "conf": ["92", "88", "91"],
            "left": [1200, 1340, 1460],
            "top": [120, 120, 120],
            "width": [90, 100, 85],
            "height": [24, 24, 24],
        }
        candidates = scan_full_frame_for_kill_text(object())
        self.assertEqual([item["text"] for item in candidates],
                         ["RAVIBHIOP", "ELIMINATED", "PLAYER123"])
        self.assertEqual(candidates[1]["left"], 1340)
        self.assertEqual(candidates[1]["confidence"], 0.88)

    @patch("apps.tournaments.live_ai_killfeed.pytesseract.image_to_data")
    def test_discards_low_confidence_words(self, ocr):
        ocr.return_value = {
            "text": ["ELIMINATED", "unclear"],
            "conf": ["90", "30"],
            "left": [100, 200],
            "top": [100, 100],
            "width": [80, 30],
            "height": [20, 20],
        }
        self.assertEqual(
            [item["text"] for item in scan_full_frame_for_kill_text(object())],
            ["ELIMINATED"],
        )
