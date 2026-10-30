from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("social", "0008_alter_currencygift_currency"),
    ]

    operations = [
        migrations.AlterField(
            model_name="dailyspin",
            name="currency",
            field=models.CharField(
                choices=[
                    ("diamonds", "Diamonds"),
                    ("coins", "Coins"),
                    ("fan_tokens", "Fan Currency"),
                ],
                max_length=12,
            ),
        ),
    ]
