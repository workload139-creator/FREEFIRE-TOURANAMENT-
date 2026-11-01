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
    def test_extracts_only_repeated_profile_nickname_after_exact_uid(self, ocr):
        ocr.return_value = {
            "text": [
                "UID:", "1234567890", "ravibhiop", "ravibhiop",
                "zdfdkkoooof", "FREE", "FIRE", "INDIA", "PROFILE",
            ],
            "conf": ["96", "94", "93", "91", "95", "99", "99", "99", "99"],
        }

        uid_ok, uid_confidence, nickname, nickname_confidence = (
            extract_profile_identity(object(), "1234567890")
        )

        self.assertTrue(uid_ok)
        self.assertEqual(uid_confidence, 0.94)
        self.assertEqual(nickname, "ravibhiop")
        self.assertEqual(nickname_confidence, 0.91)

    @patch("apps.tournaments.live_ai_ocr.pytesseract.image_to_data")
    def test_ambiguous_repeated_profile_names_fail_closed(self, ocr):
        ocr.return_value = {
            "text": [
                "UID:", "1234567890", "ravibhiop", "ravibhiop",
                "anothername", "anothername",
            ],
            "conf": ["96", "94", "93", "91", "90", "89"],
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
