from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("tournaments", "0008_registration_verification_photo"),
    ]

    operations = [
        migrations.AddField(
            model_name="registration",
            name="payment_method",
            field=models.CharField(
                choices=[("upi", "UPI payment"), ("diamonds", "Diamonds"), ("coins", "Coins"), ("free", "Free entry")],
                db_index=True,
                default="upi",
                max_length=12,
            ),
        ),
        migrations.AddField(
            model_name="registration",
            name="currency_amount",
            field=models.PositiveIntegerField(
                default=0,
                help_text="Amount of Diamonds or Coins consumed for entry.",
            ),
        ),
    ]
