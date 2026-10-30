import apps.core.storage
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("social", "0007_fan_tokens_and_follower_awards"),
    ]

    operations = [
        migrations.AlterField(
            model_name="ffticksubscription",
            name="payment_screenshot",
            field=models.ImageField(
                blank=True,
                null=True,
                storage=apps.core.storage.PrivateMediaStorage(),
                upload_to="ff_tick_payments/",
            ),
        ),
        migrations.AlterField(
            model_name="shoppaymentrequest",
            name="payment_screenshot",
            field=models.ImageField(
                storage=apps.core.storage.PrivateMediaStorage(),
                upload_to="shop_payments/",
            ),
        ),
        migrations.AlterField(
            model_name="currencywithdrawalrequest",
            name="upi_qr_code",
            field=models.ImageField(
                blank=True,
                null=True,
                storage=apps.core.storage.PrivateMediaStorage(),
                upload_to="currency_withdrawal_qr/",
            ),
        ),
    ]
