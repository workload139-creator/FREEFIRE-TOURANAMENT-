from django.contrib import admin

from .models import Registration, Tournament


class RegistrationInline(admin.TabularInline):
    model = Registration

    extra = 0

    fields = (
        "player",
        "free_fire_uid",
        "entry_fee_paid",
        "payment_verified",
        "status",
        "registered_at",
    )

    readonly_fields = ("registered_at",)

    show_change_link = True


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

    list_filter = (
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
        (
            "Tournament Information",
            {
                "fields": (
                    "title",
                    "description",
                    "status",
                ),
            },
        ),
        (
            "Fees and Players",
            {
                "fields": (
                    "entry_fee",
                    "prize_pool",
                    "max_players",
                ),
            },
        ),
        (
            "Match Details",
            {
                "fields": (
                    "start_time",
                    "room_id",
                    "room_password",
                ),
            },
        ),
        (
            "Timestamps",
            {
                "fields": (
                    "created_at",
                    "updated_at",
                ),
            },
        ),
    )

    readonly_fields = (
        "created_at",
        "updated_at",
    )


@admin.register(Registration)
class RegistrationAdmin(admin.ModelAdmin):

    list_display = (
        "player",
        "tournament",
        "free_fire_uid",
        "entry_fee_paid",
        "payment_verified",
        "status",
        "registered_at",
    )

    list_filter = (
        "status",
        "payment_verified",
        "registered_at",
    )

    search_fields = (
        "player__username",
        "free_fire_uid",
        "tournament__title",
    )

    readonly_fields = (
        "registered_at",
        "updated_at",
    )

    list_select_related = (
        "player",
        "tournament",
    )
