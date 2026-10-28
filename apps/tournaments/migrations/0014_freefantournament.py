from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("tournaments", "0013_merge_free_fan_unlimited"),
    ]

    operations = [
        migrations.CreateModel(
            name="FreeFanTournament",
            fields=[],
            options={
                "verbose_name": "Free Fan Tournament",
                "verbose_name_plural": "Free Fan Tournaments",
                "proxy": True,
                "indexes": [],
                "constraints": [],
            },
            bases=("tournaments.tournament",),
        ),
    ]
