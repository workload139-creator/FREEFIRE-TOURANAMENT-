from django.contrib import admin, messages

from .models import FriendRequest, UserBlock, UserReport, PhotoPost, FFTickSubscription, PlayerShopWallet, ShopPaymentRequest, CurrencyWithdrawalRequest, DailySpin, FanTokenAward


@admin.register(FriendRequest)
class FriendRequestAdmin(admin.ModelAdmin):
    list_display = ("requester", "recipient", "status", "created_at", "updated_at")
    list_filter = ("status", "created_at")
    search_fields = ("requester__username", "recipient__username")
    readonly_fields = ("requester", "recipient", "created_at", "updated_at")


@admin.register(UserBlock)
class UserBlockAdmin(admin.ModelAdmin):
    list_display = ("blocker", "blocked", "created_at")
    search_fields = ("blocker__username", "blocked__username")
    readonly_fields = ("blocker", "blocked", "created_at")


@admin.register(UserReport)
class UserReportAdmin(admin.ModelAdmin):
    list_display = ("reporter", "reported_user", "reason", "status", "created_at", "reviewed_at")
    list_filter = ("status", "reason", "created_at")
    search_fields = ("reporter__username", "reported_user__username", "details")
    readonly_fields = ("reporter", "reported_user", "reason", "details", "created_at")
    list_editable = ("status",)


from django.utils import timezone
from datetime import timedelta


@admin.register(PhotoPost)
class PhotoPostAdmin(admin.ModelAdmin):
    list_display = ("id", "author", "created_at", "is_hidden")
    list_filter = ("is_hidden", "created_at")
    search_fields = ("author__username", "caption")
    readonly_fields = ("created_at",)


@admin.action(description="Verify payment and activate FF Tick for 3 months")
def verify_ff_tick_payments(modeladmin, request, queryset):
    approved = skipped = 0
    for item in queryset.select_related("user"):
        if item.status != FFTickSubscription.Status.PENDING or not item.payment_reference.strip() or not item.payment_screenshot:
            skipped += 1
            continue
        now = timezone.now()
        active = FFTickSubscription.objects.filter(user=item.user, status=FFTickSubscription.Status.ACTIVE, expires_at__gt=now).order_by("-expires_at").first()
        start = active.expires_at if active else now
        item.status = FFTickSubscription.Status.ACTIVE
        item.verified_at = now
        item.expires_at = start + timedelta(days=90)
        item.verified_by = request.user
        item.save(update_fields=("status", "verified_at", "expires_at", "verified_by"))
        approved += 1
    if approved:
        modeladmin.message_user(request, f"{approved} FF Tick subscription(s) activated. Check actual UPI receipt first.", messages.SUCCESS)
    if skipped:
        modeladmin.message_user(request, f"{skipped} request(s) skipped: verify pending status, UTR and screenshot.", messages.WARNING)


@admin.action(description="Reject selected FF Tick payment requests")
def reject_ff_tick_payments(modeladmin, request, queryset):
    count = queryset.filter(status=FFTickSubscription.Status.PENDING).update(status=FFTickSubscription.Status.REJECTED, verified_by=request.user, verified_at=timezone.now())
    modeladmin.message_user(request, f"{count} pending FF Tick request(s) rejected.", messages.INFO)


@admin.register(FFTickSubscription)
class FFTickSubscriptionAdmin(admin.ModelAdmin):
    list_display = ("user", "amount", "duration_months", "payment_reference", "status", "submitted_at", "expires_at", "verified_by")
    list_filter = ("status", "submitted_at")
    search_fields = ("user__username", "payment_reference")
    readonly_fields = ("submitted_at", "verified_at", "expires_at", "verified_by")
    actions = (verify_ff_tick_payments, reject_ff_tick_payments)


from django.utils import timezone


@admin.register(PlayerShopWallet)
class PlayerShopWalletAdmin(admin.ModelAdmin):
    list_display = ("user", "diamonds", "coins", "updated_at")
    search_fields = ("user__username",)
    readonly_fields = ("updated_at",)


@admin.action(description="Verify real UPI payment and credit selected shop pack")
def approve_shop_payments(modeladmin, request, queryset):
    # Verify the actual bank/UPI transaction before using this action.
    # Lock each pending request and credit exactly once in the same DB transaction.
    from django.db import transaction
    from django.db.models import F

    approved = skipped = 0
    with transaction.atomic():
        for item_id in queryset.values_list("pk", flat=True):
            item = ShopPaymentRequest.objects.select_for_update().select_related("user").filter(pk=item_id).first()
            if item is None or item.status != ShopPaymentRequest.Status.PENDING:
                skipped += 1
                continue
            if not item.payment_reference.strip() or not item.payment_screenshot:
                skipped += 1
                continue
            wallet, _ = PlayerShopWallet.objects.get_or_create(user=item.user)
            wallet = PlayerShopWallet.objects.select_for_update().get(pk=wallet.pk)
            if item.product == ShopPaymentRequest.Product.DIAMONDS:
                wallet.diamonds = F("diamonds") + item.quantity
                wallet.save(update_fields=("diamonds", "updated_at"))
            else:
                wallet.coins = F("coins") + item.quantity
                wallet.save(update_fields=("coins", "updated_at"))
            item.status = ShopPaymentRequest.Status.APPROVED
            item.reviewed_at = timezone.now()
            item.reviewed_by = request.user
            item.save(update_fields=("status", "reviewed_at", "reviewed_by"))
            approved += 1
    modeladmin.message_user(
        request,
        f"{approved} payment request(s) credited once after verification; {skipped} skipped. Confirm the actual received transaction in bank/UPI, not just the screenshot.",
        messages.SUCCESS if approved else messages.WARNING,
    )


