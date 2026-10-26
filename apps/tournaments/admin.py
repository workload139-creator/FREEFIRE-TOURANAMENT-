from django import forms
from django.contrib import admin, messages
from django.db import transaction
from django.utils.html import format_html

from apps.accounts.models import (
    AdminWallet,
    AdminWalletTransaction,
    WalletTransaction,
)
from .models import KillSubmission, Registration, Tournament
from .services import cancel_tournament_and_refund


class TournamentAdminForm(forms.ModelForm):
    """Make tournament creation easier and default new tournaments to public status."""

    start_time = forms.DateTimeField(
        input_formats=[
            "%Y-%m-%dT%H:%M",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
        ],
        widget=forms.DateTimeInput(
            format="%Y-%m-%dT%H:%M",
            attrs={"type": "datetime-local"},
        ),
    )

    class Meta:
        model = Tournament
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.pk:
            self.initial["status"] = Tournament.Status.UPCOMING
        self.fields["status"].help_text = (
            "Website par dikhane aur registration kholne ke liye "
            "'Upcoming' select karein. Draft tournaments public list mein nahi dikhte."
        )
        self.fields["auto_reopen"].help_text = (
            "Unlimited BR ke root tournament par ON/OFF karein: ON se 49-player round ke baad next round khulega."
        )

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("is_unlimited_br"):
            if cleaned.get("mode") != Tournament.Mode.BR:
                self.add_error("mode", "Unlimited series sirf Battle Royale (BR) mode mein ho sakti hai.")
            if cleaned.get("max_players") != 49:
                self.add_error("max_players", "Unlimited BR round mein exactly 49 players hone chahiye.")
            cleaned["auto_start_at_capacity"] = True
        elif cleaned.get("auto_reopen"):
            self.add_error("auto_reopen", "Auto reopen sirf Unlimited BR series ke liye hai.")
        return cleaned


class RegistrationInline(admin.TabularInline):
    model = Registration
    extra = 0
    show_change_link = True
    readonly_fields = (
        "registered_at", "updated_at", "ready_confirmed_at",
        "refund_processed_at",
    )



@admin.action(description="Cancel tournament and refund registered players")
def cancel_and_refund_tournaments(modeladmin, request, queryset):
    cancelled = 0
    refunded = 0
    for tournament in queryset:
        count, message = cancel_tournament_and_refund(tournament.pk)
        if "already cancelled" not in message.lower():
            cancelled += 1
        refunded += count
    modeladmin.message_user(
        request,
        f"{cancelled} tournament(s) cancelled; {refunded} player refund(s) recorded.",
        messages.SUCCESS,
    )


