# Add one-time redeem-code inventory and wallet transaction type.
import django.core.validators
from decimal import Decimal
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="wallettransaction",
            name="transaction_type",
            field=models.CharField(
                choices=[
                    ("deposit", "Deposit"),
                    ("withdrawal", "Withdrawal"),
                    ("entry_fee", "Tournament Entry Fee"),
                    ("refund", "Refund"),
                    ("prize", "Tournament Prize"),
                    ("redeem_code", "Redeem Code Purchase"),
                ],
                max_length=20,
            ),
        ),
        migrations.CreateModel(
            name="RedeemCode",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=120)),
                ("code", models.CharField(max_length=160, unique=True)),
                ("price", models.DecimalField(
                    decimal_places=2,
                    max_digits=10,
                    validators=[django.core.validators.MinValueValidator(Decimal("0.01"))],
                )),
                ("description", models.CharField(blank=True, max_length=255)),
                ("is_active", models.BooleanField(default=True)),
                ("claimed_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("claimed_by", models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="purchased_redeem_codes",
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={"ordering": ["price", "created_at"]},
        ),
    ]
