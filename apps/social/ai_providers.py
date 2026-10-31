"""Server-side connectivity checks for FF Arena AI providers.

Only a tiny generic prompt is sent. Player names, UPI IDs, references,
screenshots, phone numbers and payment records are never sent by these checks.
"""
import json
import os
import urllib.error
import urllib.request


def _request(url, payload, api_key, timeout=25):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _safe_error(exc):
    if isinstance(exc, urllib.error.HTTPError):
        try:
            body = exc.read(1200).decode("utf-8", errors="replace")
        except Exception:
            body = ""
        # Never include request headers or credentials in surfaced errors.
        return f"HTTP {exc.code}: {body[:500]}"
    if isinstance(exc, (TimeoutError, urllib.error.URLError)):
        return f"Connection/timeout error: {str(exc)[:300]}"
    return f"{type(exc).__name__}: {str(exc)[:300]}"


def test_openai():
    key = os.getenv("OPENAI_API_KEY", "").strip()
    model = (os.getenv("OPENAI_KILL_REVIEW_MODEL", "").strip() or os.getenv("OPENAI_MODEL", "gpt-4.1-mini").strip())
    if not key:
        return {"configured": False, "ok": False, "model": model, "message": "OPENAI_API_KEY is missing"}
    try:
        result = _request(
            "https://api.openai.com/v1/responses",
            {
                "model": model,
                "input": "Reply with exactly: FF_ARENA_AI_OK",
                "max_output_tokens": 20,
            },
            key,
        )
        text = result.get("output_text", "")
        if not text:
            text = "Response received"
        return {"configured": True, "ok": True, "model": model, "message": text[:160]}
    except Exception as exc:
        return {"configured": True, "ok": False, "model": model, "message": _safe_error(exc)}


def test_ollama():
    # Test the exact OpenAI-compatible endpoint/model used by kill-evidence review.
    # Keep legacy OLLAMA_* variables as fallbacks for existing deployments.
    key = (
        os.getenv("KILL_REVIEW_API_KEY", "").strip()
        or os.getenv("OLLAMA_API_KEY", "").strip()
    )
    model = (
        os.getenv("OLLAMA_KILL_REVIEW_MODEL", "").strip()
        or os.getenv("OLLAMA_MODEL", "gemma4").strip()
    )
    base_url = (
        os.getenv("KILL_REVIEW_BASE_URL", "").strip()
        or os.getenv("OLLAMA_BASE_URL", "https://ollama.com/v1").strip()
    ).rstrip("/")
    if not base_url:
        return {"configured": False, "ok": False, "model": model, "message": "KILL_REVIEW_BASE_URL is missing"}
    try:
        result = _request(
            f"{base_url}/chat/completions",
            {
                "model": model,
                "messages": [{"role": "user", "content": "Reply with exactly: FF_ARENA_OLLAMA_OK"}],
                "max_tokens": 20,
                "temperature": 0,
            },
            key,
        )
        text = (result.get("choices") or [{}])[0].get("message", {}).get("content", "") or "Response received"
        return {"configured": bool(key), "ok": True, "model": model, "message": text[:160]}
    except Exception as exc:
        return {"configured": bool(key), "ok": False, "model": model, "message": _safe_error(exc)}


def test_all_providers():
    return {"openai": test_openai(), "ollama": test_ollama()}