@admin.action(description="Mark winner prize PAID after manual UPI transfer and real UTR entry")
def mark_winner_prizes_paid(modeladmin, request, queryset):
    paid = 0
    skipped = 0
    for selected in queryset:
        with transaction.atomic():
            tournament = Tournament.objects.select_for_update().get(pk=selected.pk)
            if tournament.winner_prize_paid or not tournament.winner_uid or tournament.prize_pool <= 0:
                skipped += 1
                continue
            utr = (tournament.winner_prize_reference or "").strip()
            if len(utr) < 6 or utr.startswith("WIN-PRIZE-"):
                skipped += 1
                continue
            if Tournament.objects.filter(winner_prize_reference__iexact=utr).exclude(pk=tournament.pk).exists():
                skipped += 1
                continue
            eligible = Registration.objects.select_for_update().filter(
                tournament=tournament,
                free_fire_uid=str(tournament.winner_uid).strip(),
                payment_verified=True,
                refund_processed=False,
                status__in=[Registration.Status.CONFIRMED, Registration.Status.WAITING_READY, Registration.Status.READY],
            ).select_related("player")
            if eligible.count() != 1:
                skipped += 1
                continue
            winner = eligible.first()
            if not (winner.player.upi_id or "").strip() and not winner.player.upi_qr_code:
                skipped += 1
                continue
            admin_wallet, _ = AdminWallet.objects.get_or_create(name="Main Admin Wallet")
            admin_wallet = AdminWallet.objects.select_for_update().get(pk=admin_wallet.pk)
            prize = tournament.prize_pool
            if admin_wallet.balance < prize:
                skipped += 1
                continue
            ledger_reference = f"ADMIN-WIN-UPI-{tournament.pk}"
            if AdminWalletTransaction.objects.filter(reference=ledger_reference).exists():
                skipped += 1
                continue
            # Real transfer must already be sent externally to the winner's saved UPI ID/QR.
            admin_wallet.balance -= prize
            admin_wallet.save(update_fields=["balance", "updated_at"])
            AdminWalletTransaction.objects.create(
                admin_wallet=admin_wallet,
                transaction_type=AdminWalletTransaction.TransactionType.PRIZE,
                amount=prize,
                status=AdminWalletTransaction.Status.COMPLETED,
                reference=ledger_reference,
                description=f"Manual UPI winner prize for tournament {tournament.pk}; external UTR {utr}; player profile {winner.player_id}.",
            )
            tournament.winner_prize_paid = True
            tournament.save(update_fields=["winner_prize_paid", "updated_at"])
            paid += 1
    if paid:
        modeladmin.message_user(request, f"{paid} winner prize(s) marked paid after manual UPI transfer.", messages.SUCCESS)
    if skipped:
        modeladmin.message_user(request, f"{skipped} winner prize(s) skipped: check winner UID, saved UPI/QR, real unique UTR and Admin Wallet ledger balance.", messages.WARNING)


@admin.register(Tournament)
class TournamentAdmin(admin.ModelAdmin):
    form = TournamentAdminForm
    list_display = (
        "title", "mode", "vs_format", "entry_fee", "prize_pool",
        "max_players", "start_time", "status", "is_unlimited_br",
        "auto_reopen", "winner_prize_paid",
    )
    list_filter = ("mode", "status", "start_time")
    search_fields = ("title", "description")
    ordering = ("start_time",)
    inlines = (RegistrationInline,)
    actions = (cancel_and_refund_tournaments, mark_winner_prizes_paid,)
    readonly_fields = ("series_root", "winner_prize_paid", "kill_prize_distributed", "kill_prize_pool", "kill_prize_reference", "winner_payout_destination", "winner_payout_qr")

    def get_readonly_fields(self, request, obj=None):
        fields = list(super().get_readonly_fields(request, obj))
        if obj and obj.winner_prize_paid:
            fields.append("winner_uid")
        return tuple(fields)

    @admin.display(description="Winner UPI destination")
    def winner_payout_destination(self, obj):
        if not obj or not obj.pk or not obj.winner_uid:
            return "Set Winner UID first; then reload to view payout details."
        registrations = Registration.objects.filter(
            tournament=obj, free_fire_uid=str(obj.winner_uid).strip(), payment_verified=True
        ).select_related("player")
        if registrations.count() != 1:
            return "No unique verified registration matches this Winner UID."
        player = registrations.first().player
        if (player.upi_id or "").strip():
            return f"Profile #{player.pk} · {player.username} · UPI ID saved"
        if player.upi_qr_code:
            return f"Profile #{player.pk} · {player.username} · use uploaded QR below"
        return f"Profile #{player.pk} · {player.username} · no UPI ID/QR saved"

    @admin.display(description="Winner UPI QR")
    def winner_payout_qr(self, obj):
        if not obj or not obj.pk or not obj.winner_uid:
            return "Set Winner UID first."
        registration = Registration.objects.filter(
            tournament=obj, free_fire_uid=str(obj.winner_uid).strip(), payment_verified=True
        ).select_related("player").first()
        if not registration:
            return "No verified registration matches this Winner UID."
        player = registration.player
        if player.upi_qr_code:
            try:
                return format_html(
                    '<a href="{}" target="_blank" rel="noopener"><img src="{}" width="120" height="120" alt="Winner uploaded UPI QR" /></a>',
                    player.upi_qr_code.url, player.upi_qr_code.url,
                )
            except (ValueError, OSError):
                pass
        if not (player.upi_id or "").strip() or "@" not in player.upi_id:
            return "Winner has not supplied a usable UPI ID or QR."
        import base64
        import io
        from urllib.parse import urlencode
        import qrcode
        uri = "upi://pay?" + urlencode({
            "pa": player.upi_id.strip(),
            "pn": player.username[:50],
            "am": f"{obj.prize_pool:.2f}",
            "cu": "INR",
            "tn": f"FF winner prize tournament {obj.pk}",
        })
        image = qrcode.make(uri)
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
        return format_html('<img src="data:image/png;base64,{}" width="120" height="120" alt="Winner UPI payment QR" />', encoded)

    fieldsets = (
        ("Tournament Details", {"fields": ("title", "description", "mode", "vs_format")}),
        ("Fees & Players", {"fields": ("entry_fee", "prize_pool", "max_players")}),
        ("Unlimited BR Series", {"fields": ("is_unlimited_br", "auto_start_at_capacity", "auto_reopen", "series_root")}),
        ("Schedule & Status", {"fields": ("start_time", "status")}),
        ("Room Details", {"fields": ("room_id", "room_password")}),
        ("First Place Winner", {"fields": ("winner_uid", "winner_payout_destination", "winner_payout_qr", "winner_prize_reference", "winner_prize_paid")}),
    )


