"""Cashfree Payments API helpers. Secrets must only live in Render environment variables."""
import base64
import hashlib
import hmac
import json
import os
import urllib.error
import urllib.request


API_VERSION = "2025-01-01"


class CashfreeError(Exception):
    pass


def _config():
    app_id = os.getenv("CASHFREE_CLIENT_ID", "").strip()
    secret = os.getenv("CASHFREE_CLIENT_SECRET", "").strip()
    mode = os.getenv("CASHFREE_MODE", "sandbox").strip().lower()
    if not app_id or not secret:
        raise CashfreeError("Cashfree API keys Render Environment mein set nahi hain.")
    if mode not in {"sandbox", "production"}:
        raise CashfreeError("CASHFREE_MODE sandbox ya production hona chahiye.")
    base = "https://sandbox.cashfree.com/pg" if mode == "sandbox" else "https://api.cashfree.com/pg"
    return app_id, secret, mode, base


def api_request(method, path, payload=None):
    app_id, secret, _mode, base = _config()
    body = None if payload is None else json.dumps(payload, separators=(",", ":")).encode("utf-8")
    headers = {
        "x-client-id": app_id,
        "x-client-secret": secret,
        "x-api-version": API_VERSION,
        "accept": "application/json",
    }
    if body is not None:
        headers["content-type"] = "application/json"
    request = urllib.request.Request(base + path, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1000]
        raise CashfreeError(f"Cashfree API error ({exc.code}): {detail}") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise CashfreeError("Cashfree se connection ya response error aaya. Dobara try karein.") from exc


def create_order(*, order_id, amount, user, return_url, notify_url):
    phone = "".join(ch for ch in (user.phone_number or "") if ch.isdigit())[-10:]
    if len(phone) != 10:
        raise CashfreeError("Payment se pehle profile mein valid 10-digit phone number add karein.")
    customer_id = "player_" + str(user.pk)
    customer_name = " ".join((user.get_full_name() or user.username).split())
    customer_name = "".join(ch for ch in customer_name if ch.isalnum() or ch in " .'-")[:100] or customer_id
    return api_request("POST", "/orders", {
        "order_id": order_id,
        "order_amount": float(amount),
        "order_currency": "INR",
        "customer_details": {
            "customer_id": customer_id,
            "customer_name": customer_name,
            "customer_email": user.email or f"{customer_id}@example.invalid",
            "customer_phone": phone,
        },
        "order_meta": {
            "return_url": return_url,
            "notify_url": notify_url,
        },
        "order_note": "Free Fire tournament wallet deposit",
    })


def verify_paid_order(order_id, expected_amount):
    order = api_request("GET", "/orders/" + order_id)
    if order.get("order_status") != "PAID":
        return False
    actual_amount = str(order.get("order_amount", ""))
    if not actual_amount or round(float(actual_amount), 2) != round(float(expected_amount), 2):
        raise CashfreeError("Cashfree order amount website ke deposit amount se match nahi karta.")
    payments = api_request("GET", "/orders/" + order_id + "/payments")
    if not isinstance(payments, list):
        return False
    return any(
        payment.get("payment_status") == "SUCCESS"
        and round(float(payment.get("payment_amount", 0)), 2) == round(float(expected_amount), 2)
        for payment in payments
    )


def verify_webhook_signature(raw_body, timestamp, signature):
    _app_id, secret, _mode, _base = _config()
    if not timestamp or not signature:
        return False
    signed_payload = timestamp.encode("utf-8") + raw_body
    expected = base64.b64encode(hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).digest()).decode("ascii")
    return hmac.compare_digest(expected, signature)
