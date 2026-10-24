from django import forms
from django.contrib import admin, messages
from django.db import transaction

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


@admin.register(Tournament)
class TournamentAdmin(admin.ModelAdmin):
    form = TournamentAdminForm
    list_display = (
        "title", "mode", "vs_format", "entry_fee", "prize_pool",
        "max_players", "start_time", "status",
    )
    list_filter = ("mode", "status", "start_time")
    search_fields = ("title", "description")
    ordering = ("start_time",)
    inlines = (RegistrationInline,)
    actions = (cancel_and_refund_tournaments,)
    fieldsets = (
        ("Tournament Details", {"fields": ("title", "description", "mode", "vs_format")}),
        ("Fees & Players", {"fields": ("entry_fee", "prize_pool", "max_players")}),
        ("Schedule & Status", {"fields": ("start_time", "status")}),
        ("Room Details", {"fields": ("room_id", "room_password")}),
    )


@admin.action(description="Verify selected entry payments and confirm registrations")
def verify_entry_payments(modeladmin, request, queryset):
    verified_count = 0
    skipped_count = 0

    with transaction.atomic():
        for registration in queryset.select_related("tournament", "player").select_for_update():
            if registration.payment_verified:
                skipped_count += 1
                continue

            if registration.status != Registration.Status.PENDING_PAYMENT:
                skipped_count += 1
                continue

            fee = registration.entry_fee_paid
            if fee > 0:
                ledger_exists = WalletTransaction.objects.filter(
                    wallet__user=registration.player,
                    transaction_type=WalletTransaction.TransactionType.ENTRY_FEE,
                    reference=f"TOURNEY-ENTRY-{registration.pk}",
                    amount=fee,
                    status=WalletTransaction.Status.COMPLETED,
                ).exists()
                if not ledger_exists:
                    skipped_count += 1
                    continue

            registration.payment_verified = True
            registration.status = Registration.Status.CONFIRMED
            registration.save(update_fields=["payment_verified", "status", "updated_at"])

            if fee > 0:
                admin_wallet, _ = AdminWallet.objects.get_or_create(name="Main Admin Wallet")
                admin_wallet = AdminWallet.objects.select_for_update().get(pk=admin_wallet.pk)
                admin_reference = f"ADMIN-ENTRY-{registration.pk}"
                if not AdminWalletTransaction.objects.filter(reference=admin_reference).exists():
                    admin_wallet.balance += fee
                    admin_wallet.save(update_fields=["balance", "updated_at"])
                    AdminWalletTransaction.objects.create(
                        admin_wallet=admin_wallet,
                        transaction_type=AdminWalletTransaction.TransactionType.ENTRY_FEE,
                        amount=fee,
                        status=AdminWalletTransaction.Status.COMPLETED,
                        reference=admin_reference,
                        description=f"Verified entry fee for tournament {registration.tournament_id}",
                    )
            verified_count += 1

    if verified_count:
        modeladmin.message_user(request, f"{verified_count} registration(s) verified and confirmed.", messages.SUCCESS)
    if skipped_count:
        modeladmin.message_user(request, f"{skipped_count} registration(s) skipped: status or wallet ledger did not qualify.", messages.WARNING)


@admin.register(Registration)
class RegistrationAdmin(admin.ModelAdmin):
    list_display = (
        "tournament", "player", "free_fire_uid", "entry_fee_paid",
        "payment_verified", "status", "room_details_sent",
        "ready_deadline", "refund_processed", "registered_at",
    )
    list_filter = ("status", "payment_verified", "refund_processed")
    search_fields = ("free_fire_uid", "player__username", "tournament__title")
    readonly_fields = (
        "registered_at", "updated_at", "ready_confirmed_at",
        "refund_processed_at",
    )
    actions = (verify_entry_payments,)


@admin.register(KillSubmission)
class KillSubmissionAdmin(admin.ModelAdmin):
    list_display = (
        "id", "player", "tournament", "registered_uid", "free_fire_uid",
        "status", "ai_proposed_kills", "approved_kills", "approved_reward",
        "submitted_at",
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

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
