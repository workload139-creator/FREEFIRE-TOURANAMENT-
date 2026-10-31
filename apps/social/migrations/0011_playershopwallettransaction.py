from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("social", "0010_private_payment_media_storage"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="PlayerShopWalletTransaction",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("currency", models.CharField(choices=[("diamonds", "Diamonds"), ("coins", "Coins"), ("fan_tokens", "Fan Tokens")], max_length=12)),
                ("direction", models.CharField(choices=[("credit", "Credit"), ("debit", "Debit")], max_length=8)),
                ("quantity", models.PositiveIntegerField()),
                ("balance_after", models.PositiveIntegerField()),
                ("source", models.CharField(max_length=32)),
                ("reference", models.CharField(blank=True, max_length=100)),
                ("idempotency_key", models.CharField(max_length=160, unique=True)),
                ("description", models.CharField(blank=True, max_length=250)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="shop_wallet_transactions", to=settings.AUTH_USER_MODEL)),
                ("wallet", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="transactions", to="social.playershopwallet")),
            ],
            options={"ordering": ("-created_at", "-pk")},
        ),
    ]
