from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.social.models import PlayerShopWallet
from .models import Registration, TournamentLedgerEntry


@transaction.atomic
@login_required
@require_POST
def request_tournament_diamond_refund(request, registration_id):
    """Return one entry-fee-equivalent Diamond refund in the final hour before start."""
    registration = get_object_or_404(
        Registration.objects.select_for_update().select_related("tournament", "player"),
        pk=registration_id,
        player=request.user,
    )
    tournament = registration.tournament
    now = timezone.now()

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

    if not (tournament.start_time - timezone.timedelta(hours=1) <= now < tournament.start_time):
        messages.error(request, "Diamond refund sirf tournament start hone se aakhri 1 ghante ke andar milta hai.")
        return redirect("tournaments:my_registrations")

    amount = Decimal(str(registration.entry_fee_paid or tournament.entry_fee))
    if amount <= 0 or amount != amount.to_integral_value():
        messages.error(request, "Is entry fee ka exact whole-Diamond refund automatically calculate nahi ho sakta. Admin support se contact karein.")
        return redirect("tournaments:my_registrations")

    quantity = int(amount)
    reference = f"SELF-DIAMOND-REFUND-{registration.pk}"
    if TournamentLedgerEntry.objects.filter(reference=reference).exists():
        messages.error(request, "Is registration ka refund record pehle se maujood hai.")
        return redirect("tournaments:my_registrations")

    wallet, _ = PlayerShopWallet.objects.get_or_create(user=request.user)
    wallet = PlayerShopWallet.objects.select_for_update().get(pk=wallet.pk)
    wallet.diamonds += quantity
    wallet.save(update_fields=["diamonds", "updated_at"])

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
        currency=TournamentLedgerEntry.Currency.DIAMONDS,
        quantity=quantity,
        amount_inr=amount,
        status=TournamentLedgerEntry.Status.COMPLETED,
        description="Player self-refund within one hour before tournament start; credited as Diamonds.",
    )
    messages.success(request, f"Refund complete: {quantity} Diamonds aapke wallet mein turant add ho gaye.")
    return redirect("tournaments:my_registrations")
