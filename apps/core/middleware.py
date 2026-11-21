import logging
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone

logger = logging.getLogger("django.request")


class ExceptionLoggingMiddleware:
    """Write full tracebacks for uncaught view exceptions without request secrets."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_exception(self, request, exception):
        user = getattr(request, "user", None)
        user_id = user.pk if user is not None and getattr(user, "is_authenticated", False) else None
        logger.error(
            "Unhandled request exception method=%s path=%s user_id=%s",
            request.method,
            request.path[:200],
            user_id,
            exc_info=(type(exception), exception, exception.__traceback__),
        )
        return None


class LastSeenMiddleware:
    """Update last_seen at most once per minute for authenticated users."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            now = timezone.now()
            last_seen = getattr(user, "last_seen", None)
            if last_seen is None or now - last_seen > timedelta(minutes=1):
                get_user_model().objects.filter(pk=user.pk).update(last_seen=now)
                user.last_seen = now
        return response
