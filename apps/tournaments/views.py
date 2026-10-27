from datetime import timedelta
import os
from decimal import Decimal
import base64
import io

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from urllib.parse import quote, urlencode
from django.views.decorators.http import require_POST

from apps.accounts.models import Wallet, WalletTransaction, AdminWallet, AdminWalletTransaction
from .forms import KillSubmissionForm, RegistrationForm
from .ai_review import AIReviewError, analyze_kill_evidence
from .registration_services import RegistrationError, create_pending_registration
from .models import KillSubmission, Registration, Tournament
from .services import process_expired_ready_registrations, mark_not_playing_and_refund

import qrcode


def tournament_list(request):
    process_expired_ready_registrations()
    tournaments = Tournament.objects.filter(
        status__in=[Tournament.Status.UPCOMING, Tournament.Status.LIVE, Tournament.Status.COMPLETED]
    ).order_by("start_time")
    return render(
        request,
        "tournaments/list.html",
        {
            "tournaments": tournaments,
            "br_tournaments": tournaments.filter(mode=Tournament.Mode.BR),
            "vs_tournaments": tournaments.filter(mode=Tournament.Mode.VS),
        },
    )


def tournament_detail(request, tournament_id):
    tournament = get_object_or_404(Tournament, pk=tournament_id)
    return render(request, "tournaments/tournament_detail.html", {"tournament": tournament})


def build_entry_payment_uri(tournament):
    """Build a UPI deep link only when the configured receiving UPI ID exists."""
    if tournament.entry_fee <= Decimal("0.00"):
        return ""
    upi_id = os.getenv("FF_ARENA_UPI_ID", "").strip()
    if not upi_id or "@" not in upi_id or any(char.isspace() for char in upi_id):
        return ""
    query = urlencode({"pa": upi_id, "pn": os.getenv("FF_ARENA_UPI_NAME", "FF Arena").strip() or "FF Arena", "am": f"{tournament.entry_fee:.2f}", "cu": "INR", "tn": f"FFArena-{tournament.pk}"})
    return f"upi://pay?{query}"


def build_entry_qr_url(tournament):
    """Create QR locally, avoiding external QR API and cross-origin download failures."""
    uri = build_entry_payment_uri(tournament)
    if not uri:
        return ""
    image = qrcode.make(uri)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")

@login_required
def tournament_register(request, tournament_id):
    process_expired_ready_registrations()
    tournament = get_object_or_404(Tournament, pk=tournament_id)
    if tournament.gender_category == Tournament.GenderCategory.BOYS and request.user.gender != "boy":
        messages.error(request, "Yeh Boys Only tournament hai. Profile mein Boy category select karne wale players hi join kar sakte hain.")
        return redirect("tournaments:detail", tournament_id=tournament.pk)
    if tournament.gender_category == Tournament.GenderCategory.GIRLS and request.user.gender != "girl":
        messages.error(request, "Yeh Girls Only tournament hai. Profile mein Girl category select karne wale players hi join kar sakte hain.")
        return redirect("tournaments:detail", tournament_id=tournament.pk)
    if not (request.user.upi_id or "").strip() and not request.user.upi_qr_code:
        messages.info(request, "Tournament join karne se pehle prize receive karne ke liye apni UPI ID ya QR profile mein add karein.")
        target = reverse("accounts:profile_edit") + "?next=" + quote(request.path, safe="")
        return redirect(target)

    if request.method == "GET":
        time_closed = tournament.start_time <= timezone.now() and not tournament.is_unlimited_br
        if tournament.status != Tournament.Status.UPCOMING or time_closed or tournament.is_full:
            messages.error(request, "Yeh tournament abhi registration ke liye available nahi hai.")
            return redirect("tournaments:list")
        if Registration.objects.filter(tournament=tournament, player=request.user).exists():
            messages.info(request, "Aap is tournament mein pehle se registered hain.")
            return redirect("tournaments:detail", tournament_id=tournament.pk)
        return render(request, "tournaments/register.html", {"tournament": tournament, "form": RegistrationForm(user=request.user, tournament=tournament), "upi_payment_uri": build_entry_payment_uri(tournament), "qr_image_url": build_entry_qr_url(tournament)})

    if tournament.entry_fee > Decimal("0.00") and not build_entry_payment_uri(tournament):
        messages.error(request, "Tournament payment abhi configured nahi hai. Admin ko Render Environment mein valid FF_ARENA_UPI_ID set karna hoga.")
        return redirect("tournaments:detail", tournament_id=tournament.pk)

    if request.method != "POST":
        return redirect("tournaments:list")

    form = RegistrationForm(request.POST, request.FILES, user=request.user, tournament=tournament)
    if not form.is_valid():
        return render(request, "tournaments/register.html", {"tournament": tournament, "form": form, "upi_payment_uri": build_entry_payment_uri(tournament), "qr_image_url": build_entry_qr_url(tournament)})

    try:
        registration = create_pending_registration(
            tournament_id=tournament_id,
            player=request.user,
            free_fire_uid=form.cleaned_data["free_fire_uid"],
            payment_reference=form.cleaned_data.get("payment_reference", ""),
        )
    except RegistrationError as exc:
        form.add_error(None, str(exc))
        return render(
            request,
            "tournaments/register.html",
            {"tournament": tournament, "form": form, "upi_payment_uri": build_entry_payment_uri(tournament), "qr_image_url": build_entry_qr_url(tournament)},
        )
    except IntegrityError:
        form.add_error(None, "Registration nahi ho saki; aap pehle se registered ho sakte hain.")
        return render(
            request,
            "tournaments/register.html",
            {"tournament": tournament, "form": form, "upi_payment_uri": build_entry_payment_uri(tournament), "qr_image_url": build_entry_qr_url(tournament)},
        )

    if form.cleaned_data.get("verification_photo"):
        registration.verification_photo = form.cleaned_data["verification_photo"]
        registration.save(update_fields=["verification_photo"])

    if tournament.entry_fee > Decimal("0.00"):
        messages.info(request, "Payment UTR submit ho gaya. Registration tabhi confirm hogi jab admin aapki payment apne UPI/bank statement se verify karega.")
    else:
        messages.success(request, "Free tournament registration confirm ho gayi.")
    return redirect("tournaments:my_registrations")


