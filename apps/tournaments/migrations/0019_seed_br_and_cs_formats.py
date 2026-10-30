from datetime import timedelta
from decimal import Decimal

from django.db import migrations
from django.utils import timezone


def seed_arena_formats(apps, schema_editor):
    Tournament = apps.get_model("tournaments", "Tournament")
    active_statuses = ["upcoming", "live"]
    now = timezone.now()

    # Keep exactly one public BR card per Solo/Duo/Squad format.
    br_formats = (
        ("solo", "Solo", 49),
        ("duo", "Duo", 48),
        ("squad", "Squad", 48),
    )
    for code, label, capacity in br_formats:
        existing = Tournament.objects.filter(
            mode="BR", is_free_fan_tournament=False,
            gender_category__in=["open", "boys", "girls"],
            br_format=code, status__in=active_statuses,
        ).order_by("-created_at", "-pk").first()
        if existing is None:
            Tournament.objects.create(
                title=f"Battle Royale - {label}",
                mode="BR", br_format=code, vs_format="",
                gender_category="open",
                description=f"{label} Battle Royale tournament.",
                entry_fee=Decimal("10.00"), prize_pool=Decimal("0.00"),
                max_players=capacity,
                start_time=now + timedelta(minutes=10),
                status="upcoming", is_unlimited_br=True,
                is_free_fan_tournament=False,
                auto_start_at_capacity=True, auto_reopen=False,
            )
        else:
            Tournament.objects.filter(pk=existing.pk).update(
                max_players=capacity,
                is_unlimited_br=True,
                auto_start_at_capacity=True,
                auto_reopen=False,
            )

    # Create/normalize the four permanent Clash Squad formats.
    cs_formats = (
        ("1v1", "1 vs 1", 2, Decimal("20.00")),
        ("2v2", "2 vs 2", 4, Decimal("38.00")),
        ("3v3", "3 vs 3", 6, Decimal("56.00")),
        ("4v4", "4 vs 4", 8, Decimal("84.00")),
    )
    for code, label, capacity, prize in cs_formats:
        existing = Tournament.objects.filter(
            mode="VS", is_free_fan_tournament=False,
            gender_category__in=["open", "boys", "girls"],
            vs_format=code, status__in=active_statuses,
        ).order_by("-created_at", "-pk").first()
        if existing is None:
            Tournament.objects.create(
                title=f"Clash Squad - {label}",
                mode="VS", br_format="", vs_format=code,
                gender_category="open",
                description=(
                    f"{label} Clash Squad. Entry fee ₹10 per player. "
                    "Each approved kill earns 2 Coins. Admin tournament share: ₹8."
                ),
                entry_fee=Decimal("10.00"), prize_pool=prize,
                max_players=capacity,
                # Keep the standing CS event open for registration until admin starts it.
                start_time=now + timedelta(days=3650),
                status="upcoming", is_unlimited_br=False,
                is_free_fan_tournament=False,
                auto_start_at_capacity=False, auto_reopen=False,
            )
        else:
            Tournament.objects.filter(pk=existing.pk).update(
                entry_fee=Decimal("10.00"),
                prize_pool=prize,
                max_players=capacity,
            )


class Migration(migrations.Migration):
    dependencies = [
        ("tournaments", "0018_name_solo_br_event"),
    ]

    operations = [
        migrations.RunPython(seed_arena_formats, migrations.RunPython.noop),
    ]
