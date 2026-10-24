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
from .models import KillSubmission, Registration, Tournament


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
    registered_uid = (request.user.free_fire_uid or "").strip()
    if not registered_uid or uid != registered_uid:
        form.add_error(
            "free_fire_uid",
            "Tournament UID aapke account ke registered Free Fire UID se match honi chahiye.",
        )
        return render(
            request,
            "tournaments/register.html",
            {"tournament": tournament, "form": form},
        )

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



@login_required
def my_registrations(request):
    registrations = Registration.objects.filter(player=request.user).select_related("tournament")
    return render(request, "tournaments/my_registrations.html", {"registrations": registrations})


@login_required
def kill_submission(request, registration_id):
    registration = get_object_or_404(
        Registration.objects.select_related("tournament", "player"),
        pk=registration_id,
        player=request.user,
    )
    if not registration.payment_verified or registration.status != Registration.Status.READY:
        messages.error(request, "Kill evidence submit karne ke liye verified registration zaroori hai.")
        return redirect("tournaments:my_registrations")

    if KillSubmission.objects.filter(registration=registration).exists():
        messages.info(request, "Is registration ki evidence submission pehle hi maujood hai.")
        return redirect("tournaments:my_registrations")

    if request.method == "POST":
        from .forms import KillSubmissionForm
        form = KillSubmissionForm(request.POST, request.FILES)
        if form.is_valid():
            submitted_uid = form.cleaned_data["free_fire_uid"]
            if submitted_uid != registration.free_fire_uid:
                form.add_error("free_fire_uid", "UID registration wali UID se match nahi karti.")
            else:
                submission = form.save(commit=False)
                submission.registration = registration
                submission.player = request.user
                submission.tournament = registration.tournament
                submission.registered_uid = registration.free_fire_uid
                submission.proposed_reward = Decimal("0.00")
                submission.save()
                messages.success(request, "Evidence submit ho gaya. Abhi AI result ya payout confirm nahi hua; admin review karega.")
                return redirect("tournaments:my_registrations")
    else:
        from .forms import KillSubmissionForm
        form = KillSubmissionForm(initial={"free_fire_uid": registration.free_fire_uid})

    return render(request, "tournaments/kill_submission.html", {
        "form": form,
        "registration": registration,
        "tournament": registration.tournament,
    })


@login_required
@user_passes_test(lambda user: user.is_staff)
def admin_kill_review(request):
    submissions = KillSubmission.objects.filter(
        status=KillSubmission.Status.PENDING
    ).select_related("player", "tournament", "registration")
    return render(request, "tournaments/admin_kill_review.html", {"submissions": submissions})


@login_required
@user_passes_test(lambda user: user.is_staff)
@require_POST
def review_kill_submission(request, submission_id):
    with transaction.atomic():
        submission = get_object_or_404(
            KillSubmission.objects.select_for_update().select_related("registration", "player", "tournament"),
            pk=submission_id,
        )
        if submission.status != KillSubmission.Status.PENDING:
            messages.error(request, "Yeh submission pehle hi review ho chuki hai.")
            return redirect("tournaments:admin_kill_review")

        decision = request.POST.get("decision", "").strip()
        notes = request.POST.get("admin_notes", "").strip()[:4000]
        if decision == "reject":
            submission.status = KillSubmission.Status.REJECTED
            submission.admin_notes = notes
            submission.reviewed_at = timezone.now()
            submission.save(update_fields=["status", "admin_notes", "reviewed_at"])
            messages.success(request, "Submission reject kar di gayi.")
            return redirect("tournaments:admin_kill_review")

        if decision != "approve":
            messages.error(request, "Valid review action select karo.")
            return redirect("tournaments:admin_kill_review")

        try:
            approved_kills = int(request.POST.get("approved_kills", ""))
        except (TypeError, ValueError):
            messages.error(request, "Approved kills ek valid whole number hona chahiye.")
            return redirect("tournaments:admin_kill_review")
        if approved_kills < 0 or approved_kills > 99:
            messages.error(request, "Approved kills 0 se 99 ke beech hone chahiye.")
            return redirect("tournaments:admin_kill_review")
        if submission.free_fire_uid != submission.registered_uid or submission.registered_uid != submission.registration.free_fire_uid:
            messages.error(request, "UID mismatch hai; payout roka gaya.")
            return redirect("tournaments:admin_kill_review")

        reward = Decimal(approved_kills) * Decimal("5.00")
        submission.approved_kills = approved_kills
        submission.approved_reward = reward
        submission.admin_notes = notes
        submission.reviewed_at = timezone.now()

        if reward > 0:
            admin_wallet, _ = AdminWallet.objects.get_or_create(name="Main Admin Wallet")
            admin_wallet = AdminWallet.objects.select_for_update().get(pk=admin_wallet.pk)
            if admin_wallet.balance < reward:
                messages.error(request, f"Admin wallet mein balance kam hai. ₹{reward} payout approve nahi hua.")
                return redirect("tournaments:admin_kill_review")

            player_wallet, _ = Wallet.objects.get_or_create(user=submission.player)
            player_wallet = Wallet.objects.select_for_update().get(pk=player_wallet.pk)
            reference = f"KILL-PRIZE-{submission.pk}"
            if WalletTransaction.objects.filter(reference=reference).exists():
                messages.error(request, "Is submission ka payout reference pehle se maujood hai.")
                return redirect("tournaments:admin_kill_review")

            admin_wallet.balance -= reward
            admin_wallet.save(update_fields=["balance", "updated_at"])
            player_wallet.balance += reward
            player_wallet.save(update_fields=["balance", "updated_at"])
            AdminWalletTransaction.objects.create(
                admin_wallet=admin_wallet,
                transaction_type=AdminWalletTransaction.TransactionType.PRIZE,
                amount=reward,
                status=AdminWalletTransaction.Status.COMPLETED,
                reference=reference,
                description=f"Admin-approved kill reward for submission {submission.pk}",
            )
            WalletTransaction.objects.create(
                wallet=player_wallet,
                transaction_type=WalletTransaction.TransactionType.PRIZE,
                amount=reward,
                status=WalletTransaction.Status.COMPLETED,
                reference=reference,
                description=f"Admin-approved reward: {approved_kills} kills at ₹5 each",
            )
            submission.payout_reference = reference

        submission.status = KillSubmission.Status.APPROVED
        submission.save(update_fields=[
            "approved_kills", "approved_reward", "admin_notes", "reviewed_at",
            "payout_reference", "status",
        ])

    messages.success(request, f"Admin review complete. Approved reward: ₹{reward}.")
    return redirect("tournaments:admin_kill_review")


def leaderboard(request, tournament_id):
    tournament = get_object_or_404(Tournament, pk=tournament_id)
    submissions = KillSubmission.objects.filter(
        tournament=tournament,
        status=KillSubmission.Status.APPROVED,
    ).select_related("player", "registration").order_by("-approved_kills", "reviewed_at")
    return render(request, "tournaments/leaderboard.html", {
        "tournament": tournament,
        "submissions": submissions,
    })
