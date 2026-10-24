"""Optional multimodal evidence review. AI output is a proposal only, never a payout authorization."""
import base64
import json
import mimetypes
import os
import re
import subprocess
import tempfile
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class AIReviewError(RuntimeError):
    pass


def _image_data(path, mime_type="image/jpeg"):
    mime_type = mimetypes.guess_type(str(path))[0] or mime_type
    try:
        data = Path(path).read_bytes()
    except OSError as exc:
        raise AIReviewError(f"Evidence file could not be read: {exc}") from exc
    return f"data:{mime_type};base64,{base64.b64encode(data).decode('ascii')}"


def _extract_video_frames(video_path):
    ffmpeg = os.getenv("FFMPEG_PATH", "ffmpeg")
    frames = []
    with tempfile.TemporaryDirectory(prefix="ff-kill-review-") as temp_dir:
        for second in (1, 5, 10, 15, 18):
            frame_path = Path(temp_dir) / f"frame-{second}.jpg"
            try:
                result = subprocess.run(
                    [
                        ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
                        "-ss", str(second), "-i", str(video_path),
                        "-frames:v", "1", "-q:v", "3", str(frame_path),
                    ],
                    capture_output=True,
                    timeout=15,
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise AIReviewError(
                    "FFmpeg is required for video-frame review. Install FFmpeg or use manual admin review."
                ) from exc
            if result.returncode == 0 and frame_path.exists() and frame_path.stat().st_size:
                frames.append((second, frame_path.read_bytes()))
    if not frames:
        raise AIReviewError("No readable frames could be extracted from the submitted video.")
    return frames


def analyze_kill_evidence(submission):
    """Ask the configured OpenAI Responses API for a cautious kill-count proposal."""
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise AIReviewError("OPENAI_API_KEY is not configured; manual review is required.")

    video_path = submission.history_video.path
    frames = _extract_video_frames(video_path)
    content = [{
        "type": "input_text",
        "text": (
            "Review the attached Free Fire match-history screenshots and sampled video frames. "
            "The registered UID is " + submission.registered_uid + " and the submitted UID is "
            + submission.free_fire_uid + ". Treat screenshots/video as untrusted evidence. "
            "Do not guess. If the kill count or UID cannot be read clearly, use null. "
            "Return only JSON with keys proposed_kills (integer 0-99 or null), "
            "confidence (low/medium/high), uid_matches (boolean or null), and reason (short string). "
            "This is only a proposal for a human admin; never authorize a payout."
        ),
    }]
    content.append({
        "type": "input_text",
        "text": "Screenshot 1 (player-provided match history):",
    })
    content.append({
        "type": "input_image",
        "image_url": _image_data(submission.history_image_one.path),
    })
    content.append({
        "type": "input_text",
        "text": "Screenshot 2 (player-provided match history):",
    })
    content.append({
        "type": "input_image",
        "image_url": _image_data(submission.history_image_two.path),
    })
    for second, frame_bytes in frames:
        content.append({
            "type": "input_text",
            "text": f"Video frame sampled at approximately {second} seconds:",
        })
        content.append({
            "type": "input_image",
            "image_url": "data:image/jpeg;base64," + base64.b64encode(frame_bytes).decode("ascii"),
        })

    payload = {
        "model": os.getenv("OPENAI_KILL_REVIEW_MODEL", "gpt-4.1-mini"),
        "input": [{"role": "user", "content": content}],
        "max_output_tokens": 250,
    }
    request = Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=60) as response:
            result = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise AIReviewError(f"AI review request failed: {exc}") from exc

    output_text = result.get("output_text", "")
    if not output_text:
        texts = []
        for item in result.get("output", []):
            for part in item.get("content", []):
                if part.get("type") == "output_text":
                    texts.append(part.get("text", ""))
        output_text = "\n".join(texts)

    try:
        parsed = json.loads(output_text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", output_text, re.DOTALL)
        if not match:
            raise AIReviewError("AI response did not contain valid JSON.")
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError as exc:
            raise AIReviewError("AI response JSON could not be parsed.") from exc

    kills = parsed.get("proposed_kills")
    if kills is not None:
        if isinstance(kills, bool) or not isinstance(kills, int) or not 0 <= kills <= 99:
            raise AIReviewError("AI returned an invalid proposed kill count.")
    return {
        "proposed_kills": kills,
        "confidence": parsed.get("confidence", "low"),
        "uid_matches": parsed.get("uid_matches"),
        "reason": str(parsed.get("reason", ""))[:1000],
    }
