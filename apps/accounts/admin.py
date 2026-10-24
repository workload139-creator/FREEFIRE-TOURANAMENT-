from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin
from django.core.exceptions import ValidationError
from django.db import transaction

from .models import (
    AdminWallet,
    AdminWalletTransaction,
    DepositRequest,
    User,
    Wallet,
    WalletTransaction,
)
from .services import credit_verified_deposit


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ("username", "phone_number", "free_fire_uid", "phone_verified", "uid_verified", "is_active")
    search_fields = ("username", "phone_number", "free_fire_uid")
    list_filter = ("phone_verified", "uid_verified", "is_active", "is_staff")
    fieldsets = UserAdmin.fieldsets + (
        ("Player Details", {"fields": (
            "phone_number", "phone_verified", "free_fire_uid",
            "uid_verified", "upi_id", "upi_verified",
        )}),
    )


@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = ("user", "balance", "updated_at")
    search_fields = ("user__username", "user__email")
    readonly_fields = ("created_at", "updated_at")


@admin.register(WalletTransaction)
class WalletTransactionAdmin(admin.ModelAdmin):
    list_display = ("wallet", "transaction_type", "amount", "status", "reference", "created_at")
    list_filter = ("transaction_type", "status", "created_at")
    search_fields = ("wallet__user__username", "reference", "description")
    readonly_fields = ("created_at",)


@admin.action(description="Credit deposits after checking the actual UPI/payment receipt")
def approve_verified_deposits(modeladmin, request, queryset):
    approved = 0
    skipped = 0
    for item in queryset:
        try:
            with transaction.atomic():
                deposit = DepositRequest.objects.select_for_update().select_related("wallet", "wallet__user").get(pk=item.pk)
                if deposit.status != DepositRequest.Status.PENDING or not deposit.payment_reference.strip():
                    skipped += 1
                    continue
                reference = deposit.payment_reference.strip()
                if WalletTransaction.objects.filter(reference=reference).exists():
                    skipped += 1
                    continue
                credit_verified_deposit(
                    user=deposit.wallet.user,
                    amount=deposit.amount,
                    payment_reference=reference,
                )
                deposit.status = DepositRequest.Status.APPROVED
                deposit.save(update_fields=["status"])
                approved += 1
        except (ValidationError, Wallet.DoesNotExist):
            skipped += 1

    if approved:
        modeladmin.message_user(request, f"{approved} deposit(s) credited.", messages.SUCCESS)
    if skipped:
        modeladmin.message_user(request, f"{skipped} deposit(s) skipped; verify payment reference and wallet limit.", messages.WARNING)


@admin.register(DepositRequest)
class DepositRequestAdmin(admin.ModelAdmin):
    list_display = ("wallet", "amount", "payment_reference", "status", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("wallet__user__username", "payment_reference")
    readonly_fields = ("created_at",)
    fields = ("wallet", "amount", "payment_reference", "status", "created_at")
    actions = (approve_verified_deposits,)


@admin.register(AdminWallet)
class AdminWalletAdmin(admin.ModelAdmin):
    list_display = ("name", "balance", "updated_at")
    readonly_fields = ("created_at", "updated_at")


@admin.register(AdminWalletTransaction)
class AdminWalletTransactionAdmin(admin.ModelAdmin):
    list_display = ("admin_wallet", "transaction_type", "amount", "status", "reference", "created_at")
    list_filter = ("transaction_type", "status")
    search_fields = ("admin_wallet__name", "reference", "description")
    readonly_fields = ("created_at",)
