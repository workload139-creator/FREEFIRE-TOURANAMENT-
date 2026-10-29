from datetime import timedelta
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts.models import Wallet, WalletTransaction
from apps.social.models import PlayerShopWallet
from .models import Registration, TournamentLedgerEntry


@transaction.atomic
@login_required
@require_POST
def request_tournament_diamond_refund(request, registration_id):
    """Refund a verified entry into the player's original internal wallet currency."""
    registration = get_object_or_404(
        Registration.objects.select_for_update().select_related("tournament", "player"),
        pk=registration_id,
        player=request.user,
    )
    tournament = registration.tournament
    now = timezone.now()

    # Recover older NOT_PLAYING registrations that were marked before the refund fix.
    # Only verified payments can be claimed, and the row lock + stable reference prevent duplicates.
    if registration.status == Registration.Status.NOT_PLAYING and not registration.refund_processed:
        if not registration.payment_verified:
            messages.error(request, "Payment verified nahi hai; refund credit nahi kiya ja sakta.")
            return redirect("tournaments:my_registrations")
        amount = Decimal(str(registration.entry_fee_paid or tournament.entry_fee))
        reference = f"NOTPLAYING-REFUND-{registration.pk}"
        if WalletTransaction.objects.filter(reference=reference).exists() or TournamentLedgerEntry.objects.filter(reference=reference).exists():
            messages.error(request, "Is registration ka refund transaction pehle se record hai. Duplicate credit nahi kiya gaya.")
            return redirect("tournaments:my_registrations")
        if amount <= 0:
            messages.error(request, "Is registration ki refundable amount nahi hai.")
            return redirect("tournaments:my_registrations")
        if registration.payment_method in ("diamonds", "coins", "fan_tokens"):
            quantity = registration.currency_amount
            if quantity <= 0:
                messages.error(request, "Original currency amount nahi mila; admin support se contact karein.")
                return redirect("tournaments:my_registrations")
            shop_wallet, _ = PlayerShopWallet.objects.get_or_create(user=request.user)
            shop_wallet = PlayerShopWallet.objects.select_for_update().get(pk=shop_wallet.pk)
            setattr(shop_wallet, registration.payment_method, getattr(shop_wallet, registration.payment_method) + quantity)
            shop_wallet.save(update_fields=["diamonds", "coins", "fan_tokens", "updated_at"])
            currency = registration.payment_method
        elif registration.payment_method == "upi":
            wallet, _ = Wallet.objects.get_or_create(user=request.user)
            wallet = Wallet.objects.select_for_update().get(pk=wallet.pk)
            wallet.balance += amount
            wallet.save(update_fields=["balance", "updated_at"])
            WalletTransaction.objects.get_or_create(
                reference=reference,
                defaults={
                    "wallet": wallet,
                    "transaction_type": WalletTransaction.TransactionType.REFUND,
                    "amount": amount,
                    "status": WalletTransaction.Status.COMPLETED,
                    "description": f"Refund for previously marked NOT_PLAYING registration {registration.pk}.",
                },
            )
            quantity = 0
            currency = TournamentLedgerEntry.Currency.INR
        else:
            messages.error(request, "Is payment method ka automatic refund supported nahi hai; admin se contact karein.")
            return redirect("tournaments:my_registrations")

        registration.status = Registration.Status.REFUNDED
        registration.refund_processed = True
        registration.refund_processed_at = now
        registration.refund_reference = reference
        registration.room_details_sent = False
        registration.save(update_fields=[
            "status", "refund_processed", "refund_processed_at",
            "refund_reference", "room_details_sent", "updated_at",
        ])
        TournamentLedgerEntry.objects.get_or_create(
            reference=reference,
            defaults={
                "tournament": tournament,
                "player": request.user,
                "registration": registration,
                "entry_type": TournamentLedgerEntry.EntryType.REFUND,
                "currency": currency,
                "quantity": quantity,
                "amount_inr": amount,
                "status": TournamentLedgerEntry.Status.COMPLETED,
                "description": "One-time refund claimed for an older verified NOT_PLAYING registration.",
            },
        )
        messages.success(request, "Refund complete. Amount original wallet mein credit ho gaya.")
        return redirect("tournaments:my_registrations")

    if registration.refund_processed or registration.status in (
        Registration.Status.CANCELLED,
        Registration.Status.REFUNDED,
        Registration.Status.NOT_PLAYING,
    ):
        messages.error(request, "Is registration ka refund pehle hi process ho chuka hai ya ab available nahi hai.")
        return redirect("tournaments:my_registrations")

    if not registration.payment_verified or registration.status not in (
        Registration.Status.CONFIRMED,
        Registration.Status.WAITING_READY,
        Registration.Status.READY,
    ):
        messages.error(request, "Refund ke liye registration ki payment verified honi chahiye.")
        return redirect("tournaments:my_registrations")

    if tournament.status != tournament.Status.UPCOMING:
        messages.error(request, "Tournament live, completed ya cancelled hai; self-refund available nahi hai.")
        return redirect("tournaments:my_registrations")

    if not (tournament.start_time - timedelta(hours=1) <= now < tournament.start_time):
        messages.error(request, "Self-refund sirf tournament start hone se aakhri 1 ghante ke andar available hai.")
        return redirect("tournaments:my_registrations")

    amount = Decimal(str(registration.entry_fee_paid or tournament.entry_fee))
    if amount <= 0:
        messages.error(request, "Is free entry ka refund amount nahi hai.")
        return redirect("tournaments:my_registrations")

    reference = f"SELF-REFUND-{registration.pk}"
    if (
        TournamentLedgerEntry.objects.filter(reference=reference).exists()
        or WalletTransaction.objects.filter(reference=reference).exists()
    ):
        messages.error(request, "Is registration ka refund record pehle se maujood hai.")
        return redirect("tournaments:my_registrations")

    if registration.payment_method in ("diamonds", "coins", "fan_tokens"):
        quantity = registration.currency_amount
        if quantity <= 0:
            messages.error(request, "Refund currency amount available nahi hai; admin support se contact karein.")
            return redirect("tournaments:my_registrations")
        shop_wallet, _ = PlayerShopWallet.objects.get_or_create(user=request.user)
        shop_wallet = PlayerShopWallet.objects.select_for_update().get(pk=shop_wallet.pk)
        setattr(shop_wallet, registration.payment_method, getattr(shop_wallet, registration.payment_method) + quantity)
        shop_wallet.save(update_fields=["diamonds", "coins", "fan_tokens", "updated_at"])
        currency = registration.payment_method
        description = f"Self-refund within the final hour; returned {quantity} {currency}."
        success_message = f"Refund complete: {quantity} {currency} aapke wallet mein add ho gaye."
    elif registration.payment_method == "upi":
        wallet, _ = Wallet.objects.get_or_create(user=request.user)
        wallet = Wallet.objects.select_for_update().get(pk=wallet.pk)
        wallet.balance += amount
        wallet.save(update_fields=["balance", "updated_at"])
        WalletTransaction.objects.create(
            wallet=wallet,
            transaction_type=WalletTransaction.TransactionType.REFUND,
            amount=amount,
            status=WalletTransaction.Status.COMPLETED,
            reference=reference,
            description=f"Verified tournament entry self-refund for registration {registration.pk}.",
        )
        quantity = 0
        currency = TournamentLedgerEntry.Currency.INR
        description = "Verified UPI entry fee credited to the player's internal INR wallet during the final-hour self-refund window."
        success_message = f"Refund complete: ₹{amount} aapke INR wallet mein add ho gaye."
    else:
        messages.error(request, "Is payment method ka automatic refund supported nahi hai; admin se contact karein.")
        return redirect("tournaments:my_registrations")

    registration.status = Registration.Status.REFUNDED
    registration.refund_processed = True
    registration.refund_processed_at = now
    registration.refund_reference = reference
    registration.room_details_sent = False
    registration.save(update_fields=[
        "status", "refund_processed", "refund_processed_at",
        "refund_reference", "room_details_sent", "updated_at",
    ])

    TournamentLedgerEntry.objects.create(
        reference=reference,
        tournament=tournament,
        player=request.user,
        registration=registration,
        entry_type=TournamentLedgerEntry.EntryType.REFUND,
        currency=currency,
        quantity=quantity,
        amount_inr=amount,
        status=TournamentLedgerEntry.Status.COMPLETED,
        description=description,
    )
    messages.success(request, success_message)
    return redirect("tournaments:my_registrations")
