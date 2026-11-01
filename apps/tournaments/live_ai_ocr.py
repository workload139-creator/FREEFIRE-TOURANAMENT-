"""Conservative OCR helpers for the registered Free Fire profile and BR lobby.

The current evidence sample shows a profile card with a UID label and the same
nickname repeated in the account header/profile card, followed by a BR lobby
with that nickname, a BR-RANKED label and a START button. We only accept that
specific sequence. Unsupported lobby layouts fail closed.
"""
import re

import pytesseract
from pytesseract import Output


MIN_OCR_CONFIDENCE = 70.0
PROFILE_UI_WORDS = {
    "free", "fire", "india", "profile", "gallery", "overview", "role",
    "history", "weapon", "album", "honor", "score", "wishlist", "clash",
    "squad", "english", "level", "ranked", "bermuda", "store", "luck",
    "royale", "booyah", "pass", "missions", "events", "start", "uid",
}


def _normalise_token(value):
    return re.sub(r"[^a-z0-9]", "", str(value or "").casefold())


def _ocr_words(image, config):
    data = pytesseract.image_to_data(image, output_type=Output.DICT, config=config)
    words = []
    texts = data.get("text", [])
    confidences = data.get("conf", [])
    for index, raw in enumerate(texts):
        token = _normalise_token(raw)
        if not token:
            continue
        try:
            confidence = float(confidences[index])
        except (IndexError, TypeError, ValueError):
            continue
        if confidence >= MIN_OCR_CONFIDENCE:
            def numeric_field(name):
            try:
                return int(data.get(name, [])[index])
            except (IndexError, TypeError, ValueError):
                return None

        block_num = numeric_field("block_num")
        par_num = numeric_field("par_num")
        line_num = numeric_field("line_num")
        words.append({
            "token": token,
            "confidence": confidence,
            "block_num": block_num,
            "par_num": par_num,
            "line_num": line_num,
        })
    return words


def extract_profile_identity(image, registered_uid):
    """Return exact UID proof and one unambiguous nickname from a profile frame.

    The nickname must be a non-UI token repeated at least twice on the profile
    frame. This matches the supplied sample, where the same IGN appears in the
    account header and the profile card. Ambiguous or unseen layouts are held.
    """
    uid = re.sub(r"\D", "", str(registered_uid or ""))
    if not uid:
        return False, 0.0, "", 0.0

    words = _ocr_words(image, "--psm 6")
    has_uid_label = any(word["token"] == "uid" for word in words)
    uid_scores = [
        word["confidence"]
        for word in words
        if re.sub(r"\D", "", word["token"]) == uid
    ]
    if not has_uid_label or not uid_scores:
        return False, 0.0, "", 0.0

    # On the supplied profile sample, the IGN is the single name token on
    # the line immediately above the visible language label ("English").
    # The guild/clan text also appears elsewhere in the header, so simple
    # repeated-token counting would be ambiguous and is deliberately avoided.
    language_lines = [
        word for word in words
        if word["token"] == "english"
        and word["block_num"] is not None
        and word["par_num"] is not None
        and word["line_num"] is not None
    ]
    if len(language_lines) != 1:
        return True, min(uid_scores) / 100.0, "", 0.0

    language = language_lines[0]
    previous_line_numbers = [
        word["line_num"]
        for word in words
        if word["block_num"] == language["block_num"]
        and word["par_num"] == language["par_num"]
        and word["line_num"] is not None
        and word["line_num"] < language["line_num"]
    ]
    if not previous_line_numbers:
        return True, min(uid_scores) / 100.0, "", 0.0

    nickname_line = max(previous_line_numbers)
    name_words = [
        word for word in words
        if word["block_num"] == language["block_num"]
        and word["par_num"] == language["par_num"]
        and word["line_num"] == nickname_line
        and len(word["token"]) >= 4
        and re.search(r"[a-z]", word["token"])
        and word["token"] not in PROFILE_UI_WORDS
    ]
    nickname_tokens = {word["token"] for word in name_words}
    if len(nickname_tokens) != 1:
        return True, min(uid_scores) / 100.0, "", 0.0

    nickname = next(iter(nickname_tokens))
    scores = [word["confidence"] for word in name_words if word["token"] == nickname]
    nickname_confidence = min(scores) / 100.0
    return True, min(uid_scores) / 100.0, nickname, nickname_confidence


def verify_profile_uid(image, registered_uid):
    """Backward-compatible exact UID check; nickname proof is returned separately."""
    verified, confidence, _nickname, _nickname_confidence = extract_profile_identity(
        image, registered_uid
    )
    return verified, confidence


def verify_br_lobby_nickname(image, expected_nickname):
    """Confirm the profile nickname on the supplied BR-RANKED lobby layout.

    No fixed screen coordinates are used. The exact nickname, BR-RANKED label,
    and START control must all be visible in the same OCR frame. This does not
    claim support for Clash Squad/VS lobby layouts yet.
    """
    expected = _normalise_token(expected_nickname)
    if not expected:
        return False, 0.0

    words = _ocr_words(image, "--psm 11")
    tokens = {word["token"] for word in words}
    if expected not in tokens:
        return False, 0.0

    has_br_ranked = "brranked" in tokens or {"br", "ranked"}.issubset(tokens)
    if not has_br_ranked or "start" not in tokens:
        return False, 0.0

    name_confidence = max(
        word["confidence"] for word in words if word["token"] == expected
    )
    anchor_words = [
        word["confidence"]
        for word in words
        if word["token"] in {"brranked", "br", "ranked", "start"}
    ]
    return True, min(name_confidence, min(anchor_words)) / 100.0