@login_required
@require_POST
def confirm_playing(request, registration_id):
    process_expired_ready_registrations()
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
@require_POST
def decline_playing(request, registration_id):
    process_expired_ready_registrations()
    registration = get_object_or_404(Registration, pk=registration_id, player=request.user)
    if registration.status != Registration.Status.WAITING_READY:
        messages.error(request, "Is registration ke liye NO option ab available nahi hai.")
        return redirect("tournaments:my_registrations")
    registration.ready_deadline = timezone.now()
    registration.save(update_fields=["ready_deadline", "updated_at"])
    changed, detail = mark_not_playing_and_refund(registration.pk)
    if changed:
        messages.warning(request, "Aap NOT PLAYING mark ho gaye. Direct UPI refund ke liye admin ko actual transfer process karna hoga.")
    else:
        messages.error(request, "Status update nahi ho saka: " + detail)
    return redirect("tournaments:my_registrations")


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
        allowed_statuses = [Tournament.Status.UPCOMING]
        if tournament.is_unlimited_br:
            allowed_statuses.append(Tournament.Status.LIVE)
        if tournament.status not in allowed_statuses:
            messages.error(request, "Is tournament status mein room details set nahi kar sakte.")
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
    process_expired_ready_registrations()
    registration = get_object_or_404(
        Registration.objects.select_related("tournament"),
        pk=registration_id,
        player=request.user,
    )
    can_view_room = (
        registration.payment_verified
        and registration.room_details_sent
        and registration.status == Registration.Status.READY
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
    process_expired_ready_registrations()
    tournament = get_object_or_404(Tournament, pk=tournament_id)
    registrations = Registration.objects.filter(tournament=tournament).select_related("player").order_by("-registered_at")
    kill_submissions = KillSubmission.objects.filter(
        tournament=tournament
    ).select_related("player", "registration").order_by("-submitted_at")
    context = {
        "tournament": tournament,
        "registrations": registrations,
        "kill_submissions": kill_submissions,
        "pending_payments": registrations.filter(payment_verified=False, entry_fee_paid__gt=0),
        "refund_queue": registrations.filter(
            payment_verified=True,
            entry_fee_paid__gt=0,
            refund_processed=False,
            status__in=[Registration.Status.CANCELLED, Registration.Status.NOT_PLAYING],
        ).select_related("player"),
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
    process_expired_ready_registrations()
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
                try:
                    ai_result = analyze_kill_evidence(submission)
                    submission.ai_proposed_kills = ai_result["proposed_kills"]
                    submission.ai_confidence = ai_result["confidence"][:10]
                    submission.ai_uid_matches = ai_result["uid_matches"]
                    submission.ai_review_notes = ai_result["reason"]
                    if (
                        ai_result["proposed_kills"] is not None
                        and ai_result["uid_matches"] is True
                        and submitted_uid == registration.free_fire_uid
                        and registration.tournament.mode == Tournament.Mode.BR
                    ):
                        proposed_kills = int(ai_result["proposed_kills"])
                        if proposed_kills >= settings.MINIMUM_VERIFIED_KILLS:
                            submission.proposed_reward = Decimal(proposed_kills) * Decimal(str(settings.REWARD_PER_APPROVED_KILL))
                    submission.save(update_fields=[
                        "ai_proposed_kills", "ai_confidence", "ai_uid_matches",
                        "ai_review_notes", "proposed_reward",
                    ])
                    messages.success(
                        request,
                        "Evidence submit ho gaya. AI ka result sirf proposal hai; admin final review karega.",
                    )
                except AIReviewError as exc:
                    messages.warning(
                        request,
                        f"Evidence save ho gaya, lekin AI review available nahi tha: {exc} Admin manually review karega.",
                    )
                return redirect("tournaments:my_registrations")
    else:
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
    tournament_id = request.GET.get("tournament")
    if tournament_id and str(tournament_id).isdigit():
        submissions = submissions.filter(tournament_id=int(tournament_id))
    return render(request, "tournaments/admin_kill_review.html", {
        "submissions": submissions,
        "selected_tournament_id": tournament_id or "",
    })


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
        if (
            submission.free_fire_uid != submission.registered_uid
            or submission.registered_uid != submission.registration.free_fire_uid
        ):
            messages.error(request, "UID mismatch hai; payout eligibility roki gayi.")
            return redirect("tournaments:admin_kill_review")

        submission.approved_kills = approved_kills
        if submission.tournament.mode == Tournament.Mode.BR and approved_kills >= settings.MINIMUM_VERIFIED_KILLS:
            submission.proposed_reward = Decimal(approved_kills) * Decimal(str(settings.REWARD_PER_APPROVED_KILL))
        else:
            submission.proposed_reward = Decimal("0.00")
        submission.approved_reward = submission.proposed_reward
        submission.admin_notes = notes
        submission.reviewed_at = timezone.now()
        submission.status = KillSubmission.Status.APPROVED
        submission.save(update_fields=[
            "approved_kills", "proposed_reward", "approved_reward",
            "admin_notes", "reviewed_at", "status",
        ])

    messages.success(
        request,
        f"Kill evidence review complete: {approved_kills} kills approved. Eligible BR reward ₹{submission.approved_reward} calculate hua. Ab admin ko player ki saved UPI ID/QR par manually payout karke real UTR admin panel mein enter karna hoga; review approval se payment nahi hota.",
    )
    return redirect("tournaments:admin_kill_review")


def results(request):
    completed_tournaments = Tournament.objects.filter(
        status=Tournament.Status.COMPLETED
    ).order_by("-start_time")
    return render(
        request,
        "tournaments/results.html",
        {"completed_tournaments": completed_tournaments},
    )


def leaderboard(request, tournament_id):
    """Show every paid, verified entrant; kills/rewards appear only after admin approval."""
    tournament = get_object_or_404(Tournament, pk=tournament_id)
    eligible_statuses = [
        Registration.Status.CONFIRMED,
        Registration.Status.WAITING_READY,
        Registration.Status.READY,
    ]
    registrations = list(
        Registration.objects.filter(
            tournament=tournament,
            payment_verified=True,
            refund_processed=False,
            status__in=eligible_statuses,
        ).select_related("player").order_by("registered_at")
    )
    approved_submissions = {
        item.registration_id: item
        for item in KillSubmission.objects.filter(
            tournament=tournament,
            status=KillSubmission.Status.APPROVED,
        ).select_related("player", "registration")
    }
    rows = []
    for registration in registrations:
        submission = approved_submissions.get(registration.pk)
        rows.append({
            "registration": registration,
            "submission": submission,
            "kills": submission.approved_kills if submission and submission.approved_kills is not None else -1,
            "is_winner": bool(tournament.winner_uid and registration.free_fire_uid == tournament.winner_uid),
        })

    # Admin-confirmed winner stays first; remaining verified entrants sort by approved kills,
    # with players awaiting evidence/review still visible and shown as pending.
    rows.sort(key=lambda row: (
        not row["is_winner"],
        -row["kills"],
        row["registration"].registered_at,
    ))
    return render(request, "tournaments/leaderboard.html", {
        "tournament": tournament,
        "leaderboard_rows": rows,
        "verified_player_count": len(rows),
    })
