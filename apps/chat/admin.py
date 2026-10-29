from django.contrib import admin

from .models import Conversation, Message


class MessageInline(admin.TabularInline):
    model = Message
    extra = 0
    readonly_fields = ("conversation", "sender", "body", "created_at", "read_at")
    can_delete = False


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ("id", "user_one", "user_two", "created_at", "updated_at")
    search_fields = ("user_one__username", "user_two__username")
    readonly_fields = ("created_at", "updated_at")
    inlines = (MessageInline,)


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ("conversation", "sender", "body_preview", "created_at", "read_at")
    list_filter = ("created_at", "read_at")
    search_fields = ("sender__username", "body")
    readonly_fields = ("conversation", "sender", "body", "created_at", "read_at")

    def body_preview(self, obj):
        return obj.body[:80]
    body_preview.short_description = "Message"


from .party_models import PartyRoom, PartyRoomMembership, PartyRoomMessage, PartyRoomGift, CommunityTournament, CommunityTournamentEntry


@admin.register(PartyRoom)
class PartyRoomAdmin(admin.ModelAdmin):
    list_display = ("title", "host", "visibility", "is_open", "created_at")
    list_filter = ("visibility", "is_open", "theme")
    search_fields = ("title", "host__username")


@admin.register(CommunityTournament)
class CommunityTournamentAdmin(admin.ModelAdmin):
    list_display = ("title", "host", "game_mode", "starts_at", "status", "max_players")
    list_filter = ("game_mode", "status")
    search_fields = ("title", "host__username")


admin.site.register(PartyRoomMembership)
admin.site.register(PartyRoomMessage)
admin.site.register(PartyRoomGift)
admin.site.register(CommunityTournamentEntry)
