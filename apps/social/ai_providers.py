"""Local AI reviewer diagnostics. This module never contacts OpenAI or Ollama."""
import os
import shutil

def test_local_reviewers():
    return {
        "openai": {"configured": False, "ok": False, "model": "Not used", "message": "Removed; local reviewers are active."},
        "ollama": {"configured": False, "ok": False, "model": "Not used", "message": "Removed; local reviewers are active."},
        "local": {
            "tesseract": bool(shutil.which(os.getenv("TESSERACT_PATH", "tesseract"))),
            "ffmpeg": bool(os.getenv("FFMPEG_PATH")) or bool(shutil.which("ffmpeg")),
        },
    }

def test_all_providers():
    return test_local_reviewers()
