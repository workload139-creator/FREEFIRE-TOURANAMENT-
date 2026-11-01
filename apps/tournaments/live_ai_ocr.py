"""Conservative OCR helpers for binding a live stream to its registered player.

Only an exact registered Free Fire UID next to a visible UID label is accepted.
This module deliberately does not infer kills from OCR text.
"""
import re

import pytesseract
from pytesseract import Output


def verify_profile_uid(image, registered_uid):
    uid = re.sub(r"\D", "", str(registered_uid or ""))
    if not uid:
        return False, 0.0

    data = pytesseract.image_to_data(
        image,
        output_type=Output.DICT,
        config="--psm 6",
    )
    words = []
    for raw, confidence in zip(data.get("text", []), data.get("conf", [])):
        word = str(raw or "").strip()
        try:
            score = float(confidence)
        except (TypeError, ValueError):
            continue
        if word and score >= 70:
            words.append((word, score))

    # Require the profile's UID label and the exact UID token in the same OCR
    # result. Do not fuzzy-match digits: a mismatch must remain unverified.
    has_uid_label = any(re.search(r"\buid\b", word, re.IGNORECASE) for word, _ in words)
    if not has_uid_label:
        return False, 0.0

    for word, score in words:
        digits = re.sub(r"\D", "", word)
        if digits == uid:
            return True, min(1.0, score / 100.0)
    return False, 0.0
