from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("social", "0002_photopost_ffticksubscription"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.CreateModel(
            name="PlayerShopWallet",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("diamonds", models.PositiveIntegerField(default=0)),
                ("coins", models.PositiveIntegerField(default=0)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("user", models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name="shop_wallet", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name="ShopPaymentRequest",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("product", models.CharField(choices=[("diamonds", "Diamonds"), ("coins", "Coins")], max_length=12)),
                ("quantity", models.PositiveIntegerField()),
                ("amount", models.DecimalField(decimal_places=2, max_digits=8)),
                ("payment_reference", models.CharField(max_length=100)),
                ("payment_screenshot", models.ImageField(upload_to="shop_payments/")),
                ("status", models.CharField(choices=[("pending", "Pending verification"), ("approved", "Approved"), ("rejected", "Rejected")], db_index=True, default="pending", max_length=10)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("reviewed_at", models.DateTimeField(blank=True, null=True)),
                ("admin_note", models.CharField(blank=True, max_length=250)),
                ("reviewed_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="reviewed_shop_payments", to=settings.AUTH_USER_MODEL)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="shop_payment_requests", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ("-created_at",)},
        ),
        migrations.CreateModel(
            name="CurrencyGift",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("currency", models.CharField(choices=[("diamonds", "Diamonds"), ("coins", "Coins")], max_length=12)),
                ("quantity", models.PositiveIntegerField()),
                ("conversation_id", models.PositiveBigIntegerField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("recipient", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="received_currency_gifts", to=settings.AUTH_USER_MODEL)),
                ("sender", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="sent_currency_gifts", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ("-created_at",)},
        ),
        migrations.CreateModel(
            name="CurrencyWithdrawalRequest",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("currency", models.CharField(choices=[("diamonds", "Diamonds"), ("coins", "Coins")], max_length=12)),
                ("quantity", models.PositiveIntegerField()),
                ("amount_inr", models.DecimalField(decimal_places=2, max_digits=8)),
                ("upi_id", models.CharField(max_length=100)),
                ("status", models.CharField(choices=[("pending", "Pending manual UPI payout"), ("paid", "Paid"), ("rejected", "Rejected and refunded")], db_index=True, default="pending", max_length=10)),
                ("payout_reference", models.CharField(blank=True, max_length=100)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("processed_at", models.DateTimeField(blank=True, null=True)),
                ("processed_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="processed_currency_withdrawals", to=settings.AUTH_USER_MODEL)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="currency_withdrawals", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ("-created_at",)},
        ),
    ]
