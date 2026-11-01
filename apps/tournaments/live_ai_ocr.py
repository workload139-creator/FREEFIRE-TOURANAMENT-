"""Conservative OCR helpers for the registered Free Fire profile and BR lobby.

The supplied profile sample shows a UID label, a player-name row immediately
above the language label, and a separate clan/header token. The supplied BR
lobby repeats the player name alongside BR-RANKED and START. Unsupported
layouts fail closed; no screen coordinates are hard-coded.
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


def _numeric_field(data, name, index):
    try:
        return int(data.get(name, [])[index])
    except (IndexError, TypeError, ValueError):
        return None


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
        if confidence < MIN_OCR_CONFIDENCE:
            continue
        words.append({
            "token": token,
            "confidence": confidence,
            "block_num": _numeric_field(data, "block_num", index),
            "par_num": _numeric_field(data, "par_num", index),
            "line_num": _numeric_field(data, "line_num", index),
        })
    return words


def extract_profile_identity(image, registered_uid):
    """Return exact UID proof and one unambiguous IGN from the profile card.

    On the supplied screen, the IGN is the single non-UI name token on the line
    immediately above "English". The separate clan/header text is not selected.
    If OCR cannot identify that exact row, the nickname remains empty.
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
    nickname_confidence = min(
        word["confidence"] for word in name_words if word["token"] == nickname
    ) / 100.0
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
