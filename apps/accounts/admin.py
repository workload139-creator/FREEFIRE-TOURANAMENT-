from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import (
    AdminWallet,
    AdminWalletTransaction,
    DepositRequest,
    User,
    Wallet,
    WalletTransaction,
    WithdrawalRequest,
)
from .services import credit_verified_deposit


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ("username", "gender", "profile_visibility", "phone_number", "free_fire_uid", "upi_id", "upi_verified", "phone_verified", "uid_verified", "is_active")
    search_fields = ("username", "phone_number", "free_fire_uid")
    list_filter = ("gender", "phone_verified", "uid_verified", "is_active", "is_staff")
    fieldsets = UserAdmin.fieldsets + (
        ("Player Details", {"fields": (
            "phone_number", "gender", "profile_visibility", "phone_verified", "free_fire_uid",
            "uid_verified", "upi_id", "upi_qr_code", "upi_verified",
        )}),
    )


@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    fieldsets = ((None, {"fields": ("user", "balance", "created_at", "updated_at"), "description": "PLAYER WALLET: one wallet per player. Balance is read-only here. Use Deposit Requests and Withdrawal Requests for audited changes; do not edit balance directly."}),)
    list_display = ("wallet_id", "user", "balance", "updated_at")
    search_fields = ("user__username", "user__email")
    readonly_fields = ("balance", "created_at", "updated_at")


