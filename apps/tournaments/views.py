from datetime import timedelta
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts.models import Wallet, WalletTransaction, AdminWallet, AdminWalletTransaction
from .forms import RegistrationForm
from .models import Registration, Tournament


def tournament_list(request):
    tournaments = Tournament.objects.all().order_by("start_time")
    return render(
        request,
        "tournaments/list.html",
        {
            "tournaments": tournaments,
            "mode_groups": [
                ("BR", "Battle Royale"),
                ("VS", "VS Battles"),
            ],
        },
    )


def tournament_detail(request, tournament_id):
    tournament = get_object_or_404(Tournament, pk=tournament_id)
    return render(request, "tournaments/tournament_detail.html", {"tournament": tournament})


@login_required
def tournament_register(request, tournament_id):
    tournament = get_object_or_404(Tournament, pk=tournament_id)

    if request.method == "GET":
        if tournament.status != Tournament.Status.UPCOMING or tournament.start_time <= timezone.now() or tournament.is_full:
            messages.error(request, "Yeh tournament abhi registration ke liye available nahi hai.")
            return redirect("tournaments:list")
        if Registration.objects.filter(tournament=tournament, player=request.user).exists():
            messages.info(request, "Aap is tournament mein pehle se registered hain.")
            return redirect("tournaments:detail", tournament_id=tournament.pk)
        return render(request, "tournaments/register.html", {"tournament": tournament, "form": RegistrationForm()})

    if request.method != "POST":
        return redirect("tournaments:list")

    form = RegistrationForm(request.POST)
    if not form.is_valid():
        return render(request, "tournaments/register.html", {"tournament": tournament, "form": form})

    uid = form.cleaned_data["free_fire_uid"]
    try:
        with transaction.atomic():
            tournament = get_object_or_404(Tournament.objects.select_for_update(), pk=tournament_id)
            if tournament.status != Tournament.Status.UPCOMING or tournament.start_time <= timezone.now():
                messages.error(request, "Yeh tournament registration ke liye available nahi hai.")
                return redirect("tournaments:list")
            if tournament.is_full:
                messages.error(request, "Tournament full hai.")
                return redirect("tournaments:list")
            if Registration.objects.filter(tournament=tournament, player=request.user).exists():
                messages.info(request, "Aap pehle se registered hain.")
                return redirect("tournaments:detail", tournament_id=tournament.pk)

            wallet, _ = Wallet.objects.get_or_create(user=request.user)
            wallet = Wallet.objects.select_for_update().get(pk=wallet.pk)
            fee = tournament.entry_fee
            if wallet.balance < fee:
                messages.error(request, f"Wallet mein balance kam hai. Entry fee ₹{fee} hai; pehle wallet mein deposit request karein.")
                return redirect("accounts:wallet")

            registration = Registration.objects.create(
                tournament=tournament,
                player=request.user,
                free_fire_uid=uid,
                entry_fee_paid=fee,
                payment_verified=False,
                status=Registration.Status.PENDING_PAYMENT,
            )
            wallet.balance -= fee
            wallet.save(update_fields=["balance", "updated_at"])
            if fee > Decimal("0.00"):
                WalletTransaction.objects.create(
                    wallet=wallet,
                    transaction_type=WalletTransaction.TransactionType.ENTRY_FEE,
                    amount=fee,
                    status=WalletTransaction.Status.COMPLETED,
                    reference=f"TOURNEY-ENTRY-{registration.pk}",
                    description=f"Entry fee for tournament {tournament.title}; awaiting admin payment review",
                )
    except IntegrityError:
        messages.error(request, "Registration nahi ho saki; aap pehle se registered ho sakte hain.")
        return redirect("tournaments:list")

    messages.success(request, "Entry fee wallet se debit ho gayi. Admin verification ke baad registration confirm hogi.")
    return redirect("tournaments:list")


