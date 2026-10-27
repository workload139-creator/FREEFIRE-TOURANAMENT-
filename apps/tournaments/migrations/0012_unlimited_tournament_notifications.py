from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("tournaments", "0011_alter_registration_currency_amount_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="tournament",
            name="live_notification_sent_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="tournament",
            name="live_notification_status",
            field=models.CharField(db_index=True, default="pending", max_length=20),
        ),
        migrations.CreateModel(
            name="UnlimitedTournament",
            fields=[],
            options={
                "verbose_name": "Unlimited Tournament",
                "verbose_name_plural": "Unlimited Tournaments",
                "proxy": True,
                "indexes": [],
                "constraints": [],
            },
            bases=("tournaments.tournament",),
        ),
    ]
