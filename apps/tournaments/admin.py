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
from .services import award_tournament_winner, cancel_tournament_and_refund, distribute_kill_prize_pool


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



@admin.action(description="Confirm & distribute approved BR kill-prize pool (internal wallet ledger)")
def distribute_br_kill_prizes(modeladmin, request, queryset):
    completed = 0
    skipped = 0
    for tournament in queryset:
        ok, message = distribute_kill_prize_pool(tournament.pk)
        if ok:
            completed += 1
            modeladmin.message_user(request, f"{tournament.title}: {message}", messages.SUCCESS)
        else:
            skipped += 1
            modeladmin.message_user(request, f"{tournament.title}: {message}", messages.WARNING)
    if skipped and not completed:
        modeladmin.message_user(request, "Koi prize batch distribute nahi hua.", messages.WARNING)


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


@admin.register(Tournament)
class TournamentAdmin(admin.ModelAdmin):
    form = TournamentAdminForm
    list_display = (
        "title", "mode", "vs_format", "entry_fee", "prize_pool",
        "max_players", "start_time", "status", "is_unlimited_br",
        "auto_reopen", "winner_prize_paid", "kill_prize_distributed", "kill_prize_pool",
    )
    list_filter = ("mode", "status", "start_time")
    search_fields = ("title", "description")
    ordering = ("start_time",)
    inlines = (RegistrationInline,)
    actions = (cancel_and_refund_tournaments, distribute_br_kill_prizes,)
    readonly_fields = ("series_root", "winner_prize_paid", "winner_prize_reference", "kill_prize_distributed", "kill_prize_pool", "kill_prize_reference")

    def get_readonly_fields(self, request, obj=None):
        fields = list(super().get_readonly_fields(request, obj))
        if obj and obj.winner_prize_paid:
            fields.append("winner_uid")
        return tuple(fields)

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if obj.winner_uid and not obj.winner_prize_paid:
            paid, message = award_tournament_winner(obj.pk)
            if paid:
                self.message_user(request, message, messages.SUCCESS)
            elif "Winner UID enter" not in message:
                self.message_user(request, message, messages.WARNING)

    fieldsets = (
        ("Tournament Details", {"fields": ("title", "description", "mode", "vs_format")}),
        ("Fees & Players", {"fields": ("entry_fee", "prize_pool", "max_players")}),
        ("Unlimited BR Series", {"fields": ("is_unlimited_br", "auto_start_at_capacity", "auto_reopen", "series_root")}),
        ("Schedule & Status", {"fields": ("start_time", "status")}),
        ("Room Details", {"fields": ("room_id", "room_password")}),
        ("First Place Winner", {"fields": ("winner_uid", "winner_prize_paid", "winner_prize_reference")}),
        ("Kill Prize Batch", {"fields": ("kill_prize_distributed", "kill_prize_pool", "kill_prize_reference")}),
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


@admin.register(Registration)
class RegistrationAdmin(admin.ModelAdmin):
    list_display = (
        "tournament", "player", "free_fire_uid", "entry_fee_paid",
        "payment_verified", "payment_reference", "status", "room_details_sent",
        "ready_deadline", "refund_processed", "registered_at",
    )
    list_filter = ("status", "payment_verified", "refund_processed")
    search_fields = ("free_fire_uid", "payment_reference", "player__username", "tournament__title")
    readonly_fields = (
        "registered_at", "updated_at", "ready_confirmed_at",
        "refund_processed_at",
    )
    actions = (verify_entry_payments,)


@admin.register(KillSubmission)
class KillSubmissionAdmin(admin.ModelAdmin):
    list_display = (
        "id", "player", "player_profile_id", "tournament", "registered_uid", "free_fire_uid",
        "player_upi_id", "payout_qr", "status", "ai_proposed_kills", "approved_kills", "approved_reward",
        "payout_reference", "submitted_at",
    )
    list_filter = ("status", "tournament", "submitted_at")
    search_fields = ("player__username", "tournament__title", "registered_uid", "free_fire_uid")
    readonly_fields = (
        "registration", "player", "tournament", "registered_uid", "free_fire_uid",
        "history_video", "history_image_one", "history_image_two",
        "ai_proposed_kills", "ai_confidence", "ai_uid_matches", "ai_review_notes",
        "approved_kills", "proposed_reward", "approved_reward",
        "status", "admin_notes", "payout_reference", "submitted_at", "reviewed_at",
    )

    @admin.display(description="Profile ID", ordering="player__id")
    def player_profile_id(self, obj):
        return obj.player_id

    @admin.display(description="Prize UPI ID", ordering="player__upi_id")
    def player_upi_id(self, obj):
        return obj.player.upi_id or "Missing — player must add it in Profile"

    @admin.display(description="UPI QR")
    def payout_qr(self, obj):
        upi_id = (obj.player.upi_id or "").strip()
        if not upi_id or "@" not in upi_id:
            return "UPI ID missing"
        if obj.player.upi_qr_code:
            try:
                return format_html(
                    '<a href="{}" target="_blank" rel="noopener"><img src="{}" width="72" height="72" alt="Uploaded player UPI QR" /></a>',
                    obj.player.upi_qr_code.url,
                    obj.player.upi_qr_code.url,
                )
            except (ValueError, OSError):
                pass
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
