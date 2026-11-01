"""Conservative OCR helpers for binding a live stream to its registered player.

The profile pass requires an exact registered UID, a visible PROFILE marker,
and one unambiguous repeated nickname token. Later frames only confirm that
the same nickname remains visible. OCR is never kill proof.
"""
import re

import pytesseract
from pytesseract import Output


MIN_WORD_CONFIDENCE = 70.0
PROFILE_UI_WORDS = {
    "profile", "gallery", "overview", "role", "history", "weapon", "album",
    "honor", "score", "wishlist", "free", "fire", "india", "english",
    "clash", "squad", "heroic", "emblem", "rusher", "uid", "start",
    "ranked", "store", "luck", "royale", "booyah", "pass", "missions",
    "events", "vault", "preset", "lab", "claim", "your", "reward",
    "download", "elimination", "streak", "player",
}


def _read_words(image, page_segmentation="11"):
    data = pytesseract.image_to_data(
        image,
        output_type=Output.DICT,
        config=f"--psm {page_segmentation}",
    )
    words = []
    raw_words = data.get("text", [])
    for index, raw in enumerate(raw_words):
        text = str(raw or "").strip()
        try:
            confidence = float(data.get("conf", [])[index])
        except (IndexError, TypeError, ValueError):
            continue
        if not text or confidence < MIN_WORD_CONFIDENCE:
            continue
        def value(name):
            values = data.get(name, [])
            try:
                return int(values[index])
            except (IndexError, TypeError, ValueError):
                return index if name == "line_num" else 0
        words.append({
            "text": text,
            "normalized": re.sub(r"[^a-z0-9]", "", text.casefold()),
            "digits": re.sub(r"\D", "", text),
            "confidence": confidence,
            "line": (value("block_num"), value("par_num"), value("line_num")),
        })
    return words


def verify_profile_uid(image, registered_uid):
    """Legacy exact-UID check; retained for compatibility and isolated tests."""
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
        if word and score >= MIN_WORD_CONFIDENCE:
            words.append((word, score))

    has_uid_label = any(re.search(r"\buid\b", word, re.IGNORECASE) for word, _ in words)
    if not has_uid_label:
        return False, 0.0

    for word, score in words:
        if re.sub(r"\D", "", word) == uid:
            return True, min(1.0, score / 100.0)
    return False, 0.0


def verify_profile_identity(image, registered_uid):
    """Bind an exact UID to one unambiguous repeated nickname on the profile.

    The supplied profile sample shows the nickname in both the player header
    and profile card. Requiring the same alphabetic token on two OCR lines is
    deliberately strict; ambiguous, symbol-heavy, or unreadable names fail
    closed and remain for Admin review.
    """
    uid = re.sub(r"\D", "", str(registered_uid or ""))
    if not uid:
        return False, 0.0, "", 0.0

    words = _read_words(image, page_segmentation="11")
    if not any(word["normalized"] == "profile" for word in words):
        return False, 0.0, "", 0.0
    if not any("uid" in word["normalized"] for word in words):
        return False, 0.0, "", 0.0

    uid_words = [word for word in words if word["digits"] == uid]
    if not uid_words:
        return False, 0.0, "", 0.0
    uid_confidence = max(word["confidence"] for word in uid_words) / 100.0

    occurrences = {}
    for word in words:
        nickname = word["normalized"]
        if (
            not nickname
            or not nickname.isalpha()
            or not 4 <= len(nickname) <= 20
            or nickname in PROFILE_UI_WORDS
        ):
            continue
        occurrences.setdefault(nickname, {}).setdefault(word["line"], []).append(
            word["confidence"]
        )

    repeated = []
    for nickname, lines in occurrences.items():
        if len(lines) >= 2:
            line_scores = [max(scores) for scores in lines.values()]
            repeated.append((nickname, min(line_scores) / 100.0))

    if len(repeated) != 1:
        return False, uid_confidence, "", 0.0

    nickname, nickname_confidence = repeated[0]
    return True, uid_confidence, nickname, nickname_confidence


def verify_bound_nickname_visible(image, expected_nickname):
    """Return true only when the exact profile-bound nickname is OCR-visible."""
    expected = re.sub(r"[^a-z0-9]", "", str(expected_nickname or "").casefold())
    if not expected or not expected.isalpha() or not 4 <= len(expected) <= 20:
        return False, 0.0
    matches = [
        word["confidence"]
        for word in _read_words(image, page_segmentation="11")
        if word["normalized"] == expected
    ]
    if not matches:
        return False, 0.0
    return True, min(1.0, max(matches) / 100.0)
