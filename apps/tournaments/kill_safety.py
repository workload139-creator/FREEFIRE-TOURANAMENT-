"""Deterministic safeguards for Free Fire match evidence and one-time rewards."""
from datetime import datetime
from django.utils import timezone


_REVIEWER_KEYS = (
    "ff_arena_assessment_local_1",
    "ff_arena_assessment_local_2",
    "ff_arena_agent_local_1",
    "ff_arena_agent_local_2",
)


def _parse_match_date(value):
    """Parse common Free Fire history date formats; ambiguous numeric dates are day-first."""
    raw = str(value or "").strip()
    if not raw:
        return None
    normalized = raw.replace(" UTC", "+00:00").replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is not None:
            return timezone.localtime(parsed).date()
        return parsed.date()
    except (TypeError, ValueError):
        pass
    for fmt in (
        "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y",
        "%Y/%m/%d", "%Y-%m-%d", "%Y.%m.%d",
        "%d/%m/%Y %H:%M", "%d-%m-%Y %H:%M",
        "%Y-%m-%d %H:%M", "%d %b %Y", "%d %B %Y",
    ):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def validate_match_dates(reviewer_reports, tournament):
    """Require all four reviewers to agree on a readable date on tournament day or the following day."""
    reports = reviewer_reports if isinstance(reviewer_reports, dict) else {}
    dates = []
    for key in _REVIEWER_KEYS:
        report = reports.get(key) or {}
        if report.get("status") != "COMPLETED":
            return False, "All four AI reviewers must complete before date validation."
        parsed = _parse_match_date(report.get("match_date"))
        if parsed is None:
            return False, "Match date is missing or unreadable in one or more history reviews."
        dates.append(parsed)
    if len(set(dates)) != 1:
        return False, "AI reviewers did not agree on the match-history date."
    # Date-free rounds can remain open for registration for many days. Validate
    # evidence against the actual LIVE session where possible, not the round's
    # creation timestamp; fall back to the status-change timestamp for older events.
    live_sessions = getattr(tournament, "live_sessions", None)
    live_started_at = (
        live_sessions.order_by("started_at").values_list("started_at", flat=True).first()
        if live_sessions is not None else None
    )
    reference_time = live_started_at or (
        tournament.updated_at
        if getattr(tournament, "status", "") in ("live", "completed")
        else tournament.start_time
    )
    tournament_date = timezone.localtime(reference_time).date()
    observed = dates[0]
    # Match history may roll over after midnight, so allow tournament day and
    # the following calendar day, but never a pre-tournament screenshot.
    if (observed - tournament_date).days not in (0, 1):
        return False, (
            f"Match-history date {observed.isoformat()} is outside the allowed "
            f"tournament window around {tournament_date.isoformat()}."
        )
    return True, f"All four reviewers agree on match date {observed.isoformat()}."


def get_match_id(reviewer_reports):
    """Return a match ID only when all four completed reviewers agree on one non-empty ID."""
    reports = reviewer_reports if isinstance(reviewer_reports, dict) else {}
    values = []
    for key in _REVIEWER_KEYS:
        report = reports.get(key) or {}
        if report.get("status") != "COMPLETED":
            return ""
        value = str(report.get("match_id") or "").strip()
        if not value:
            return ""
        values.append(value.casefold())
    return values[0] if len(set(values)) == 1 else ""


def has_duplicate_match_id(submission):
    """A UID cannot claim the same match ID twice in the same tournament."""
    match_id = get_match_id(submission.ai_reviewer_reports)
    if not match_id:
        return False
    candidates = type(submission).objects.filter(
        tournament_id=submission.tournament_id,
        registered_uid=submission.registered_uid,
    ).exclude(pk=submission.pk).only("id", "ai_reviewer_reports")
    for candidate in candidates.iterator():
        if get_match_id(candidate.ai_reviewer_reports) == match_id:
            return True
    return False
