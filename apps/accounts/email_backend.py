import json
import urllib.error
import urllib.request
from email.utils import parseaddr

from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend
from django.core.exceptions import ImproperlyConfigured


class BrevoEmailBackend(BaseEmailBackend):
    """Send Django emails (including password-reset emails) through Brevo HTTPS API."""

    api_url = "https://api.brevo.com/v3/smtp/email"

    def send_messages(self, email_messages):
        if not email_messages:
            return 0

        api_key = getattr(settings, "BREVO_API_KEY", "").strip()
        if not api_key:
            raise ImproperlyConfigured("BREVO_API_KEY is not configured.")

        sent_count = 0
        for message in email_messages:
            sender_name, sender_email = parseaddr(
                message.from_email or settings.DEFAULT_FROM_EMAIL
            )
            if not sender_email:
                raise ImproperlyConfigured("DEFAULT_FROM_EMAIL must be a valid email address.")

            recipients = list(dict.fromkeys(
                (message.to or []) + (message.cc or []) + (message.bcc or [])
            ))
            if not recipients:
                continue

            payload = {
                "sender": {"name": sender_name or "FF Arena", "email": sender_email},
                "to": [{"email": address} for address in (message.to or [])],
                "subject": message.subject or "",
            }
            if message.cc:
                payload["cc"] = [{"email": address} for address in message.cc]
            if message.bcc:
                payload["bcc"] = [{"email": address} for address in message.bcc]

            text_content = message.body or ""
            html_content = None
            for alternative, mimetype in (getattr(message, "alternatives", None) or []):
                if mimetype == "text/html":
                    html_content = alternative
                elif mimetype == "text/plain":
                    text_content = alternative

            if html_content:
                payload["htmlContent"] = html_content
                if text_content:
                    payload["textContent"] = text_content
            elif getattr(message, "content_subtype", "plain") == "html":
                payload["htmlContent"] = text_content
            else:
                payload["textContent"] = text_content

            reply_to = getattr(message, "reply_to", None)
            if reply_to:
                reply_name, reply_email = parseaddr(reply_to[0])
                payload["replyTo"] = {"email": reply_email}
                if reply_name:
                    payload["replyTo"]["name"] = reply_name

            request = urllib.request.Request(
                self.api_url,
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "accept": "application/json",
                    "api-key": api_key,
                    "content-type": "application/json",
                },
                method="POST",
            )
            try:
                with urllib.request.urlopen(request, timeout=20) as response:
                    if response.status in (200, 201, 202):
                        sent_count += 1
                    else:
                        raise RuntimeError(
                            f"Brevo email API returned HTTP {response.status}."
                        )
            except urllib.error.HTTPError as exc:
                # Never expose provider response text or API credentials.
                raise RuntimeError(
                    f"Brevo email API rejected the message (HTTP {exc.code}). "
                    "Check the API key permissions and verified sender."
                ) from None
            except urllib.error.URLError:
                raise RuntimeError("Could not connect to the Brevo email API.") from None

        return sent_count
