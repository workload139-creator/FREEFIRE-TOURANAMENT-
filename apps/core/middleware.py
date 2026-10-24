from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone


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
