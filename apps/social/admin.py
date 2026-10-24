from django.contrib import admin

from .models import FriendRequest, UserBlock, UserReport


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
