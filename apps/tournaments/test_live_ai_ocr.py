from unittest.mock import patch

from django.test import SimpleTestCase

from apps.tournaments.live_ai_ocr import verify_profile_uid


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
