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


from django.contrib import admin
from .models import Wallet


@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = ("user", "balance", "updated_at")
    search_fields = ("user__username", "user__email")
    readonly_fields = ("created_at", "updated_at")



from .models import WalletTransaction


@admin.register(WalletTransaction)
class WalletTransactionAdmin(admin.ModelAdmin):
    list_display = (
        "wallet",
        "transaction_type",
        "amount",
        "status",
        "reference",
        "created_at",
    )

    list_filter = ("transaction_type", "status", "created_at")

    search_fields = (
        "wallet__user__username",
        "reference",
        "description",
    )

    readonly_fields = ("created_at",)




