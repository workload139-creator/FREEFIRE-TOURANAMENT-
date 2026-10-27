from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("social", "0005_daily_spin_and_tournament_currency"),
    ]

    operations = [
        migrations.AddField(
            model_name="currencywithdrawalrequest",
            name="upi_qr_code",
            field=models.ImageField(blank=True, null=True, upload_to="currency_withdrawal_qr/"),
        ),
    ]
