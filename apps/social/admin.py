from django.contrib import admin, messages
from django.utils.html import format_html

from .models import FriendRequest, UserBlock, UserReport, PhotoPost, FFTickSubscription, PlayerShopWallet, PlayerShopWalletTransaction, ShopPaymentRequest, CurrencyWithdrawalRequest, DailySpin, FanTokenAward


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
    search_fields = ("user__username", "user__player_code", "user__email")
    readonly_fields = ("user", "diamonds", "coins", "fan_tokens", "updated_at")


@admin.action(description="Verify real UPI payment and credit selected shop pack")
def approve_shop_payments(modeladmin, request, queryset):
    # PostgreSQL requires select_for_update() to run inside transaction.atomic().
    # Lock the pending request and wallet, then credit and mark approved together.
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
                currency = PlayerShopWalletTransaction.Currency.DIAMONDS
            else:
                wallet.coins = F("coins") + item.quantity
                wallet.save(update_fields=("coins", "updated_at"))
                currency = PlayerShopWalletTransaction.Currency.COINS
            wallet.refresh_from_db()
            balance_after = wallet.diamonds if currency == PlayerShopWalletTransaction.Currency.DIAMONDS else wallet.coins
            PlayerShopWalletTransaction.objects.create(
                user=item.user, wallet=wallet, currency=currency,
                direction=PlayerShopWalletTransaction.Direction.CREDIT,
                quantity=item.quantity, balance_after=balance_after,
                source="shop_purchase", reference=item.payment_reference,
                idempotency_key=f"shop-payment:{item.pk}",
                description=f"Verified UPI shop purchase #{item.pk} · ₹{item.amount}",
            )
            item.status = ShopPaymentRequest.Status.APPROVED
            item.reviewed_at = timezone.now()
            item.reviewed_by = request.user
            item.save(update_fields=("status", "reviewed_at", "reviewed_by"))
            approved += 1
    modeladmin.message_user(
        request,
        f"{approved} shop payment(s) credited once after verification; {skipped} skipped. Verify the actual received transaction in bank/UPI, not just the screenshot.",
        messages.SUCCESS if approved else messages.WARNING,
    )


@admin.action(description="Reject selected pending shop payments")
def reject_shop_payments(modeladmin, request, queryset):
    count = queryset.filter(status=ShopPaymentRequest.Status.PENDING).update(status=ShopPaymentRequest.Status.REJECTED, reviewed_at=timezone.now(), reviewed_by=request.user)
    modeladmin.message_user(request, f"{count} shop request(s) rejected.", messages.INFO)


