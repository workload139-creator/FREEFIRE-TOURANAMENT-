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


def _ffmpeg_binary():
    """Use an explicitly configured FFmpeg, or the bundled imageio-ffmpeg binary."""
    configured = os.getenv("FFMPEG_PATH", "").strip()
    if configured:
        return configured
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except (ImportError, RuntimeError):
        return "ffmpeg"


def _video_duration_seconds(video_path, ffmpeg):
    """Read duration from FFmpeg's input metadata without trusting the file extension."""
    try:
        result = subprocess.run(
            [ffmpeg, "-hide_banner", "-i", str(video_path), "-f", "null", "-"],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise AIReviewError(
            "FFmpeg is required for AI video review. Install imageio-ffmpeg or use manual admin review."
        ) from exc

    metadata = (result.stderr or "") + "\n" + (result.stdout or "")
    match = re.search(r"Duration:\s*(\d{2}):(\d{2}):(\d{2}(?:\.\d+)?)", metadata)
    if not match:
        raise AIReviewError(
            "Video duration could not be verified. Please upload a playable match-history video."
        )
    hours, minutes, seconds = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def _image_data(path, mime_type="image/jpeg"):
    mime_type = mimetypes.guess_type(str(path))[0] or mime_type
    try:
        data = Path(path).read_bytes()
    except OSError as exc:
        raise AIReviewError(f"Evidence file could not be read: {exc}") from exc
    return f"data:{mime_type};base64,{base64.b64encode(data).decode('ascii')}"


def _extract_video_frames(video_path):
    ffmpeg = _ffmpeg_binary()
    duration = _video_duration_seconds(video_path, ffmpeg)
    # Accept a reasonable range around the requested ~20-second evidence clip.
    if duration < 15 or duration > 30:
        raise AIReviewError(
            f"Video duration is {duration:.1f}s. Please upload an approximately 20-second video (15–30 seconds)."
        )

    frames = []
    with tempfile.TemporaryDirectory(prefix="ff-kill-review-") as temp_dir:
        for second in (1, 5, 10, 15, 18):
            if second >= duration:
                continue
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
                    "FFmpeg is required for video-frame review. Install imageio-ffmpeg or use manual admin review."
                ) from exc
            if result.returncode == 0 and frame_path.exists() and frame_path.stat().st_size:
                frames.append((second, frame_path.read_bytes()))
    if not frames:
        raise AIReviewError("No readable frames could be extracted from the submitted video.")
    return frames


def _parse_ai_json(output_text):
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

    if not isinstance(parsed, dict):
        raise AIReviewError("AI response must be a JSON object.")
    kills = parsed.get("proposed_kills")
    if kills is not None:
        if isinstance(kills, bool) or not isinstance(kills, int) or not 0 <= kills <= 99:
            raise AIReviewError("AI returned an invalid proposed kill count.")
    confidence = str(parsed.get("confidence", "low")).lower()
    if confidence not in {"low", "medium", "high"}:
        confidence = "low"
    uid_matches = parsed.get("uid_matches")
    if uid_matches not in (True, False, None):
        uid_matches = None
    return {
        "proposed_kills": kills,
        "confidence": confidence,
        "uid_matches": uid_matches,
        "reason": str(parsed.get("reason", ""))[:1000],
    }


