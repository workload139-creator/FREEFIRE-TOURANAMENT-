from unittest.mock import patch

from django.test import SimpleTestCase

from apps.tournaments.live_ai_ocr import (
    extract_profile_identity,
    verify_br_lobby_nickname,
    verify_profile_uid,
)


class RegisteredProfileUidOCRTests(SimpleTestCase):
    @patch("apps.tournaments.live_ai_ocr.pytesseract.image_to_data")
    def test_accepts_exact_uid_with_uid_label_and_high_confidence(self, ocr):
        ocr.return_value = {
            "text": ["UID:", "1234567890"],
            "conf": ["95", "92"],
        }

        verified, confidence = verify_profile_uid(object(), "1234567890")

        self.assertTrue(verified)
        self.assertEqual(confidence, 0.92)

    @patch("apps.tournaments.live_ai_ocr.pytesseract.image_to_data")
    def test_rejects_uid_mismatch(self, ocr):
        ocr.return_value = {
            "text": ["UID:", "1234567891"],
            "conf": ["95", "99"],
        }

        verified, confidence = verify_profile_uid(object(), "1234567890")

        self.assertFalse(verified)
        self.assertEqual(confidence, 0.0)

    @patch("apps.tournaments.live_ai_ocr.pytesseract.image_to_data")
    def test_rejects_number_without_uid_label(self, ocr):
        ocr.return_value = {
            "text": ["1234567890"],
            "conf": ["99"],
        }

        verified, confidence = verify_profile_uid(object(), "1234567890")

        self.assertFalse(verified)
        self.assertEqual(confidence, 0.0)

    @patch("apps.tournaments.live_ai_ocr.pytesseract.image_to_data")
    def test_rejects_low_confidence_uid(self, ocr):
        ocr.return_value = {
            "text": ["UID:", "1234567890"],
            "conf": ["95", "69"],
        }

        verified, confidence = verify_profile_uid(object(), "1234567890")

        self.assertFalse(verified)
        self.assertEqual(confidence, 0.0)

    @patch("apps.tournaments.live_ai_ocr.pytesseract.image_to_data")
    def test_extracts_profile_name_row_and_ignores_separate_clan_header(self, ocr):
        ocr.return_value = {
            "text": [
                "UID:", "1234567890", "zdfdkkoooof", "ravibhiop",
                "English", "FREE", "FIRE", "INDIA", "PROFILE",
            ],
            "conf": ["96", "94", "95", "93", "92", "99", "99", "99", "99"],
            "block_num": [1, 1, 2, 3, 3, 4, 4, 4, 4],
            "par_num":   [1, 1, 1, 1, 1, 1, 1, 1, 1],
            "line_num":  [1, 1, 1, 2, 3, 1, 1, 1, 1],
        }

        uid_ok, uid_confidence, nickname, nickname_confidence = (
            extract_profile_identity(object(), "1234567890")
        )

        self.assertTrue(uid_ok)
        self.assertEqual(uid_confidence, 0.94)
        self.assertEqual(nickname, "ravibhiop")
        self.assertEqual(nickname_confidence, 0.93)

    @patch("apps.tournaments.live_ai_ocr.pytesseract.image_to_data")
    def test_multiple_names_on_profile_name_row_fail_closed(self, ocr):
        ocr.return_value = {
            "text": ["UID:", "1234567890", "ravibhiop", "anothername", "English"],
            "conf": ["96", "94", "93", "90", "89"],
            "block_num": [1, 1, 3, 3, 3],
            "par_num":   [1, 1, 1, 1, 1],
            "line_num":  [1, 1, 2, 2, 3],
        }

        uid_ok, _uid_confidence, nickname, nickname_confidence = (
            extract_profile_identity(object(), "1234567890")
        )

        self.assertTrue(uid_ok)
        self.assertEqual(nickname, "")
        self.assertEqual(nickname_confidence, 0.0)


class BRLobbyNicknameOCRTests(SimpleTestCase):
    @patch("apps.tournaments.live_ai_ocr.pytesseract.image_to_data")
    def test_matches_profile_nickname_on_br_ranked_lobby(self, ocr):
        ocr.return_value = {
            "text": ["ravibhiop", "BR-RANKED", "Bermuda", "START"],
            "conf": ["93", "92", "88", "96"],
        }

        verified, confidence = verify_br_lobby_nickname(object(), "ravibhiop")

        self.assertTrue(verified)
        self.assertEqual(confidence, 0.92)

    @patch("apps.tournaments.live_ai_ocr.pytesseract.image_to_data")
    def test_rejects_different_lobby_nickname(self, ocr):
        ocr.return_value = {
            "text": ["anothername", "BR-RANKED", "START"],
            "conf": ["93", "92", "96"],
        }

        verified, confidence = verify_br_lobby_nickname(object(), "ravibhiop")

        self.assertFalse(verified)
        self.assertEqual(confidence, 0.0)

    @patch("apps.tournaments.live_ai_ocr.pytesseract.image_to_data")
    def test_rejects_screen_without_br_lobby_anchors(self, ocr):
        ocr.return_value = {
            "text": ["ravibhiop", "PROFILE", "GALLERY"],
            "conf": ["93", "92", "96"],
        }

        verified, confidence = verify_br_lobby_nickname(object(), "ravibhiop")

        self.assertFalse(verified)
        self.assertEqual(confidence, 0.0)