@admin.register(ShopPaymentRequest)
class ShopPaymentRequestAdmin(admin.ModelAdmin):
    list_display = ("id", "player_id_display", "user", "player_email_display", "player_phone_display", "player_uid_display", "product", "quantity", "amount", "payment_reference", "status", "created_at", "reviewed_by")
    list_filter = ("status", "product", "created_at")
    search_fields = ("user__username", "user__player_code", "user__email", "user__phone_number", "user__free_fire_uid", "payment_reference")
    readonly_fields = ("user", "player_id_display", "player_email_display", "player_phone_display", "player_uid_display", "player_upi_display", "player_profile_qr_preview", "product", "quantity", "amount", "payment_reference", "payment_screenshot_preview", "payment_screenshot", "status", "created_at", "reviewed_at", "reviewed_by")
    fields = ("user", "player_id_display", "player_email_display", "player_phone_display", "player_uid_display", "player_upi_display", "player_profile_qr_preview", "product", "quantity", "amount", "payment_reference", "payment_screenshot_preview", "payment_screenshot", "status", "admin_note", "created_at", "reviewed_at", "reviewed_by")
    actions = (approve_shop_payments, reject_shop_payments)

    @admin.display(description="Player ID")
    def player_id_display(self, obj):
        return obj.user.player_code if obj and obj.user_id else "—"

    @admin.display(description="Player email")
    def player_email_display(self, obj):
        return (obj.user.email or "Not provided") if obj and obj.user else "—"

    @admin.display(description="Player phone")
    def player_phone_display(self, obj):
        return (getattr(obj.user, "phone_number", "") or "Not provided") if obj and obj.user else "—"

    @admin.display(description="Free Fire UID")
    def player_uid_display(self, obj):
        return (getattr(obj.user, "free_fire_uid", "") or "Not provided") if obj and obj.user else "—"

    @admin.display(description="Player UPI ID")
    def player_upi_display(self, obj):
        return (getattr(obj.user, "upi_id", "") or "Not provided") if obj and obj.user else "—"

    @admin.display(description="Player profile UPI QR")
    def player_profile_qr_preview(self, obj):
        qr = getattr(obj.user, "upi_qr_code", None) if obj and obj.user else None
        if not qr:
            return "No profile UPI QR uploaded."
        try:
            if not qr.storage.exists(qr.name):
                return "Profile QR record exists, but media file is missing."
            url = qr.url
            return format_html('<a href="{}" target="_blank" rel="noopener"><img src="{}" alt="Player UPI QR" style="width:180px;height:180px;object-fit:contain;background:#fff;padding:8px;border-radius:10px"></a>', url, url)
        except (ValueError, OSError):
            return "Profile QR is unavailable."

    @admin.display(description="Player's uploaded payment screenshot")
    def payment_screenshot_preview(self, obj):
        if not obj or not obj.payment_screenshot:
            return "No screenshot was uploaded."
        try:
            if not obj.payment_screenshot.storage.exists(obj.payment_screenshot.name):
                return "Screenshot record exists, but the file is missing from media storage."
            url = obj.payment_screenshot.url
            return format_html(
                '<a href="{}" target="_blank" rel="noopener"><img src="{}" alt="Payment proof screenshot" style="max-width:520px;max-height:520px;object-fit:contain;background:#fff;padding:6px;border-radius:8px"></a><p><a href="{}" target="_blank" rel="noopener">Open full-size screenshot</a></p>',
                url, url, url,
            )
        except (ValueError, OSError):
            return "Screenshot uploaded, but media storage could not serve it."


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
                ledger_currency = PlayerShopWalletTransaction.Currency.DIAMONDS
            else:
                PlayerShopWallet.objects.filter(pk=wallet.pk).update(coins=F("coins") + item.quantity)
                ledger_currency = PlayerShopWalletTransaction.Currency.COINS
            wallet.refresh_from_db()
            balance_after = wallet.diamonds if ledger_currency == PlayerShopWalletTransaction.Currency.DIAMONDS else wallet.coins
            PlayerShopWalletTransaction.objects.create(
                user=item.user, wallet=wallet, currency=ledger_currency,
                direction=PlayerShopWalletTransaction.Direction.CREDIT,
                quantity=item.quantity, balance_after=balance_after,
                source="withdrawal_refund", reference=str(item.pk),
                idempotency_key=f"currency-withdrawal:{item.pk}:refund",
                description=f"Rejected withdrawal #{item.pk} — currency refunded",
            )
            item.status = CurrencyWithdrawalRequest.Status.REJECTED
            item.processed_at = timezone.now()
            item.processed_by = request.user
            item.save(update_fields=("status", "processed_at", "processed_by"))
            refunded += 1
    modeladmin.message_user(request, f"{refunded} withdrawal(s) rejected and currency refunded.", messages.INFO)


@admin.register(CurrencyWithdrawalRequest)
class CurrencyWithdrawalAdmin(admin.ModelAdmin):
    # Keep the work queue clean: only pending payouts show by default.
    # Paid/rejected requests remain in the database and can be viewed using
    # the Status filter, so the audit trail is never deleted.
    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        if "status__exact" not in request.GET:
            return queryset.filter(status=CurrencyWithdrawalRequest.Status.PENDING)
        return queryset
    list_display = ("id", "player_id_display", "user", "player_email_display", "player_phone_display", "player_uid_display", "currency", "quantity", "amount_inr", "upi_id", "upi_qr_preview", "status", "payout_reference", "created_at", "processed_at")
    list_filter = ("status", "currency", "created_at")
    search_fields = ("user__username", "user__player_code", "user__email", "user__phone_number", "user__free_fire_uid", "upi_id", "payout_reference")
    readonly_fields = ("user", "player_id_display", "player_email_display", "player_phone_display", "player_uid_display", "profile_upi_qr_preview", "currency", "quantity", "amount_inr", "upi_id", "upi_qr_code", "upi_qr_preview", "status", "created_at", "processed_at", "processed_by")
    fields = ("user", "player_id_display", "player_email_display", "player_phone_display", "player_uid_display", "currency", "quantity", "amount_inr", "upi_id", "profile_upi_qr_preview", "upi_qr_code", "upi_qr_preview", "status", "payout_reference", "created_at", "processed_at", "processed_by")
    actions = (mark_currency_withdrawals_paid, reject_currency_withdrawals)

    @admin.display(description="Player ID")
    def player_id_display(self, obj):
        return obj.user.player_code if obj and obj.user_id else "—"

    @admin.display(description="Player email")
    def player_email_display(self, obj):
        return obj.user.email or "No email on account" if obj and obj.user else "—"

    @admin.display(description="Player phone")
    def player_phone_display(self, obj):
        return (getattr(obj.user, "phone_number", "") or "Not provided") if obj and obj.user else "—"

    @admin.display(description="Free Fire UID")
    def player_uid_display(self, obj):
        return (getattr(obj.user, "free_fire_uid", "") or "Not provided") if obj and obj.user else "—"

    @admin.display(description="QR saved on player profile")
    def profile_upi_qr_preview(self, obj):
        qr = getattr(obj.user, "upi_qr_code", None) if obj and obj.user else None
        if not qr:
            return "No UPI QR is saved on the player's profile."
        try:
            if not qr.storage.exists(qr.name):
                return "Profile QR record exists, but the image file is missing from media storage."
            url = qr.url
            return format_html(
                '<a href="{}" target="_blank" rel="noopener"><img src="{}" alt="Player profile UPI QR" style="width:200px;height:200px;object-fit:contain;background:#fff;padding:8px;border-radius:10px"></a><p><a href="{}" target="_blank" rel="noopener">Open player profile QR full size</a></p>',
                url, url, url,
            )
        except (ValueError, OSError):
            return "Player profile QR is recorded but cannot be served by media storage."

    @admin.display(description="QR uploaded with this withdrawal request")
    def upi_qr_preview(self, obj):
        if not obj or not obj.upi_qr_code:
            return "Player did not upload a withdrawal QR."
        try:
            if not obj.upi_qr_code.storage.exists(obj.upi_qr_code.name):
                return "Withdrawal QR record exists, but the image file is missing from media storage."
            url = obj.upi_qr_code.url
            return format_html(
                '<a href="{}" target="_blank" rel="noopener"><img src="{}" alt="Withdrawal UPI QR" style="width:200px;height:200px;object-fit:contain;background:#fff;padding:8px;border-radius:10px"></a><p><a href="{}" target="_blank" rel="noopener">Open withdrawal QR full size</a></p>',
                url, url, url,
            )
        except (ValueError, OSError):
            return "Withdrawal QR uploaded but file is unavailable."