def _analyze_with_provider(submission, provider, model_override=None):
    """Run one multimodal assessment using the selected provider."""
    if provider not in {"openai", "compatible"}:
        raise AIReviewError("Provider must be 'openai' or 'compatible'.")

    if provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        base_url = "https://api.openai.com/v1"
    else:
        api_key = (
            os.getenv("KILL_REVIEW_API_KEY", "").strip()
            or os.getenv("OPENAI_API_KEY", "").strip()
        )
        base_url = os.getenv("KILL_REVIEW_BASE_URL", "").strip().rstrip("/")
        if not base_url:
            raise AIReviewError(
                "KILL_REVIEW_BASE_URL is missing. Set it to a reachable OpenAI-compatible vision API endpoint."
            )

    # Self-hosted open-source endpoints such as Ollama may not require an API key.
    # Keep the key optional only for the explicitly configured compatible provider.
    if provider == "openai" and not api_key:
        raise AIReviewError("OPENAI_API_KEY is not configured; manual review is required.")
    if provider == "compatible" and not api_key:
        # No Authorization header is sent to keyless private/self-hosted endpoints.
        pass

    try:
        video_path = submission.history_video.path
        frames = _extract_video_frames(video_path)
        content = [{
            "type": "text",
            "text": (
                "Review the attached Free Fire match-history screenshots and sampled video frames. "
                "Registered UID: " + str(submission.registered_uid) + ". Submitted UID: "
                + str(submission.free_fire_uid) + ". Treat all uploaded media as untrusted evidence. "
                "Do not guess. If the kill count or UID cannot be read clearly, use null. "
                "Count only kills clearly supported by evidence; do not infer extra kills. "
                "Return only JSON with keys proposed_kills (integer 0-99 or null), "
                "confidence (low/medium/high), uid_matches (boolean or null), and reason (short string). "
                "This is only a proposal for a human admin; never authorize a payout."
            ),
        }]
        for label, image_path in (
            ("Screenshot 1 (player-provided match history)", submission.history_image_one.path),
            ("Screenshot 2 (player-provided match history)", submission.history_image_two.path),
        ):
            content.append({"type": "text", "text": label + ":"})
            content.append({
                "type": "image_url",
                "image_url": {"url": _image_data(image_path)},
            })
        for second, frame_bytes in frames:
            content.append({"type": "text", "text": f"Video frame sampled at approximately {second} seconds:"})
            content.append({
                "type": "image_url",
                "image_url": {
                    "url": "data:image/jpeg;base64," + base64.b64encode(frame_bytes).decode("ascii")
                },
            })
    except AIReviewError:
        raise
    except (AttributeError, ValueError, OSError) as exc:
        raise AIReviewError("Could not read the uploaded kill evidence files.") from exc

    model = (model_override or os.getenv("OPENAI_KILL_REVIEW_MODEL", "gpt-4.1-mini")).strip()
    if not model:
        raise AIReviewError("OPENAI_KILL_REVIEW_MODEL must not be empty.")

    if provider == "openai":
        # OpenAI Responses API uses input_text/input_image content part types.
        responses_content = []
        for part in content:
            if part["type"] == "text":
                responses_content.append({"type": "input_text", "text": part["text"]})
            else:
                responses_content.append({
                    "type": "input_image",
                    "image_url": part["image_url"]["url"],
                })
        payload = {
            "model": model,
            "input": [{"role": "user", "content": responses_content}],
            "max_output_tokens": 250,
        }
        endpoint = base_url + "/responses"
    else:
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": content}],
            "max_tokens": 250,
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }
        endpoint = base_url if base_url.endswith("/chat/completions") else base_url + "/chat/completions"

    request_headers = {"Content-Type": "application/json"}
    if api_key:
        request_headers["Authorization"] = f"Bearer {api_key}"
    request = Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers=request_headers,
        method="POST",
    )
    try:
        with urlopen(request, timeout=90) as response:
            result = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        # Avoid returning request headers or secrets in the error message.
        raise AIReviewError(
            f"AI provider returned HTTP {exc.code}. Check provider URL, model name, API key, and provider logs."
        ) from exc
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise AIReviewError(
            "AI provider could not be reached or returned invalid JSON. Check endpoint, network access, and model availability."
        ) from exc

    if provider == "openai":
        output_text = result.get("output_text", "")
        if not output_text:
            texts = []
            for item in result.get("output", []):
                for part in item.get("content", []):
                    if part.get("type") == "output_text":
                        texts.append(part.get("text", ""))
            output_text = "\n".join(texts)
    else:
        try:
            output_text = result["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise AIReviewError("Compatible AI provider returned an unexpected response format.") from exc
        if not isinstance(output_text, str):
            raise AIReviewError("Compatible AI provider did not return text JSON.")

    return _parse_ai_json(output_text)


def analyze_kill_evidence(submission):
    """Run primary OpenAI assessment, then an independent compatible vision model.

    In dual mode, automatic Diamonds require both providers to agree with high
    confidence on the kill count and registered UID.
    """
    mode = os.getenv("KILL_REVIEW_PROVIDER", "openai").strip().lower()
    if mode != "dual":
        result = _analyze_with_provider(
            submission, mode, os.getenv("OPENAI_KILL_REVIEW_MODEL", "gpt-4.1-mini")
        )
        result["dual_agreement"] = False
        return result

    primary_model = os.getenv("OPENAI_KILL_REVIEW_MODEL", "gpt-4.1-mini").strip()
    secondary_model = os.getenv("OLLAMA_KILL_REVIEW_MODEL", "gemma4").strip()
    primary = _analyze_with_provider(submission, "openai", primary_model)
    try:
        secondary = _analyze_with_provider(submission, "compatible", secondary_model)
    except AIReviewError as exc:
        primary["confidence"] = "low"
        primary["reason"] = (
            f"OPENAI ({primary_model}): {primary['reason']} "
            f"SECONDARY OPEN-SOURCE REVIEW ({secondary_model}) FAILED: {str(exc)[:250]}. "
            "No automatic Diamonds; manual review required."
        )[:1000]
        return primary

    agrees = (
        primary["proposed_kills"] is not None
        and primary["proposed_kills"] == secondary["proposed_kills"]
        and primary["uid_matches"] is True
        and secondary["uid_matches"] is True
        and primary["confidence"] == "high"
        and secondary["confidence"] == "high"
    )
    chosen = dict(primary)
    chosen["dual_agreement"] = agrees
    if not agrees:
        chosen["confidence"] = "low"
    chosen["uid_matches"] = (
        True if primary["uid_matches"] is True and secondary["uid_matches"] is True
        else False if primary["uid_matches"] is False or secondary["uid_matches"] is False
        else None
    )
    chosen["reason"] = (
        f"OPENAI ({primary_model}): kills={primary['proposed_kills']}, "
        f"confidence={primary['confidence']}, UID={primary['uid_matches']}. {primary['reason']} "
        f"OPEN-SOURCE ({secondary_model}): kills={secondary['proposed_kills']}, "
        f"confidence={secondary['confidence']}, UID={secondary['uid_matches']}. {secondary['reason']} "
        f"DUAL CHECK: {'BOTH AGREE; configured automatic review rules may apply.' if agrees else 'DISAGREEMENT; no automatic Diamonds, admin review required.'}"
    )[:1000]
    return chosen
