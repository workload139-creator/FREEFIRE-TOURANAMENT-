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
    transactions = wallet.transactions.order_by("-created_at")[:10]
    return JsonResponse({
        "success": True,
        "wallet": {
            "wallet_id": wallet.wallet_id,
            "balance": str(wallet.balance),
            "currency": "INR",
        },
        "transactions": [
            {
                "type": item.transaction_type,
                "status": item.status,
                "amount": str(item.amount),
                "description": item.description,
                "created_at": item.created_at.isoformat(),
            }
            for item in transactions
        ],
    })
