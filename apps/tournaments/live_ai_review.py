"""Two independent local analysis agents for live kill candidates.

These are deterministic evidence agents, not external LLMs. They report missing
proof explicitly and never approve events or issue rewards.
"""
import re


def run_two_agent_review(event, live_session):
    registration = event.registration
    player = registration.player
    text = " ".join(str(event.detected_text or "").casefold().split())
    kill_signal = bool(re.search(r"\b(eliminated|knocked|headshot|kill|killed)\b", text))
    identity_ok = bool(
        live_session
        and live_session.identity_verified_at
        and registration.free_fire_uid
        and registration.free_fire_uid == getattr(player, "free_fire_uid", "")
        and getattr(player, "uid_verified", False)
    )
    eligibility_ok = bool(
        event.tournament.status == "live"
        and event.tournament.mode in ("BR", "VS")
        and registration.status == "ready"
        and registration.payment_verified
        and not registration.refund_processed
        and event.session.status == "active"
    )
    # The current stream OCR does not yet capture a verified in-game killer
    # nickname or stable match identifier. Do not infer either from account name.
    attribution_ok = bool(
        event.match_id
        and event.kill_at
        and getattr(event, "attributed_player_name", "")
    )
    reports = {
        "ff_arena_agent_local_1": {
            "status": "COMPLETED",
            "stage": "player_identity_and_tournament",
            "passed": identity_ok and eligibility_ok,
            "reason": "Player UID and tournament eligibility verified." if identity_ok and eligibility_ok else "Player identity or tournament eligibility is not verified.",
        },
        "ff_arena_agent_local_2": {
            "status": "COMPLETED",
            "stage": "kill_evidence_and_attribution",
            "passed": kill_signal and attribution_ok,
            "reason": "Kill signal and killer/match attribution evidence found." if kill_signal and attribution_ok else "Kill evidence or killer/match attribution is incomplete.",
        },
    }
    return reports
