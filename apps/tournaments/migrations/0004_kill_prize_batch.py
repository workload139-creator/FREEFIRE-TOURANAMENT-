from decimal import Decimal
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("tournaments", "0003_merge_20261025"),
    ]

    operations = [
        migrations.AddField(
            model_name="tournament",
            name="kill_prize_distributed",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="tournament",
            name="kill_prize_pool",
            field=models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=10),
        ),
        migrations.AddField(
            model_name="tournament",
            name="kill_prize_reference",
            field=models.CharField(blank=True, default="", max_length=100),
        ),
    ]
