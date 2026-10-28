from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("tournaments", "0006_manual_upi_prize_payout"),
    ]

    operations = [
        migrations.AddField(
            model_name="tournament",
            name="is_free_fan_tournament",
            field=models.BooleanField(db_index=True, default=False),
        ),
        migrations.AddField(
            model_name="tournament",
            name="winner_coins_prize",
            field=models.PositiveIntegerField(default=20, help_text="Non-cash Coins paid to the winner of the free fan tournament."),
        ),
        migrations.AddField(
            model_name="tournament",
            name="free_winner_coins_awarded",
            field=models.BooleanField(default=False),
        ),
    ]
