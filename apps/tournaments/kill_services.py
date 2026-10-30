from decimal import Decimal, InvalidOperation


def rewards_for_tournament(tournament, kills):
    """Return every wallet currency reward for approved kills."""
    try:
        kills = int(kills)
    except (TypeError, ValueError, InvalidOperation):
        raise ValueError("Kill count must be a whole number.")
    if kills < 0:
        raise ValueError("Kill count cannot be negative.")
    if tournament.mode == "VS":
        return [("coins", kills * 2, "Coins")]
    if getattr(tournament, "is_diwali_offer", False):
        quantity = kills * 5
        return [("coins", quantity, "Coins")] if quantity else []
    if tournament.is_free_fan_tournament:
        quantity = kills // 2
        return [("fan_tokens", quantity, "Fan Tokens")] if quantity else []
    if tournament.mode == "BR":
        rewards = [("diamonds", kills * 5, "Diamonds")]
        if tournament.br_format in ("duo", "squad"):
            rewards.append(("coins", kills * 2, "Coins"))
        return [item for item in rewards if item[1] > 0]
    return [("coins", kills * 2, "Coins")]


def reward_for_tournament(tournament, kills):
    """Backward-compatible primary reward tuple for existing callers."""
    rewards = rewards_for_tournament(tournament, kills)
    if rewards:
        return rewards[0]
    if tournament.is_free_fan_tournament:
        return "fan_tokens", 0, "Fan Tokens"
    if tournament.mode == "VS":
        return "coins", 0, "Coins"
    return "diamonds", 0, "Diamonds"


def calculate_proposed_reward(kills):
    """Legacy helper retained for callers that use the default Diamond rate."""
    try:
        kills = int(kills)
    except (TypeError, ValueError, InvalidOperation):
        raise ValueError("Kill count must be a whole number.")
    if kills < 0:
        raise ValueError("Kill count cannot be negative.")
    return Decimal("5.00") * kills


def calculate_approved_reward(approved_kills, admin_approved=False):
    if not admin_approved:
        raise ValueError("Admin approval is required before finalizing reward.")
    return calculate_proposed_reward(approved_kills)

def finalize_dual_ai_reward(submission, result):
    """Credit a reward only after strict website checks and two agreeing high-confidence AIs."""
    from decimal import Decimal
    from django.conf import settings
    from django.db import transaction
    from django.utils import timezone
    from .models import KillSubmission, Registration, TournamentLedgerEntry

    proposed = result.get("proposed_kills")
    if (
        result.get("dual_agreement") is not True
        or result.get("confidence") != "high"
        or result.get("uid_matches") is not True
        or result.get("history_consistent") is not True
        or result.get("evidence_complete") is not True
        or str(result.get("observed_uid") or "").strip() != str(submission.registered_uid or "").strip()
        or proposed is None
    ):
        return False, "Both AI reviews must agree with high confidence and complete matching Free Fire evidence."

    try:
        kills = int(proposed)
    except (TypeError, ValueError):
        return False, "AI returned an invalid kill count."

    registration = submission.registration
    profile_uid = str(getattr(submission.player, "free_fire_uid", "") or "").strip()
    if not (
        kills >= settings.MINIMUM_VERIFIED_KILLS
        and kills <= 99
        and submission.free_fire_uid == submission.registered_uid
        and submission.registered_uid == registration.free_fire_uid
        and profile_uid == registration.free_fire_uid
        and registration.payment_verified
        and not registration.refund_processed
        and registration.status in (
            Registration.Status.CONFIRMED,
            Registration.Status.WAITING_READY,
            Registration.Status.READY,
        )
        and submission.tournament_id == registration.tournament_id
        and submission.player_id == registration.player_id
    ):
        return False, "Player profile, UID, payment or registration details need Admin review."

    rewards = rewards_for_tournament(submission.tournament, kills)
    if not rewards:
        return False, "Verified kills do not produce a reward under this tournament's rules."

    from apps.social.models import PlayerShopWallet

    with transaction.atomic():
        locked = KillSubmission.objects.select_for_update().select_related(
            "registration", "player", "tournament"
        ).get(pk=submission.pk)
        if locked.status != KillSubmission.Status.PENDING:
            return False, "Submission was already reviewed."
        references = [f"KILL-REWARD-{locked.pk}" if index == 0 else f"KILL-REWARD-{locked.pk}-{currency.upper()}" for index, (currency, quantity, label) in enumerate(rewards)]
        if TournamentLedgerEntry.objects.filter(reference__in=references).exists():
            return False, "A reward ledger entry already exists; Admin must reconcile this record."

        wallet, _ = PlayerShopWallet.objects.get_or_create(user=locked.player)
        wallet = PlayerShopWallet.objects.select_for_update().get(pk=wallet.pk)
        for index, (currency, quantity, label) in enumerate(rewards):
            wallet_field = {"diamonds": "diamonds", "coins": "coins", "fan_tokens": "fan_tokens"}[currency]
            setattr(wallet, wallet_field, getattr(wallet, wallet_field) + quantity)
            TournamentLedgerEntry.objects.create(
                reference=references[index], tournament=locked.tournament,
                player=locked.player, registration=locked.registration,
                entry_type=TournamentLedgerEntry.EntryType.REWARD,
                currency=currency, quantity=quantity, amount_inr=Decimal("0.00"),
                status=TournamentLedgerEntry.Status.COMPLETED,
                description=f"Dual-AI verified: {kills} kills; {quantity} {label} credited automatically.",
            )
        wallet.save(update_fields=("diamonds", "coins", "fan_tokens", "updated_at"))
        primary_quantity = rewards[0][1]
        coins_quantity = next((quantity for currency, quantity, label in rewards if currency == "coins"), 0)
        locked.ai_proposed_kills = kills
        locked.ai_confidence = "high"
        locked.ai_uid_matches = True
        locked.proposed_reward = Decimal(primary_quantity)
        locked.approved_kills = kills
        locked.approved_reward = Decimal(primary_quantity)
        locked.proposed_coins_reward = coins_quantity
        locked.approved_coins_reward = coins_quantity
        locked.admin_notes = (
            "Automatically approved: both independent AI assessments agreed with high confidence; "
            "website UID, profile, payment, registration and evidence checks passed."
        )
        locked.reviewed_at = timezone.now()
        locked.status = KillSubmission.Status.APPROVED
        locked.save(update_fields=[
            "ai_proposed_kills", "ai_confidence", "ai_uid_matches",
            "proposed_reward", "approved_kills", "approved_reward",
            "proposed_coins_reward", "approved_coins_reward",
            "admin_notes", "reviewed_at", "status",
        ])
    detail = " + ".join(f"{quantity} {label}" for currency, quantity, label in rewards)
    return True, f"{kills} verified kills: {detail} credited."