@admin.register(WalletTransaction)
class WalletTransactionAdmin(admin.ModelAdmin):
    fieldsets = ((None, {"fields": ("wallet", "transaction_type", "amount", "status", "reference", "description", "created_at"), "description": "PLAYER WALLET LEDGER: audit trail for deposits, withdrawals, entry fees, refunds and prizes. Inspect records here; do not invent or duplicate payment references."}),)
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
                if deposit.status != DepositRequest.Status.PENDING or not deposit.payment_reference.strip() or deposit.payment_reference.startswith("ffdep_"):
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
    fieldsets = ((None, {"fields": ("wallet", "amount", "payment_reference", "status", "created_at"), "description": "DEPOSIT VERIFICATION: match the reference against the actual incoming UPI/bank receipt first. Then select pending requests and run the credit action. Player deposits are ₹10–₹5,000; duplicate or placeholder references are skipped."}),)
    list_display = ("wallet", "amount", "payment_reference", "status", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("wallet__user__username", "payment_reference")
    readonly_fields = ("status", "created_at")
    actions = (approve_verified_deposits,)


@admin.register(AdminWallet)
class AdminWalletAdmin(admin.ModelAdmin):
    fieldsets = ((None, {"fields": ("name", "balance", "created_at", "updated_at"), "description": "ADMIN WALLET: internal accounting separate from player wallets. Balance is read-only here. Confirm real received top-ups through Admin Wallet Transactions; this is not a bank account."}),)
    list_display = ("wallet_id", "name", "balance", "updated_at")
    readonly_fields = ("balance", "created_at", "updated_at")


@admin.action(description="Confirm received admin UPI deposit and add it to Admin Wallet")
def confirm_admin_wallet_topups(modeladmin, request, queryset):
    credited = 0
    skipped = 0
    for item in queryset:
        with transaction.atomic():
            entry = AdminWalletTransaction.objects.select_for_update().select_related(
                "admin_wallet"
            ).get(pk=item.pk)
            if (
                entry.transaction_type != AdminWalletTransaction.TransactionType.TOP_UP
                or entry.status != AdminWalletTransaction.Status.PENDING
                or not entry.reference.strip()
            ):
                skipped += 1
                continue
            wallet = AdminWallet.objects.select_for_update().get(pk=entry.admin_wallet_id)
            wallet.balance += entry.amount
            wallet.save(update_fields=("balance", "updated_at"))
            entry.status = AdminWalletTransaction.Status.COMPLETED
            entry.save(update_fields=("status",))
            credited += 1
    if credited:
        modeladmin.message_user(
            request,
            f"{credited} verified admin deposit(s) added to the Admin Wallet ledger.",
            messages.SUCCESS,
        )
    if skipped:
        modeladmin.message_user(
            request,
            f"{skipped} item(s) skipped. Only pending top-ups with a UPI/bank reference can be confirmed.",
            messages.WARNING,
        )


@admin.register(AdminWalletTransaction)
class AdminWalletTransactionAdmin(admin.ModelAdmin):
    fieldsets = ((None, {"fields": ("admin_wallet", "transaction_type", "amount", "status", "reference", "description", "created_at"), "description": "ADMIN WALLET LEDGER: top-ups and prize/refund accounting. Verify a real received payment before confirming top-ups. Winner UPI transfers happen separately and must use a genuine UTR."}),)
    list_display = ("admin_wallet", "transaction_type", "amount", "status", "reference", "created_at")
    list_filter = ("transaction_type", "status")
    search_fields = ("admin_wallet__name", "reference", "description")
    readonly_fields = ("created_at",)
    actions = (confirm_admin_wallet_topups,)



@admin.action(description="Mark selected withdrawals paid after completing UPI transfer")
def mark_withdrawals_paid(modeladmin, request, queryset):
    updated = 0
    skipped = 0
    for item in queryset:
        with transaction.atomic():
            withdrawal = WithdrawalRequest.objects.select_for_update().select_related("wallet").get(pk=item.pk)
            if withdrawal.status != WithdrawalRequest.Status.PENDING or not withdrawal.payout_reference.strip():
                skipped += 1
                continue
            ledger = WalletTransaction.objects.filter(
                reference=f"WITHDRAW-REQ-{withdrawal.pk}",
                wallet=withdrawal.wallet,
                transaction_type=WalletTransaction.TransactionType.WITHDRAWAL,
                status=WalletTransaction.Status.PENDING,
            ).first()
            if ledger is None:
                skipped += 1
                continue
            ledger.status = WalletTransaction.Status.COMPLETED
            ledger.description = f"Manual UPI payout completed to {withdrawal.upi_id}; provider ref {withdrawal.payout_reference}"
            ledger.save(update_fields=["status", "description"])
            withdrawal.status = WithdrawalRequest.Status.PAID
            withdrawal.processed_at = timezone.now()
            withdrawal.save(update_fields=["status", "processed_at"])
            updated += 1
    if updated:
        modeladmin.message_user(request, f"{updated} withdrawal(s) marked paid.", messages.SUCCESS)
    if skipped:
        modeladmin.message_user(request, f"{skipped} request(s) skipped. Transfer first and enter payout reference.", messages.WARNING)


@admin.action(description="Reject selected withdrawals and refund wallet balance")
def reject_withdrawals_and_refund(modeladmin, request, queryset):
    refunded = 0
    skipped = 0
    for item in queryset:
        with transaction.atomic():
            withdrawal = WithdrawalRequest.objects.select_for_update().select_related("wallet", "wallet__user").get(pk=item.pk)
            if withdrawal.status != WithdrawalRequest.Status.PENDING:
                skipped += 1
                continue
            wallet = Wallet.objects.select_for_update().get(pk=withdrawal.wallet_id)
            refund_reference = f"WITHDRAW-REFUND-{withdrawal.pk}"
            if WalletTransaction.objects.filter(reference=refund_reference).exists():
                skipped += 1
                continue
            wallet.balance += withdrawal.amount
            wallet.save(update_fields=["balance", "updated_at"])
            WalletTransaction.objects.create(
                wallet=wallet,
                transaction_type=WalletTransaction.TransactionType.REFUND,
                amount=withdrawal.amount,
                status=WalletTransaction.Status.COMPLETED,
                reference=refund_reference,
                description=f"Refund for rejected withdrawal request {withdrawal.pk}",
            )
            request_ledger = WalletTransaction.objects.filter(
                reference=f"WITHDRAW-REQ-{withdrawal.pk}"
            ).first()
            if request_ledger:
                request_ledger.status = WalletTransaction.Status.FAILED
                request_ledger.save(update_fields=["status"])
            withdrawal.status = WithdrawalRequest.Status.REJECTED
            withdrawal.processed_at = timezone.now()
            withdrawal.save(update_fields=["status", "processed_at"])
            refunded += 1
    if refunded:
        modeladmin.message_user(request, f"{refunded} withdrawal(s) rejected and refunded.", messages.SUCCESS)
    if skipped:
        modeladmin.message_user(request, f"{skipped} request(s) skipped because they are not pending or a refund already exists.", messages.WARNING)


@admin.register(WithdrawalRequest)
class WithdrawalRequestAdmin(admin.ModelAdmin):
    fieldsets = ((None, {"fields": ("wallet", "amount", "upi_id", "status", "payout_reference", "created_at", "processed_at"), "description": "WITHDRAWAL PROCESSING: check the pending request and UPI ID. Send the real UPI transfer outside the website, enter the genuine payout reference, then run the paid action. If rejected, use the refund action to return the amount to the player wallet."}),)
    list_display = ("wallet", "amount", "upi_id", "status", "payout_reference", "created_at", "processed_at")
    list_filter = ("status", "created_at")
    search_fields = ("wallet__user__username", "upi_id", "payout_reference")
    readonly_fields = ("status", "created_at", "processed_at")
    actions = (mark_withdrawals_paid, reject_withdrawals_and_refund)
