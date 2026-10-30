from django.db import migrations


def rename_placeholder_solo_event(apps, schema_editor):
    Tournament = apps.get_model("tournaments", "Tournament")
    Tournament.objects.filter(
        mode="BR",
        br_format="solo",
        is_free_fan_tournament=False,
        title__iexact="ff",
        status__in=["upcoming", "live"],
    ).update(title="Battle Royale - Solo")


class Migration(migrations.Migration):
    dependencies = [
        ("tournaments", "0017_paid_br_date_free_setup"),
    ]

    operations = [
        migrations.RunPython(rename_placeholder_solo_event, migrations.RunPython.noop),
    ]
