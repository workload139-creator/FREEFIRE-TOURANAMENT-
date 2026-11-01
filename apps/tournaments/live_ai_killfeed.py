"""Full-frame OCR helpers for BR and Clash Squad live-screen analysis.

The OCR pass scans the complete frame rather than assuming a fixed killfeed
corner. It only surfaces text candidates for later independent validation;
it does not identify a killer, prove a kill, or issue a reward.
"""
import re

import pytesseract
from pytesseract import Output


SUPPORTED_TOURNAMENT_MODES = {"BR", "VS"}  # VS is FF Arena's Clash Squad format.
KILL_SIGNAL_WORDS = {"eliminated", "knocked", "headshot", "kill", "killed", "assist"}


def is_kill_signal_text(value):
    """Recognize only explicit candidate words; a streak banner is not a kill row."""
    token = re.sub(r"[^A-Za-z0-9_'-]", "", str(value or "")).casefold()
    return token in KILL_SIGNAL_WORDS


def live_kill_detection_enabled(tournament_mode):
    """Training Ground/free-play has no eligible tournament mode and is excluded."""
    return str(tournament_mode or "").strip().upper() in SUPPORTED_TOURNAMENT_MODES


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
