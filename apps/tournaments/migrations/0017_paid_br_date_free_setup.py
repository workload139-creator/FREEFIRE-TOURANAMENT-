from datetime import timedelta
from decimal import Decimal

from django.db import migrations
from django.utils import timezone


def mark_paid_br_events_date_free(apps, schema_editor):
    Tournament = apps.get_model("tournaments", "Tournament")
    eligible = Tournament.objects.filter(
        mode="BR",
        is_free_fan_tournament=False,
        gender_category__in=["open", "boys", "girls"],
    )
    eligible.update(
        is_unlimited_br=True,
        auto_start_at_capacity=True,
        auto_reopen=False,
    )
    for br_format, capacity in (("solo", 49), ("duo", 48), ("squad", 48)):
        eligible.filter(br_format=br_format).update(max_players=capacity)
    eligible.exclude(br_format__in=["solo", "duo", "squad"]).update(
        br_format="solo",
        max_players=49,
    )

    # Ensure the public BR page has one initial event for each format.
    # Admin can change each title/entry fee and create additional events later.
    for br_format, label, capacity in (
        ("solo", "Solo", 49),
        ("duo", "Duo", 48),
        ("squad", "Squad", 48),
    ):
        if not eligible.filter(
            br_format=br_format,
            status__in=["upcoming", "live"],
        ).exists():
            Tournament.objects.create(
                title=f"Battle Royale - {label}",
                mode="BR",
                br_format=br_format,
                gender_category="open",
                description=f"{label} Battle Royale event. Admin can edit the entry fee and event details.",
                entry_fee=Decimal("10.00"),
                prize_pool=Decimal("0.00"),
                max_players=capacity,
                start_time=timezone.now() + timedelta(minutes=10),
                status="upcoming",
                is_unlimited_br=True,
                is_free_fan_tournament=False,
                auto_start_at_capacity=True,
                auto_reopen=False,
            )


class Migration(migrations.Migration):
    dependencies = [
        ("tournaments", "0016_merge_br_team_slots"),
    ]

    operations = [
        migrations.RunPython(mark_paid_br_events_date_free, migrations.RunPython.noop),
    ]
