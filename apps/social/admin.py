from django.contrib import admin, messages

from .models import FriendRequest, UserBlock, UserReport, PhotoPost, FFTickSubscription


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
