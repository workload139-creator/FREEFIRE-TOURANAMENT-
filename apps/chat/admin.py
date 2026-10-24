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