@login_required
@require_POST
def confirm_playing(request, registration_id):
    with transaction.atomic():
        registration = get_object_or_404(
            Registration.objects.select_for_update().select_related("tournament"),
            pk=registration_id,
            player=request.user,
        )
        if registration.status != Registration.Status.WAITING_READY or not registration.payment_verified:
            messages.error(request, "Is registration ki confirmation available nahi hai.")
            return redirect("tournaments:list")
        if not registration.room_details_sent or not registration.tournament.room_id:
            messages.error(request, "Room details abhi available nahi hain.")
            return redirect("tournaments:list")
        if not registration.ready_deadline or timezone.now() >= registration.ready_deadline:
            messages.error(request, "Confirmation ka 60-second time khatam ho gaya. Admin se contact karein.")
            return redirect("tournaments:player_room", registration_id=registration.pk)

        registration.status = Registration.Status.READY
        registration.ready_confirmed_at = timezone.now()
        registration.save(update_fields=["status", "ready_confirmed_at", "updated_at"])

    messages.success(request, "Participation confirm ho gayi!")
    return redirect("tournaments:player_room", registration_id=registration_id)


@login_required
@user_passes_test(lambda user: user.is_staff)
@require_POST
def send_room_details(request, tournament_id):
    room_id = request.POST.get("room_id", "").strip()
    room_password = request.POST.get("room_password", "").strip()
    if not room_id or not room_password:
        messages.error(request, "Room ID aur password dono bharo.")
        return redirect("tournaments:admin_room_page", tournament_id=tournament_id)

    with transaction.atomic():
        tournament = get_object_or_404(Tournament.objects.select_for_update(), pk=tournament_id)
        if tournament.status != Tournament.Status.UPCOMING:
            messages.error(request, "Sirf upcoming tournament ke liye room details set kar sakte ho.")
            return redirect("tournaments:admin_room_page", tournament_id=tournament_id)

        tournament.room_id = room_id
        tournament.room_password = room_password
        tournament.save(update_fields=["room_id", "room_password", "updated_at"])

        now = timezone.now()
        eligible = Registration.objects.select_for_update().filter(
            tournament=tournament,
            status=Registration.Status.CONFIRMED,
            payment_verified=True,
        )
        eligible.update(
            status=Registration.Status.WAITING_READY,
            room_details_sent=True,
            ready_deadline=now + timedelta(seconds=60),
        )

    messages.success(request, "Room details set ho gayi. Eligible paid players ko 60 seconds ke andar YES confirm karna hoga.")
    return redirect("tournaments:admin_room_page", tournament_id=tournament_id)


@login_required
@user_passes_test(lambda user: user.is_staff)
def admin_room_page(request, tournament_id):
    tournament = get_object_or_404(Tournament, pk=tournament_id)
    return render(request, "tournaments/admin_room.html", {"tournament": tournament})


@login_required
def player_room(request, registration_id):
    registration = get_object_or_404(
        Registration.objects.select_related("tournament"),
        pk=registration_id,
        player=request.user,
    )
    can_view_room = (
        registration.payment_verified
        and registration.room_details_sent
        and registration.status in (Registration.Status.WAITING_READY, Registration.Status.READY)
        and bool(registration.tournament.room_id)
        and (registration.status == Registration.Status.READY or (
            registration.ready_deadline and timezone.now() < registration.ready_deadline
        ))
    )
    return render(request, "tournaments/player_room.html", {
        "registration": registration,
        "tournament": registration.tournament,
        "can_view_room": can_view_room,
    })


@login_required
@user_passes_test(lambda user: user.is_staff)
def admin_tournament_dashboard(request, tournament_id):
    tournament = get_object_or_404(Tournament, pk=tournament_id)
    registrations = Registration.objects.filter(tournament=tournament).select_related("player").order_by("-registered_at")
    context = {
        "tournament": tournament,
        "registrations": registrations,
        "total_players": registrations.count(),
        "verified_payments": registrations.filter(payment_verified=True).count(),
        "waiting_players": registrations.filter(status=Registration.Status.WAITING_READY).count(),
        "ready_players": registrations.filter(status=Registration.Status.READY).count(),
        "not_playing_players": registrations.filter(status=Registration.Status.NOT_PLAYING).count(),
        "refunded_players": registrations.filter(refund_processed=True).count(),
    }
    return render(request, "tournaments/admin_dashboard.html", context)