@admin.action(description="Verify UTR against actual UPI/bank receipt and confirm entry")
def verify_entry_payments(modeladmin, request, queryset):
    verified_count = 0
    skipped_count = 0

    with transaction.atomic():
        for registration in queryset.select_related("tournament", "player").select_for_update():
            if registration.payment_verified or registration.status != Registration.Status.PENDING_PAYMENT:
                skipped_count += 1
                continue

            fee = registration.entry_fee_paid
            utr = (registration.payment_reference or "").strip()
            if fee > 0:
                # Admin must check the actual receiving UPI/bank statement first.
                if len(utr) < 6:
                    skipped_count += 1
                    continue
                duplicate_utr = Registration.objects.filter(
                    payment_reference__iexact=utr
                ).exclude(pk=registration.pk).exists()
                if duplicate_utr:
                    skipped_count += 1
                    continue

                admin_reference = f"ADMIN-ENTRY-{registration.pk}"
                if AdminWalletTransaction.objects.filter(reference=admin_reference).exists():
                    skipped_count += 1
                    continue

                admin_wallet, _ = AdminWallet.objects.get_or_create(name="Main Admin Wallet")
                admin_wallet = AdminWallet.objects.select_for_update().get(pk=admin_wallet.pk)
                admin_wallet.balance += fee
                admin_wallet.save(update_fields=["balance", "updated_at"])
                AdminWalletTransaction.objects.create(
                    admin_wallet=admin_wallet,
                    transaction_type=AdminWalletTransaction.TransactionType.ENTRY_FEE,
                    amount=fee,
                    status=AdminWalletTransaction.Status.COMPLETED,
                    reference=admin_reference,
                    description=f"Manually verified UTR {utr} for tournament {registration.tournament_id}; admin checked actual bank/UPI receipt.",
                )

            registration.payment_verified = True
            registration.status = Registration.Status.CONFIRMED
            registration.save(update_fields=["payment_verified", "status", "updated_at"])
            verified_count += 1

    if verified_count:
        modeladmin.message_user(
            request,
            f"{verified_count} registration(s) confirmed after admin verification. Actual UPI/bank statement check required before this action.",
            messages.SUCCESS,
        )
    if skipped_count:
        modeladmin.message_user(
            request,
            f"{skipped_count} registration(s) skipped: already verified, missing/duplicate UTR, or transaction already recorded.",
            messages.WARNING,
        )


