from decimal import Decimal
import django.core.validators
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("accounts", "0001_initial")]
    operations = [
        migrations.CreateModel(
            name="WithdrawalRequest",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("amount", models.DecimalField(decimal_places=2, max_digits=12, validators=[django.core.validators.MinValueValidator(Decimal("10.00"))])),
                ("upi_id", models.CharField(max_length=100)),
                ("status", models.CharField(choices=[("pending", "Pending Manual Payout"), ("paid", "Paid"), ("rejected", "Rejected and Refunded")], db_index=True, default="pending", max_length=12)),
                ("payout_reference", models.CharField(blank=True, default="", max_length=100)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("processed_at", models.DateTimeField(blank=True, null=True)),
                ("wallet", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="withdrawal_requests", to="accounts.wallet")),
            ],
            options={"ordering": ["-created_at"]},
        ),
    ]
