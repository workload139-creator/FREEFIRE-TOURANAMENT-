from .models import PlayerActivityEvent


class PlayerActivityErrorMiddleware:
    """Record player-facing 4xx/5xx responses without storing query strings or secrets."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        user = getattr(request, "user", None)
        if (
            response.status_code >= 400
            and not request.path.startswith(("/static/", "/media/", "/health/"))
        ):
            try:
                is_server_error = response.status_code >= 500
                PlayerActivityEvent.objects.create(
                    player=user if user is not None and user.is_authenticated else None,
                    category=PlayerActivityEvent.Category.SYSTEM,
                    event_type="http.server_error" if is_server_error else "http.client_error",
                    object_type="http.request",
                    object_id="",
                    object_status=str(response.status_code),
                    summary=f"HTTP {response.status_code} on {request.method} {request.path[:150]}",
                    metadata={"method": request.method, "path": request.path[:200]},
                    assessment_state="complete",
                    assessment_summary="Assessment recorded a non-success HTTP response for investigation.",
                    agent_state="complete",
                    agent_summary="Agent recommends checking the related application log and player workflow before changing any balance.",
                    risk_level=PlayerActivityEvent.Risk.HIGH if is_server_error else PlayerActivityEvent.Risk.MEDIUM,
                    risk_score=85 if is_server_error else 55,
                    requires_admin_review=is_server_error or bool(user and user.is_authenticated),
                )
            except Exception:
                pass
        return response
