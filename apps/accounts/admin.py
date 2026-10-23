from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = (
        "username",
        "phone_number",
        "free_fire_uid",
        "phone_verified",
        "uid_verified",
        "is_active",
    )

    search_fields = (
        "username",
        "phone_number",
        "free_fire_uid",
    )

    list_filter = (
        "phone_verified",
        "uid_verified",
        "is_active",
        "is_staff",
    )

    fieldsets = UserAdmin.fieldsets + (
        (
            "Player Details",
            {
                "fields": (
                    "phone_number",
                    "phone_verified",
                    "free_fire_uid",
                    "uid_verified",
                    "upi_id",
                    "upi_verified",
                )
            },
        ),
    )
