from django.contrib import admin, messages
from django.db import transaction

from apps.accounts.models import WalletTransaction
from .models import Registration, Tournament


class RegistrationInline(admin.TabularInline):
    model = Registration
    extra = 0
    show_change_link = True
    readonly_fields = (
        "registered_at", "updated_at", "ready_confirmed_at",
        "refund_processed_at",
    )


@admin.register(Tournament)
class TournamentAdmin(admin.ModelAdmin):
    list_display = (
        "title", "mode", "vs_format", "entry_fee", "prize_pool",
        "max_players", "start_time", "status",
    )
    list_filter = ("mode", "status", "start_time")
    search_fields = ("title", "description")
    ordering = ("start_time",)
    inlines = (RegistrationInline,)
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
