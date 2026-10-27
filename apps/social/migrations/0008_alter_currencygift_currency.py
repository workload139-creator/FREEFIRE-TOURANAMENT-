from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("social", "0007_fan_tokens_and_follower_awards"),
    ]

    operations = [
        migrations.AlterField(
            model_name="currencygift",
            name="currency",
            field=models.CharField(
                choices=[
                    ("diamonds", "Diamonds"),
                    ("coins", "Coins"),
                    ("fan_tokens", "Fan Tokens"),
                ],
                max_length=12,
            ),
        ),
    ]
