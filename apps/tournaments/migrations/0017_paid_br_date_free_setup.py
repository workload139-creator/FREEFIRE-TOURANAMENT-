from django.db import migrations


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


class Migration(migrations.Migration):
    dependencies = [
        ("tournaments", "0016_merge_br_team_slots"),
    ]

    operations = [
        migrations.RunPython(mark_paid_br_events_date_free, migrations.RunPython.noop),
    ]