@admin.action(description="Mark UPI refunds paid after sending actual refund and entering its UTR")
def mark_manual_upi_refunds_paid(modeladmin, request, queryset):
    completed = 0
    skipped = 0
    for selected in queryset:
        with transaction.atomic():
            registration = Registration.objects.select_for_update().select_related("tournament", "player").get(pk=selected.pk)
            utr = (registration.refund_reference or "").strip()
            if (
                not registration.payment_reference
                or not registration.payment_verified
                or registration.status not in (Registration.Status.CANCELLED, Registration.Status.NOT_PLAYING)
                or registration.refund_processed
                or len(utr) < 6
            ):
                skipped += 1
                continue
            if Registration.objects.filter(refund_reference__iexact=utr).exclude(pk=registration.pk).exists():
                skipped += 1
                continue
            ledger_reference = f"ADMIN-UPI-REFUND-{registration.pk}"
            if AdminWalletTransaction.objects.filter(reference=ledger_reference).exists():
                skipped += 1
                continue
            admin_wallet, _ = AdminWallet.objects.get_or_create(name="Main Admin Wallet")
            admin_wallet = AdminWallet.objects.select_for_update().get(pk=admin_wallet.pk)
            amount = registration.entry_fee_paid
            if admin_wallet.balance < amount:
                skipped += 1
                continue
            # This action only records a refund already sent outside the website through UPI.
            admin_wallet.balance -= amount
            admin_wallet.save(update_fields=["balance", "updated_at"])
            AdminWalletTransaction.objects.create(
                admin_wallet=admin_wallet,
                transaction_type=AdminWalletTransaction.TransactionType.REFUND,
                amount=amount,
                status=AdminWalletTransaction.Status.COMPLETED,
                reference=ledger_reference,
                description=f"Manual UPI refund UTR {utr} for cancelled/not-playing registration {registration.pk}",
            )
            registration.status = Registration.Status.REFUNDED
            registration.refund_processed = True
            registration.refund_processed_at = timezone.now()
            registration.save(update_fields=["status", "refund_processed", "refund_processed_at", "updated_at"])
            completed += 1
    if completed:
        modeladmin.message_user(request, f"{completed} manual UPI refund(s) recorded after transfer.", messages.SUCCESS)
    if skipped:
        modeladmin.message_user(request, f"{skipped} refund(s) skipped: verify payment/status, enter unique real UTR, and check Admin Wallet ledger balance.", messages.WARNING)


@admin.register(Registration)
class RegistrationAdmin(admin.ModelAdmin):
    list_display = (
        "tournament", "player", "free_fire_uid", "entry_fee_paid",
        "payment_verified", "payment_reference", "status", "room_details_sent",
        "ready_deadline", "refund_processed", "refund_reference", "registered_at",
    )
    list_filter = ("status", "payment_verified", "refund_processed")
    search_fields = ("free_fire_uid", "payment_reference", "player__username", "tournament__title")
    readonly_fields = (
        "registered_at", "updated_at", "ready_confirmed_at",
        "refund_processed_at",
    )
    actions = (verify_entry_payments, mark_manual_upi_refunds_paid,)


