from datetime import timedelta
from decimal import Decimal

from django.db import migrations
from django.utils import timezone


def ensure_permanent_cs_slots(apps, schema_editor):
    Tournament = apps.get_model("tournaments", "Tournament")
    now = timezone.now()

    # Create one standing, editable CS slot per format. If an active slot
    # already exists, reuse it rather than creating a duplicate. Historical,
    # completed and cancelled tournaments are never changed or deleted.
    formats = (
        ("1v1", "1 vs 1", 2, 20),
        ("2v2", "2 vs 2", 4, 38),
        ("3v3", "3 vs 3", 6, 56),
        ("4v4", "4 vs 4", 8, 84),
    )

    for code, label, capacity, diamonds in formats:
        active = Tournament.objects.filter(
            mode="VS",
            vs_format=code,
            is_free_fan_tournament=False,
            is_diwali_offer=False,
            gender_category__in=("open", "boys", "girls"),
            status__in=("upcoming", "live"),
        ).order_by("-created_at", "-pk").first()

        if active:
            # Keep admin-configured fees, prizes, room details and registrations.
            # Only normalize the standing slot's player capacity.
            if active.max_players != capacity:
                Tournament.objects.filter(pk=active.pk).update(max_players=capacity)
            continue

        Tournament.objects.create(
            title=f"Clash Squad - {label}",
            mode="VS",
            br_format="",
            vs_format=code,
            gender_category="open",
            description=(
                f"{label} Clash Squad permanent slot. "
                f"Winner prize reference: {diamonds} Diamonds (Admin managed). "
                "Each approved kill earns 2 Coins."
            ),
            entry_fee=Decimal("10.00"),
            prize_pool=Decimal("0.00"),
            max_players=capacity,
            start_time=now + timedelta(days=3650),
            status="upcoming",
            is_unlimited_br=False,
            is_diwali_offer=False,
            is_free_fan_tournament=False,
            auto_start_at_capacity=True,
            auto_reopen=False,
        )


class Migration(migrations.Migration):
    dependencies = [
        ("tournaments", "0024_private_media_storage"),
    ]

    operations = [
        migrations.RunPython(ensure_permanent_cs_slots, migrations.RunPython.noop),
    ]
