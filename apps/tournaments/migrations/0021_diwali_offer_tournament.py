from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("tournaments", "0020_alter_unlimitedtournament_options"),
    ]

    operations = [
        migrations.AddField(
            model_name="tournament",
            name="is_diwali_offer",
            field=models.BooleanField(db_index=True, default=False),
        ),
        migrations.CreateModel(
            name="DiwaliOfferTournament",
            fields=[],
            options={
                "verbose_name": "Diwali Offer Tournament",
                "verbose_name_plural": "Diwali Offer Tournaments",
                "proxy": True,
                "indexes": [],
                "constraints": [],
            },
            bases=("tournaments.tournament",),
        ),
    ]
