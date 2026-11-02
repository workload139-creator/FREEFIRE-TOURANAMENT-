from django.http import JsonResponse
from django.views.decorators.http import require_GET

from .models import Wallet


def _require_player(request):
    if not request.user.is_authenticated:
        return JsonResponse(
            {"success": False, "error": "authentication_required", "message": "Please log in to your FF Arena account."},
            status=401,
        )
    return None


@require_GET
def native_profile_api(request):
    denied = _require_player(request)
    if denied:
        return denied

    user = request.user
    photo = ""
    if user.profile_photo:
        photo = request.build_absolute_uri(user.profile_photo.url)

    return JsonResponse({
        "success": True,
        "profile": {
            "id": user.pk,
            "username": user.username,
            "email": user.email,
            "phone_number": user.phone_number or "",
            "phone_verified": user.phone_verified,
            "free_fire_uid": user.free_fire_uid or "",
            "uid_verified": user.uid_verified,
            "profile_photo": photo,
        },
    })


@require_GET
def native_wallet_api(request):
    denied = _require_player(request)
    if denied:
        return denied

    wallet, _ = Wallet.objects.get_or_create(user=request.user)
    from apps.tournaments.models import Registration, TournamentLedgerEntry
    from apps.social.models import (
        PlayerShopWalletTransaction, ShopPaymentRequest,
        CurrencyWithdrawalRequest, DailySpin, CurrencyGift,
    )

    # Combine wallet transactions with tournament entries/refunds/rewards so the
    # native app shows the same server-side audit history as the website.
    wallet_transactions = [
        {
            "type": item.transaction_type,
            "status": item.get_status_display(),
            "amount": str(item.amount),
            "currency": "INR",
            "quantity": "",
            "description": item.description or item.get_transaction_type_display(),
            "reference": item.reference or "",
            "created_at": item.created_at.isoformat(),
            "_sort": item.created_at.timestamp(),
        }
        for item in wallet.transactions.order_by("-created_at")[:50]
    ]
    ledger_transactions = [
        {
            "type": item.get_entry_type_display(),
            "status": item.get_status_display(),
            "amount": str(item.amount_inr),
            "currency": item.currency.upper(),
            "quantity": item.quantity,
            "description": (item.tournament.title + " — " + (item.description or item.get_entry_type_display())),
            "reference": item.reference or "",
            "created_at": item.created_at.isoformat(),
            "_sort": item.created_at.timestamp(),
        }
        for item in TournamentLedgerEntry.objects.filter(player=request.user)
            .select_related("tournament").order_by("-created_at")[:100]
    ]
    registration_history = [
        {
            "type": "Tournament Registration",
            "status": item.get_status_display(),
            "amount": str(item.entry_fee_paid),
            "currency": "INR",
            "quantity": "",
            "description": item.tournament.title + " — " + item.get_status_display(),
            "reference": item.refund_reference or item.payment_reference or ("REG-" + str(item.pk)),
            "created_at": item.updated_at.isoformat(),
            "_sort": item.updated_at.timestamp(),
        }
        for item in Registration.objects.filter(player=request.user)
            .select_related("tournament").order_by("-updated_at")[:50]
    ]
    # Every query is scoped to the authenticated player; never return another
    # player's purchases, withdrawals, rewards, or gift activity.
    shop_ledger = [
        {
            "type": "Shop " + item.get_source_display() if hasattr(item, "get_source_display") else "Shop wallet " + item.source,
            "status": "Completed",
            "amount": "",
            "currency": item.get_currency_display(),
            "quantity": item.quantity if item.direction == "credit" else -item.quantity,
            "description": item.description or (item.get_direction_display() + " · " + item.get_currency_display()),
            "reference": item.reference or "",
            "created_at": item.created_at.isoformat(),
            "_sort": item.created_at.timestamp(),
        }
        for item in PlayerShopWalletTransaction.objects.filter(user=request.user)
            .order_by("-created_at")[:100]
    ]
    shop_requests = [
        {
            "type": "Shop Purchase",
            "status": item.get_status_display(),
            "amount": str(item.amount),
            "currency": "INR",
            "quantity": item.quantity,
            "description": item.get_product_display() + " purchase request",
            "reference": item.payment_reference or ("SHOP-" + str(item.pk)),
            "created_at": item.created_at.isoformat(),
            "_sort": item.created_at.timestamp(),
        }
        for item in ShopPaymentRequest.objects.filter(user=request.user).order_by("-created_at")[:50]
    ]
    currency_withdrawals = [
        {
            "type": "Currency Withdrawal",
            "status": item.get_status_display(),
            "amount": str(item.amount_inr),
            "currency": "INR",
            "quantity": item.quantity,
            "description": item.get_currency_display() + " withdrawal to " + item.upi_id,
            "reference": item.payout_reference or ("CURRENCY-WITHDRAW-" + str(item.pk)),
            "created_at": item.created_at.isoformat(),
            "_sort": item.created_at.timestamp(),
        }
        for item in CurrencyWithdrawalRequest.objects.filter(user=request.user).order_by("-created_at")[:50]
    ]
    spin_rewards = [
        {
            "type": "Daily Spin Reward",
            "status": "Completed",
            "amount": "",
            "currency": item.get_currency_display(),
            "quantity": item.quantity,
            "description": "Daily Spin reward received",
            "reference": "SPIN-" + str(item.pk),
            "created_at": item.spun_at.isoformat(),
            "_sort": item.spun_at.timestamp(),
        }
        for item in DailySpin.objects.filter(user=request.user).order_by("-spun_at")[:100]
    ]
    # CurrencyGift has sender/recipient fields, so explicitly scope either side.
    from django.db.models import Q
    gift_history = [
        {
            "type": "Gift Sent" if item.sender_id == request.user.pk else "Gift Received",
            "status": "Completed",
            "amount": "",
            "currency": item.get_currency_display(),
            "quantity": item.quantity if item.recipient_id == request.user.pk else -item.quantity,
            "description": ("Sent to " + item.recipient.username) if item.sender_id == request.user.pk else ("Received from " + item.sender.username),
            "reference": "GIFT-" + str(item.pk),
            "created_at": item.created_at.isoformat(),
            "_sort": item.created_at.timestamp(),
        }
        for item in CurrencyGift.objects.filter(
            Q(sender=request.user) | Q(recipient=request.user)
        ).select_related("sender", "recipient").order_by("-created_at")[:100]
    ]
    combined = sorted(
        wallet_transactions + ledger_transactions + registration_history
        + shop_ledger + shop_requests + currency_withdrawals + spin_rewards + gift_history,
        key=lambda item: item["_sort"],
        reverse=True,
    )[:200]
    for item in combined:
        item.pop("_sort", None)

    return JsonResponse({
        "success": True,
        "wallet": {
            "wallet_id": wallet.wallet_id,
            "balance": str(wallet.balance),
            "currency": "INR",
        },
        "transactions": combined,
    })