@admin.action(description="Mark selected BR prizes PAID after completing manual UPI transfer")
def mark_selected_prizes_paid(modeladmin, request, queryset):
    paid = 0
    skipped = 0
    for selected in queryset:
        with transaction.atomic():
            item = KillSubmission.objects.select_for_update().select_related("player", "tournament").get(pk=selected.pk)
            reference = (item.payout_reference or "").strip()
            if (
                item.status != KillSubmission.Status.APPROVED
                or item.tournament.mode != Tournament.Mode.BR
                or item.approved_reward <= 0
                or item.payout_status == KillSubmission.PayoutStatus.PAID
                or len(reference) < 6
                or reference.startswith("KILL-PRIZE-")
            ):
                skipped += 1
                continue
            duplicate = KillSubmission.objects.filter(payout_reference__iexact=reference).exclude(pk=item.pk).exists()
            if duplicate:
                skipped += 1
                continue
            ledger_reference = f"ADMIN-KILL-UPI-{item.pk}"
            if AdminWalletTransaction.objects.filter(reference=ledger_reference).exists():
                skipped += 1
                continue
            admin_wallet, _ = AdminWallet.objects.get_or_create(name="Main Admin Wallet")
            admin_wallet = AdminWallet.objects.select_for_update().get(pk=admin_wallet.pk)
            if admin_wallet.balance < item.approved_reward:
                skipped += 1
                continue
            # Admin must first complete the transfer in their own UPI app and enter its real UTR.
            admin_wallet.balance -= item.approved_reward
            admin_wallet.save(update_fields=["balance", "updated_at"])
            AdminWalletTransaction.objects.create(
                admin_wallet=admin_wallet,
                transaction_type=AdminWalletTransaction.TransactionType.PRIZE,
                amount=item.approved_reward,
                status=AdminWalletTransaction.Status.COMPLETED,
                reference=ledger_reference,
                description=f"Manual UPI BR kill reward; external UTR {reference}; profile {item.player_id}; tournament {item.tournament_id}.",
            )
            item.payout_status = KillSubmission.PayoutStatus.PAID
            item.payout_paid_at = timezone.now()
            item.save(update_fields=["payout_status", "payout_paid_at"])
            paid += 1
    if paid:
        modeladmin.message_user(request, f"{paid} prize(s) marked PAID using manually entered UPI reference(s).", messages.SUCCESS)
    if skipped:
        modeladmin.message_user(request, f"{skipped} item(s) skipped: no approved BR reward, missing/duplicate real UTR, or already paid.", messages.WARNING)


@admin.register(KillSubmission)
class KillSubmissionAdmin(admin.ModelAdmin):
    list_display = (
        "id", "player", "player_profile_id", "tournament", "registered_uid", "free_fire_uid",
        "player_upi_id", "payout_qr", "status", "ai_proposed_kills", "approved_kills", "approved_reward",
        "payout_reference", "payout_status", "payout_paid_at", "submitted_at",
    )
    list_filter = ("status", "tournament", "submitted_at")
    search_fields = ("player__username", "tournament__title", "registered_uid", "free_fire_uid")
    readonly_fields = (
        "registration", "player", "tournament", "registered_uid", "free_fire_uid",
        "history_video", "history_image_one", "history_image_two",
        "ai_proposed_kills", "ai_confidence", "ai_uid_matches", "ai_review_notes",
        "approved_kills", "proposed_reward", "approved_reward",
        "status", "admin_notes", "payout_status", "payout_paid_at", "submitted_at", "reviewed_at",
    )

    @admin.display(description="Profile ID", ordering="player__id")
    def player_profile_id(self, obj):
        return obj.player_id

    @admin.display(description="Prize UPI ID", ordering="player__upi_id")
    def player_upi_id(self, obj):
        if (obj.player.upi_id or "").strip():
            return obj.player.upi_id
        if obj.player.upi_qr_code:
            return "UPI ID not entered — use uploaded QR"
        return "Missing — player must add UPI ID or QR in Profile"

    @admin.display(description="UPI QR")
    def payout_qr(self, obj):
        upi_id = (obj.player.upi_id or "").strip()
        if obj.player.upi_qr_code:
            try:
                return format_html(
                    '<a href="{}" target="_blank" rel="noopener"><img src="{}" width="96" height="96" alt="Player uploaded UPI QR for manual prize payout" /></a>',
                    obj.player.upi_qr_code.url,
                    obj.player.upi_qr_code.url,
                )
            except (ValueError, OSError):
                pass
        if not upi_id or "@" not in upi_id:
            return "Player has not provided a usable UPI ID or QR"
        import base64
        import io
        from urllib.parse import urlencode
        import qrcode

        uri = "upi://pay?" + urlencode({
            "pa": upi_id,
            "pn": obj.player.username[:50],
            "cu": "INR",
            "tn": f"FF tournament prize profile {obj.player_id}",
        })
        image = qrcode.make(uri)
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
        return format_html(
            '<img src="data:image/png;base64,{}" width="72" height="72" alt="Player UPI QR" />',
            encoded,
        )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    actions = (mark_selected_prizes_paid,)
