from decimal import Decimal

from django.apps import apps
from django.db import transaction


def _safe_metadata(instance):
    values = {}
    for name in (
        "status", "payment_method", "payment_verified", "refund_processed",
        "currency", "product", "quantity", "amount", "amount_inr",
        "currency_amount", "transaction_type", "direction", "source",
        "balance_after", "entry_type", "diamonds", "coins", "fan_tokens",
        "balance", "gender", "profile_visibility", "uid_verified", "phone_verified",
    ):
        value = getattr(instance, name, None)
        if value is not None:
            values[name] = str(value) if isinstance(value, Decimal) else value
    if hasattr(instance, "free_fire_uid"):
        values["has_free_fire_uid"] = bool(getattr(instance, "free_fire_uid", ""))
    if hasattr(instance, "phone_number"):
        values["has_phone_number"] = bool(getattr(instance, "phone_number", ""))
    if hasattr(instance, "email"):
        values["has_email"] = bool(getattr(instance, "email", ""))
    if hasattr(instance, "payment_reference"):
        values["has_payment_reference"] = bool(getattr(instance, "payment_reference", ""))
    if hasattr(instance, "payout_reference"):
        values["has_payout_reference"] = bool(getattr(instance, "payout_reference", ""))
    return values


def _player_id(instance):
    for name in (
        "player_id", "user_id", "author_id", "reporter_id", "requester_id",
        "sender_id", "follower_id", "blocker_id",
    ):
        value = getattr(instance, name, None)
        if value:
            return value
    wallet_id = getattr(instance, "wallet_id", None)
    if wallet_id:
        Wallet = apps.get_model("accounts", "Wallet")
        return Wallet.objects.filter(pk=wallet_id).values_list("user_id", flat=True).first()
    return None


def assess_activity_event(event_id):
    """Two explainable local passes; no external AI provider or player secrets."""
    from .models import PlayerActivityEvent

    event = PlayerActivityEvent.objects.filter(pk=event_id).first()
    if not event:
        return
    risk = PlayerActivityEvent.Risk.INFO
    score = 0
    finding = ""
    model = event.object_type
    object_id = event.object_id

    try:
        if model == "social.shoppaymentrequest" and event.object_status == "approved":
            ShopTxn = apps.get_model("social", "PlayerShopWalletTransaction")
            if not ShopTxn.objects.filter(idempotency_key=f"shop-payment:{object_id}").exists():
                risk, score = PlayerActivityEvent.Risk.CRITICAL, 100
                finding = "Shop request approved but its unique wallet credit ledger entry is missing."
        elif model == "social.currencywithdrawalrequest":
            Withdrawal = apps.get_model("social", "CurrencyWithdrawalRequest")
            ShopTxn = apps.get_model("social", "PlayerShopWalletTransaction")
            item = Withdrawal.objects.filter(pk=object_id).only("status").first()
            if item:
                key = (
                    f"currency-withdrawal:{object_id}:refund"
                    if item.status == "rejected"
                    else f"currency-withdrawal:{object_id}:debit"
                )
                if not ShopTxn.objects.filter(idempotency_key=key).exists():
                    risk, score = PlayerActivityEvent.Risk.CRITICAL, 100
                    finding = f"Currency withdrawal status is {item.status}, but its matching debit/refund ledger entry is missing."
        elif model == "tournaments.registration":
            Registration = apps.get_model("tournaments", "Registration")
            Ledger = apps.get_model("tournaments", "TournamentLedgerEntry")
            item = Registration.objects.filter(pk=object_id).first()
            if item:
                if item.refund_processed and not Ledger.objects.filter(
                    registration_id=item.pk, entry_type="refund", status="completed"
                ).exists():
                    risk, score = PlayerActivityEvent.Risk.CRITICAL, 100
                    finding = "Registration is marked refunded but the completed tournament refund ledger entry is missing."
                elif item.payment_verified and not Ledger.objects.filter(
                    registration_id=item.pk, entry_type="entry", status="completed"
                ).exists():
                    risk, score = PlayerActivityEvent.Risk.CRITICAL, 100
                    finding = "Registration is marked paid/verified but its completed entry ledger entry is missing."
                elif item.payment_verified and item.payment_method in ("diamonds", "coins", "fan_tokens") and item.currency_amount <= 0:
                    risk, score = PlayerActivityEvent.Risk.HIGH, 85
                    finding = "Currency-paid registration has a zero or invalid currency amount."
        elif model == "accounts.wallet":
            Wallet = apps.get_model("accounts", "Wallet")
            item = Wallet.objects.filter(pk=object_id).only("balance").first()
            if item and item.balance < 0:
                risk, score = PlayerActivityEvent.Risk.CRITICAL, 100
                finding = "INR wallet balance is negative."
        elif model == "accounts.wallettransaction" and event.object_status == "failed":
            risk, score = PlayerActivityEvent.Risk.MEDIUM, 55
            finding = "A wallet transaction is marked failed and needs reconciliation."
        elif model == "social.playershopwallettransaction" and int(event.metadata.get("quantity", 0) or 0) <= 0:
            risk, score = PlayerActivityEvent.Risk.HIGH, 80
            finding = "A shop-wallet ledger transaction has a zero or invalid quantity."
    except Exception:
        risk, score = PlayerActivityEvent.Risk.MEDIUM, 60
        finding = "Automated integrity check could not complete; admin verification is required."

    if finding:
        assessment = "Assessment flagged: " + finding
        agent = "Agent cross-check: " + finding + " Do not manually credit or debit until the linked records are reconciled."
    else:
        assessment = "Assessment checked this activity and found no configured ledger mismatch."
        agent = "Agent cross-check completed. No rule-based discrepancy was found in the linked records."

    PlayerActivityEvent.objects.filter(pk=event_id).update(
        assessment_state="complete",
        assessment_summary=assessment,
        agent_state="complete",
        agent_summary=agent,
        risk_level=risk,
        risk_score=score,
        requires_admin_review=bool(finding),
    )


def record_player_activity(instance, created=False, category=None):
    from .models import PlayerActivityEvent

    model_label = instance._meta.label_lower
    category = category or _category_for(model_label)
    status = str(getattr(instance, "status", "") or "")
    player_id = _player_id(instance)
    action = "created" if created else "updated"
    try:
        event = PlayerActivityEvent.objects.create(
            player_id=player_id,
            category=category,
            event_type=f"{model_label}.{action}",
            object_type=model_label,
            object_id=str(instance.pk),
            object_status=status[:32],
            summary=f"{model_label} #{instance.pk} {action}" + (f" · {status}" if status else ""),
            metadata=_safe_metadata(instance),
        )
        transaction.on_commit(lambda event_id=event.pk: assess_activity_event(event_id))
    except Exception:
        # Monitoring must never interrupt a player's purchase, registration or refund.
        return


def _category_for(label):
    if label == "accounts.user":
        return "profile"
    if label.startswith("accounts."):
        return "wallet"
    if label in ("social.playershopwallet", "social.playershopwallettransaction"):
        return "wallet"
    if label == "social.shoppaymentrequest":
        return "shop"
    if label == "social.currencywithdrawalrequest":
        return "withdrawal"
    if label.startswith("social."):
        return "social"
    if label.startswith("tournaments."):
        return "tournament"
    return "system"
