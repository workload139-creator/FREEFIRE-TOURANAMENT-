"""Four independent local review stages for live kill candidates.

These are deterministic evidence agents, not external LLMs. They report missing
proof explicitly and never approve events or issue rewards.
"""
import re


def run_four_stage_review(event, live_slot):
    registration = event.registration
    player = registration.player
    text = " ".join(str(event.detected_text or "").casefold().split())
    kill_signal = bool(re.search(r"\b(eliminated|knocked|headshot|kill|killed)\b", text))
    identity_ok = bool(
        live_slot
        and live_slot.identity_verified_at
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
        "ff_arena_assessment_local_1": {
            "status": "COMPLETED",
            "stage": "player_identity",
            "passed": identity_ok,
            "reason": "Registered UID matches account and Live AI identity." if identity_ok else "Player identity is not fully verified.",
        },
        "ff_arena_assessment_local_2": {
            "status": "COMPLETED",
            "stage": "tournament_eligibility",
            "passed": eligibility_ok,
            "reason": "Tournament and paid registration are eligible." if eligibility_ok else "Tournament/session/payment eligibility failed.",
        },
        "ff_arena_agent_local_1": {
            "status": "COMPLETED",
            "stage": "killfeed_signal",
            "passed": kill_signal,
            "reason": "Killfeed keyword signal found; OCR alone is not proof." if kill_signal else "No recognized killfeed signal.",
        },
        "ff_arena_agent_local_2": {
            "status": "COMPLETED",
            "stage": "killer_attribution_and_match",
            "passed": attribution_ok,
            "reason": "Killer nickname and match/time metadata are present." if attribution_ok else "Cannot attribute this kill to the registered in-game player; nickname/match/time evidence is missing.",
        },
    }
    return reports
