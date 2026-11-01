"""Admin visibility for the separate 50+50 Live AI agent pools."""
from django.contrib import admin, messages
from django.utils import timezone
from .live_ai_rewards import approve_live_kill_event

from .live_ai_models import LiveAIAgentSlot, LiveAIPaymentAssessment, LiveKillEvent


@admin.register(LiveAIAgentSlot)
class LiveAIAgentSlotAdmin(admin.ModelAdmin):
    list_display = ("tournament", "registration", "kind", "slot_number", "state", "frames_seen", "detections_seen", "last_heartbeat_at", "identity_verified_at", "identity_ocr_confidence")
    list_filter = ("kind", "state", "tournament__mode")
    search_fields = ("registration__free_fire_uid", "registration__player__username", "tournament__title")
    readonly_fields = tuple(field.name for field in LiveAIAgentSlot._meta.fields)
    actions = None

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(LiveKillEvent)
class LiveKillEventAdmin(admin.ModelAdmin):
    list_display = ("detected_at", "tournament", "registration", "match_id", "confidence", "status", "payment_ai_result", "reward_reference")
    list_filter = ("status", "tournament__mode", "tournament__br_format", "tournament__vs_format")
    search_fields = ("registration__free_fire_uid", "registration__player__username", "match_id", "event_fingerprint")
    readonly_fields = ("event_uuid", "event_fingerprint", "tournament", "registration", "session", "match_id", "attributed_player_name", "kill_at", "detected_text", "confidence", "evidence_image", "detected_at", "reward_reference", "reward_payload", "payment_ai_details")
    actions = ("approve_selected_live_kills", "reject_selected_live_kills")

    @admin.action(description="Admin approve selected live kill candidates")
    def approve_selected_live_kills(self, request, queryset):
        approved = credited = skipped = 0
        for event_id in list(queryset.values_list("pk", flat=True)):
            ok, message = approve_live_kill_event(event_id, request.user)
            if ok:
                approved += 1
                credited += int("credited once" in message)
            else:
                skipped += 1
        self.message_user(request, f"Verified: {approved}; reward credit events: {credited}; held: {skipped}.", level=messages.SUCCESS if approved else messages.WARNING)

    @admin.action(description="Reject selected live kill candidates")
    def reject_selected_live_kills(self, request, queryset):
        updated = queryset.filter(status=LiveKillEvent.Status.REVIEW).update(
            status=LiveKillEvent.Status.REJECTED,
            reviewed_at=timezone.now(),
            reviewed_by=request.user,
            review_reason="Rejected by Admin.",
        )
        self.message_user(request, f"Rejected: {updated}", level=messages.WARNING)

    @admin.display(description="Payment AI assessment")
    def payment_ai_result(self, obj):
        assessment = getattr(obj, "payment_assessment", None)
        if not assessment:
            return "Waiting for Payment AI"
        return assessment.decision_reason

    @admin.display(description="Payment AI details")
    def payment_ai_details(self, obj):
        assessment = getattr(obj, "payment_assessment", None)
        if not assessment:
            return "Not assessed yet"
        return f"Eligible: {assessment.eligible}; proposed kills: {assessment.proposed_kills}; rewards: {assessment.proposed_rewards}; checks: {assessment.checks}"

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


from .live_ai_models import LiveAIPaymentAssessment


@admin.register(LiveAIPaymentAssessment)
class LiveAIPaymentAssessmentAdmin(admin.ModelAdmin):
    list_display = ("event", "eligible", "proposed_kills", "worker_version", "assessed_at")
    list_filter = ("eligible", "worker_version", "event__tournament__mode")
    search_fields = ("event__registration__free_fire_uid", "event__registration__player__username", "event__event_fingerprint")
    readonly_fields = tuple(field.name for field in LiveAIPaymentAssessment._meta.fields)
    actions = None

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
