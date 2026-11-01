from unittest.mock import patch

from django.test import SimpleTestCase

from apps.tournaments.live_ai_ocr import (
    verify_bound_nickname_visible,
    verify_profile_identity,
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
    def test_binds_exact_uid_to_one_repeated_profile_nickname(self, ocr):
        ocr.return_value = {
            "text": ["PROFILE", "UID:", "6968889283", "ravibhiop", "ravibhiop", "FREE", "FIRE", "ENGLISH", "zdfdkk0000f"],
            "conf": ["98", "95", "93", "92", "90", "99", "99", "94", "91"],
            "block_num": [1, 2, 2, 3, 4, 2, 2, 2, 2],
            "par_num":   [1, 1, 1, 1, 1, 1, 1, 1, 1],
            "line_num":  [1, 1, 1, 1, 1, 1, 1, 2, 3],
        }

        verified, uid_confidence, nickname, nickname_confidence = verify_profile_identity(
            object(), "6968889283"
        )

        self.assertTrue(verified)
        self.assertEqual(nickname, "ravibhiop")
        self.assertEqual(uid_confidence, 0.93)
        self.assertEqual(nickname_confidence, 0.90)

    @patch("apps.tournaments.live_ai_ocr.pytesseract.image_to_data")
    def test_profile_binding_rejects_uid_mismatch(self, ocr):
        ocr.return_value = {
            "text": ["PROFILE", "UID:", "6968889284", "ravibhiop", "ravibhiop"],
            "conf": ["98", "95", "93", "92", "90"],
            "block_num": [1, 2, 2, 3, 4],
            "par_num": [1, 1, 1, 1, 1],
            "line_num": [1, 1, 1, 1, 1],
        }

        verified, _, nickname, _ = verify_profile_identity(object(), "6968889283")

        self.assertFalse(verified)
        self.assertEqual(nickname, "")

    @patch("apps.tournaments.live_ai_ocr.pytesseract.image_to_data")
    def test_profile_binding_rejects_ambiguous_repeated_names(self, ocr):
        ocr.return_value = {
            "text": ["PROFILE", "UID:", "6968889283", "ravibhiop", "ravibhiop", "othername", "othername"],
            "conf": ["98", "95", "93", "92", "90", "91", "90"],
            "block_num": [1, 2, 2, 3, 4, 5, 6],
            "par_num": [1, 1, 1, 1, 1, 1, 1],
            "line_num": [1, 1, 1, 1, 1, 1, 1],
        }

        verified, _, nickname, _ = verify_profile_identity(object(), "6968889283")

        self.assertFalse(verified)
        self.assertEqual(nickname, "")

    @patch("apps.tournaments.live_ai_ocr.pytesseract.image_to_data")
    def test_lobby_frame_matches_only_exact_bound_nickname(self, ocr):
        ocr.return_value = {
            "text": ["START", "BR-RANKED", "ravibhiop"],
            "conf": ["95", "92", "91"],
            "block_num": [1, 2, 3],
            "par_num": [1, 1, 1],
            "line_num": [1, 1, 1],
        }

        self.assertEqual(verify_bound_nickname_visible(object(), "RAVIBHIOP"), (True, 0.91))
        ocr.return_value["text"] = ["START", "BR-RANKED", "anothername"]
        self.assertEqual(verify_bound_nickname_visible(object(), "ravibhiop"), (False, 0.0))
