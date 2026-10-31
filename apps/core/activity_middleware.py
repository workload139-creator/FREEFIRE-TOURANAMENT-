from .models import PlayerActivityEvent


class PlayerActivityErrorMiddleware:
    """Record player-facing server errors without storing query strings or secrets."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if (
            response.status_code >= 500
            and not request.path.startswith(("/static/", "/media/", "/health/"))
        ):
            user = getattr(request, "user", None)
            try:
                PlayerActivityEvent.objects.create(
                    player=user if user is not None and user.is_authenticated else None,
                    category=PlayerActivityEvent.Category.SYSTEM,
                    event_type="http.server_error",
                    object_type="http.request",
                    object_id="",
                    object_status=str(response.status_code),
                    summary=f"Server error {response.status_code} on {request.method} {request.path[:150]}",
                    metadata={"method": request.method, "path": request.path[:200]},
                    assessment_state="complete",
                    assessment_summary="Assessment flagged a server response with status 500 or higher.",
                    agent_state="complete",
                    agent_summary="Agent recommends checking Render application logs and the linked player workflow.",
                    risk_level=PlayerActivityEvent.Risk.HIGH,
                    risk_score=85,
                    requires_admin_review=True,
                )
            except Exception:
                pass
        return response