@admin.action(description="Reject selected pending shop payments")
def reject_shop_payments(modeladmin, request, queryset):
    count = queryset.filter(status=ShopPaymentRequest.Status.PENDING).update(status=ShopPaymentRequest.Status.REJECTED, reviewed_at=timezone.now(), reviewed_by=request.user)
    modeladmin.message_user(request, f"{count} shop request(s) rejected.", messages.INFO)


@admin.register(ShopPaymentRequest)
class ShopPaymentRequestAdmin(admin.ModelAdmin):
    list_display = ("user", "product", "quantity", "amount", "payment_reference", "status", "created_at", "reviewed_by")
    list_filter = ("status", "product", "created_at")
    search_fields = ("user__username", "payment_reference")
    # Submitted payment evidence is visible and immutable during admin review.
    readonly_fields = ("user", "product", "quantity", "amount", "payment_reference", "payment_screenshot", "created_at", "reviewed_at", "reviewed_by")
    fields = ("user", "product", "quantity", "amount", "payment_reference", "payment_screenshot", "status", "admin_note", "created_at", "reviewed_at", "reviewed_by")
    actions = (approve_shop_payments, reject_shop_payments)


@admin.action(description="Confirm PAID after sending actual UPI money and entering reference")
def mark_currency_withdrawals_paid(modeladmin, request, queryset):
    from django.db import transaction

    paid = skipped = 0
    with transaction.atomic():
        for item in queryset.select_for_update().filter(status=CurrencyWithdrawalRequest.Status.PENDING):
            # Never confirm a payout unless the admin has saved a real transfer reference.
            if not (item.payout_reference or "").strip():
                skipped += 1
                continue
            item.status = CurrencyWithdrawalRequest.Status.PAID
            item.processed_at = timezone.now()
            item.processed_by = request.user
            item.save(update_fields=("status", "processed_at", "processed_by"))
            paid += 1
    if paid:
        modeladmin.message_user(request, f"{paid} withdrawal(s) confirmed PAID.", messages.SUCCESS)
    if skipped:
        modeladmin.message_user(request, f"{skipped} request(s) remain PENDING: save the genuine UPI/UTR reference after transferring the money.", messages.WARNING)


@admin.action(description="Reject selected PENDING withdrawals and refund currency")
def reject_currency_withdrawals(modeladmin, request, queryset):
    from django.db import transaction
    from django.db.models import F

    refunded = 0
    with transaction.atomic():
        for item in queryset.select_for_update().filter(status=CurrencyWithdrawalRequest.Status.PENDING).select_related("user"):
            wallet, _ = PlayerShopWallet.objects.get_or_create(user=item.user)
            if item.currency == CurrencyWithdrawalRequest.Currency.DIAMONDS:
                PlayerShopWallet.objects.filter(pk=wallet.pk).update(diamonds=F("diamonds") + item.quantity)
            else:
                PlayerShopWallet.objects.filter(pk=wallet.pk).update(coins=F("coins") + item.quantity)
            item.status = CurrencyWithdrawalRequest.Status.REJECTED
            item.processed_at = timezone.now()
            item.processed_by = request.user
            item.save(update_fields=("status", "processed_at", "processed_by"))
            refunded += 1
    modeladmin.message_user(request, f"{refunded} withdrawal(s) rejected and currency refunded.", messages.INFO)


@admin.register(CurrencyWithdrawalRequest)
class CurrencyWithdrawalAdmin(admin.ModelAdmin):
    list_display = ("user", "currency", "quantity", "amount_inr", "upi_id", "upi_qr_code", "status", "payout_reference", "created_at")
    list_filter = ("status", "currency", "created_at")
    search_fields = ("user__username", "upi_id", "payout_reference")
    readonly_fields = ("user", "currency", "quantity", "amount_inr", "upi_id", "upi_qr_code", "status", "created_at", "processed_at", "processed_by")
    fields = ("user", "currency", "quantity", "amount_inr", "upi_id", "upi_qr_code", "status", "payout_reference", "created_at", "processed_at", "processed_by")
    actions = (mark_currency_withdrawals_paid, reject_currency_withdrawals)


@admin.register(DailySpin)
class DailySpinAdmin(admin.ModelAdmin):
    list_display = ("user", "currency", "quantity", "spun_at")
    list_filter = ("currency", "spun_at")
    search_fields = ("user__username",)
    readonly_fields = ("user", "currency", "quantity", "spun_at")
    def has_add_permission(self, request):
        return False
    def has_change_permission(self, request, obj=None):
        return False


@admin.register(FanTokenAward)
class FanTokenAwardAdmin(admin.ModelAdmin):
    list_display = ("user", "follower_milestone", "quantity", "created_at")
    list_filter = ("follower_milestone", "created_at")
    search_fields = ("user__username", "user__email")
    readonly_fields = ("user", "follower_milestone", "quantity", "created_at")
