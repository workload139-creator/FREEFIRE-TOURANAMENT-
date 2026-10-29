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
    combined = sorted(
        wallet_transactions + ledger_transactions + registration_history,
        key=lambda item: item["_sort"],
        reverse=True,
    )[:100]
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
