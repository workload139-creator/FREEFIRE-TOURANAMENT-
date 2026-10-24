
from django.contrib import admin
from .models import Tournament, Registration


class RegistrationInline(admin.TabularInline):
    model = Registration
    extra = 0
    show_change_link = True


@admin.register(Tournament)
class TournamentAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "mode",
        "vs_format",
        "entry_fee",
        "prize_pool",
        "max_players",
        "start_time",
        "status",
    )

    list_filter = (
        "mode",
        "status",
        "start_time",
    )

    search_fields = (
        "title",
        "description",
    )

    ordering = ("start_time",)

    inlines = [RegistrationInline]

    fieldsets = (
        ("Tournament Details", {
            "fields": (
                "title",
                "description",
                "mode",
                "vs_format",
            )
        }),
        ("Fees & Players", {
            "fields": (
                "entry_fee",
                "prize_pool",
                "max_players",
            )
        }),
        ("Schedule & Status", {
            "fields": (
                "start_time",
                "status",
            )
        }),
        ("Room Details", {
            "fields": (
                "room_id",
                "room_password",
            )
        }),
    )


@admin.register(Registration)
class RegistrationAdmin(admin.ModelAdmin):
    list_display = (
        "tournament",
        "player",
        "free_fire_uid",
        "entry_fee_paid",
        "payment_verified",
        "status",
    )

    list_filter = (
        "status",
        "payment_verified",
    )

    search_fields = (
        "free_fire_uid",
        "player__username",
        "tournament__title",
    )
