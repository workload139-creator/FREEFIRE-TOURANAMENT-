from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("tournaments", "0033_room_invite_and_ready_no_count"),
    ]

    operations = [
        migrations.AddField(
            model_name="tournament",
            name="winner_prize_currency",
            field=models.CharField(
                choices=[
                    ("diamonds", "Diamonds"),
                    ("coins", "Coins"),
                    ("fan_tokens", "Fan Currency"),
                ],
                default="diamonds",
                help_text="Internal wallet prize currency. This is separate from any manual INR/UPI prize pool.",
                max_length=12,
            ),
        ),
        migrations.AddField(
            model_name="tournament",
            name="winner_prize_amount",
            field=models.PositiveIntegerField(
                default=0,
                help_text="Per-player winner prize. Team formats receive this exact amount per verified team member.",
            ),
        ),
    ]
