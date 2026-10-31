"""Admin visibility for the separate 50+50 Live AI agent pools."""
from django.contrib import admin

from .live_ai_models import LiveAIAgentSlot, LiveKillEvent


@admin.register(LiveAIAgentSlot)
class LiveAIAgentSlotAdmin(admin.ModelAdmin):
    list_display = ("tournament", "registration", "kind", "slot_number", "state", "frames_seen", "detections_seen", "last_heartbeat_at")
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
    list_display = ("detected_at", "tournament", "registration", "match_id", "confidence", "status", "reward_reference")
    list_filter = ("status", "tournament__mode", "tournament__br_format", "tournament__vs_format")
    search_fields = ("registration__free_fire_uid", "registration__player__username", "match_id", "event_fingerprint")
    readonly_fields = ("event_uuid", "event_fingerprint", "tournament", "registration", "session", "match_id", "kill_at", "detected_text", "confidence", "evidence_image", "detected_at", "reward_reference", "reward_payload")
    actions = None

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
