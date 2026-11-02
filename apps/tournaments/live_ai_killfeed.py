"""Full-frame OCR helpers for Battle Royale live-screen analysis.

The OCR pass scans the complete frame rather than assuming a fixed killfeed
corner. It only surfaces text candidates for later independent validation;
it does not identify a killer, prove a kill, or issue a reward.
"""
import re

import pytesseract
from pytesseract import Output


SUPPORTED_TOURNAMENT_MODES = {"BR"}  # Clash Squad uses live viewing only; no AI scan.


def live_kill_detection_enabled(tournament_mode):
    """Only Battle Royale is eligible for AI killfeed scanning."""
    return str(tournament_mode or "").strip().upper() in SUPPORTED_TOURNAMENT_MODES




def player_eliminated_from_text(text):
    """Require a player-facing elimination/spectator phrase, not a killfeed event.

    A killfeed line such as "Enemy eliminated Player" is not sufficient because
    it describes someone else being eliminated. The player's own overlay must
    explicitly say "you are eliminated" or show both elimination and spectator
    wording.
    """
    normalized = re.sub(r"[^a-z0-9 ]+", " ", str(text or "").lower())
    normalized = " ".join(normalized.split())
    explicit_phrases = (
        "you are eliminated",
        "you have been eliminated",
        "you got eliminated",
        "you were eliminated",
    )
    if any(phrase in normalized for phrase in explicit_phrases):
        return True
    has_eliminated = "eliminated" in normalized
    has_spectator = any(word in normalized for word in ("spectating", "spectator", "spectate"))
    return has_eliminated and has_spectator


def scan_full_frame_for_kill_text(image, min_confidence=55.0):
    """Read OCR words from anywhere in the frame; return possible killfeed text.

    No crop/ROI is used: notification position may vary by device, HUD layout,
    orientation, or player settings. OCR text is a candidate only.
    """
    data = pytesseract.image_to_data(
        image,
        output_type=Output.DICT,
        config="--psm 11",
    )
    candidates = []
    for index, raw in enumerate(data.get("text", [])):
        word = re.sub(r"[^A-Za-z0-9_'-]", "", str(raw or "")).strip()
        if not word:
            continue
        try:
            confidence = float(data.get("conf", [])[index])
        except (IndexError, TypeError, ValueError):
            continue
        if confidence < float(min_confidence):
            continue
        candidates.append({
            "text": word,
            "confidence": min(1.0, confidence / 100.0),
            "left": int(data.get("left", [0] * len(data.get("text", [])))[index]),
            "top": int(data.get("top", [0] * len(data.get("text", [])))[index]),
            "width": int(data.get("width", [0] * len(data.get("text", [])))[index]),
            "height": int(data.get("height", [0] * len(data.get("text", [])))[index]),
        })
    return candidates