@admin.register(PlayerShopWalletTransaction)
class PlayerShopWalletTransactionAdmin(admin.ModelAdmin):
    list_display = ("created_at", "user", "currency", "direction", "quantity", "balance_after", "source", "reference")
    list_filter = ("currency", "direction", "source", "created_at")
    search_fields = ("user__username", "user__player_code", "user__email", "reference", "idempotency_key")
    readonly_fields = ("user", "wallet", "currency", "direction", "quantity", "balance_after", "source", "reference", "idempotency_key", "description", "created_at")
    ordering = ("-created_at", "-pk")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

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


# FF Arena unified AI assessment dashboard (explainable rule-based checks).
from django.db.models import Count
from django.shortcuts import render
from django.urls import path


def ai_assessment_dashboard(request):
    from apps.accounts.models import DepositRequest, WithdrawalRequest
    from apps.tournaments.models import KillSubmission, Registration

    pending_shop = ShopPaymentRequest.objects.filter(status=ShopPaymentRequest.Status.PENDING).select_related('user').order_by('created_at')[:12]
    pending_currency_withdrawals = CurrencyWithdrawalRequest.objects.filter(status=CurrencyWithdrawalRequest.Status.PENDING).select_related('user').order_by('created_at')[:12]
    pending_deposits = DepositRequest.objects.filter(status=DepositRequest.Status.PENDING).select_related('wallet', 'wallet__user').order_by('created_at')[:10]
    pending_cash_withdrawals = WithdrawalRequest.objects.filter(status=WithdrawalRequest.Status.PENDING).select_related('wallet', 'wallet__user').order_by('created_at')[:10]
    pending_kills = KillSubmission.objects.filter(status=KillSubmission.Status.PENDING).select_related('player', 'tournament').order_by('submitted_at')[:10]
    kill_monitor_submissions = KillSubmission.objects.select_related("player", "tournament", "registration").order_by("-submitted_at")[:20]
    kill_monitor_counts = {status: KillSubmission.objects.filter(status=status).count() for status, _label in KillSubmission.Status.choices}
    pending_registrations = Registration.objects.filter(status=Registration.Status.PENDING_PAYMENT).select_related('player', 'tournament').order_by('registered_at')[:10]
    pending_tick = FFTickSubscription.objects.filter(status=FFTickSubscription.Status.PENDING).select_related('user').order_by('submitted_at')[:10]
    open_reports = UserReport.objects.filter(status__in=(UserReport.Status.OPEN, UserReport.Status.REVIEWING)).select_related('reporter', 'reported_user').order_by('created_at')[:10]

    duplicate_refs = list(ShopPaymentRequest.objects.exclude(payment_reference='').values('payment_reference').annotate(total=Count('id')).filter(total__gt=1).values_list('payment_reference', flat=True)[:50])
    duplicate_shop_requests = ShopPaymentRequest.objects.filter(payment_reference__in=duplicate_refs).select_related('user').order_by('-created_at')[:10]
    approved_ids = list(ShopPaymentRequest.objects.filter(status=ShopPaymentRequest.Status.APPROVED).values_list('id', flat=True))
    ledger_keys = set(PlayerShopWalletTransaction.objects.filter(idempotency_key__in=[f'shop-payment:{pk}' for pk in approved_ids]).values_list('idempotency_key', flat=True))
    missing_ledger_ids = [pk for pk in approved_ids if f'shop-payment:{pk}' not in ledger_keys][:20]
    suspicious_approved_shop = ShopPaymentRequest.objects.filter(pk__in=missing_ledger_ids).select_related('user').order_by('-created_at')

    counts = {
        'shop': ShopPaymentRequest.objects.filter(status=ShopPaymentRequest.Status.PENDING).count(),
        'currency_withdrawals': CurrencyWithdrawalRequest.objects.filter(status=CurrencyWithdrawalRequest.Status.PENDING).count(),
        'deposits': DepositRequest.objects.filter(status=DepositRequest.Status.PENDING).count(),
        'cash_withdrawals': WithdrawalRequest.objects.filter(status=WithdrawalRequest.Status.PENDING).count(),
        'kills': KillSubmission.objects.filter(status=KillSubmission.Status.PENDING).count(),
        'registrations': Registration.objects.filter(status=Registration.Status.PENDING_PAYMENT).count(),
        'tick': FFTickSubscription.objects.filter(status=FFTickSubscription.Status.PENDING).count(),
        'reports': UserReport.objects.filter(status__in=(UserReport.Status.OPEN, UserReport.Status.REVIEWING)).count(),
        'ledger_alerts': len(missing_ledger_ids),
        'duplicate_shop_refs': len(duplicate_refs),
    }
    total_pending = sum(counts[k] for k in ('shop','currency_withdrawals','deposits','cash_withdrawals','kills','registrations','tick','reports'))
    risk_alerts = counts['ledger_alerts'] + counts['duplicate_shop_refs']
    links = {
        'shop': '/admin/social/shoppaymentrequest/', 'currency_withdrawals': '/admin/social/currencywithdrawalrequest/',
        'deposits': '/admin/accounts/depositrequest/', 'cash_withdrawals': '/admin/accounts/withdrawalrequest/',
        'kills': '/admin/tournaments/killsubmission/', 'registrations': '/admin/tournaments/registration/',
        'tick': '/admin/social/ffticksubscription/', 'reports': '/admin/social/userreport/',
        'ledger': '/admin/social/playershopwallettransaction/',
    }
    return render(request, 'admin/ai_assessment_dashboard.html', {
        **admin.site.each_context(request), 'title': 'AI Assessment Dashboard', 'counts': counts,
        'total_pending': total_pending, 'risk_alerts': risk_alerts, 'links': links, 'ai_api_configured': {'openai': bool(__import__('os').getenv('OPENAI_API_KEY')), 'ollama': bool(__import__('os').getenv('OLLAMA_API_KEY'))},
        'pending_shop': pending_shop, 'pending_currency_withdrawals': pending_currency_withdrawals,
        'pending_deposits': pending_deposits, 'pending_cash_withdrawals': pending_cash_withdrawals,
        'pending_kills': pending_kills, 'kill_monitor_submissions': kill_monitor_submissions, 'kill_monitor_counts': kill_monitor_counts, 'pending_registrations': pending_registrations,
        'pending_tick': pending_tick, 'open_reports': open_reports,
        'duplicate_shop_requests': duplicate_shop_requests, 'suspicious_approved_shop': suspicious_approved_shop,
    })


