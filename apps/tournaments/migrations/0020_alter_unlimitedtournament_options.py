from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("tournaments", "0019_seed_br_and_cs_formats"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="unlimitedtournament",
            options={
                "verbose_name": "Battle Royale Tournament",
                "verbose_name_plural": "Battle Royale Tournaments",
            },
        ),
    ]
