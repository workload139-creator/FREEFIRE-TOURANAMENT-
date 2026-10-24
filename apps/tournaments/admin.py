from django.contrib import admin
from .models import Tournament, Registration


class RegistrationInline(admin.TabularInline):
    model = Registration
    extra = 0
    readonly_fields = ("registered_at", "updated_at")


@admin.register(Tournament)
class TournamentAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "entry_fee",
        "prize_pool",
        "max_players",
        "start_time",
        "status",
    )

    list_filter = ("status", "start_time")
    search_fields = ("title", "description")
    ordering = ("start_time",)
    inlines = [RegistrationInline]


@admin.register(Registration)
class RegistrationAdmin(admin.ModelAdmin):
    list_display = (
        "player",
        "tournament",
        "free_fire_uid",
        "entry_fee_paid",
        "payment_verified",
        "status",
    )

    list_filter = ("status", "payment_verified")
    search_fields = (
        "player__username",
        "free_fire_uid",
        "tournament__title",
    )