_original_admin_get_urls = admin.site.get_urls

def _admin_get_urls_with_ai_assessment():
    return [path('ai-assessment/', admin.site.admin_view(ai_assessment_dashboard), name='ai_assessment_dashboard')] + _original_admin_get_urls()

admin.site.get_urls = _admin_get_urls_with_ai_assessment


# Explicit admin-only API smoke test. Credentials stay on the server.
from django.shortcuts import redirect


def ai_assessment_test_apis(request):
    if request.method != "POST":
        return redirect("admin:ai_assessment_dashboard")
    from .ai_providers import test_all_providers

    results = test_all_providers()
    for provider, result in results.items():
        label = "OpenAI" if provider == "openai" else "Ollama"
        detail = f"{label} ({result['model']}): {result['message']}"
        if result["ok"]:
            messages.success(request, f"{label} API connected and inference test passed. {detail}")
        else:
            messages.error(request, f"{label} API test failed. {detail}")
    return redirect("admin:ai_assessment_dashboard")


def _admin_get_urls_with_ai_assessment_and_api_test():
    return [
        path("ai-assessment/test-apis/", admin.site.admin_view(ai_assessment_test_apis), name="ai_assessment_test_apis"),
        path("ai-assessment/", admin.site.admin_view(ai_assessment_dashboard), name="ai_assessment_dashboard"),
    ] + _original_admin_get_urls()


admin.site.get_urls = _admin_get_urls_with_ai_assessment_and_api_test
