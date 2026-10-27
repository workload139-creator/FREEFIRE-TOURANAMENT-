from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("tournaments", "0010_tournament_ledger_entry"),
    ]

    operations = [
        migrations.AlterField(
            model_name="registration",
            name="currency_amount",
            field=models.PositiveIntegerField(
                default=0,
                help_text="Amount of Diamonds, Coins, or Fan Tokens consumed for entry.",
            ),
        ),
        migrations.AlterField(
            model_name="registration",
            name="payment_method",
            field=models.CharField(
                choices=[
                    ("upi", "UPI payment"),
                    ("diamonds", "Diamonds"),
                    ("coins", "Coins"),
                    ("fan_tokens", "Fan Tokens"),
                    ("free", "Free entry"),
                ],
                db_index=True,
                default="upi",
                max_length=12,
            ),
        ),
    ]
