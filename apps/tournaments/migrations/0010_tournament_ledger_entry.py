from decimal import Decimal
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("tournaments", "0009_registration_currency_payment_fields"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="TournamentLedgerEntry",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("entry_type", models.CharField(choices=[("entry", "Entry Payment"), ("reward", "AI / Tournament Reward"), ("refund", "Refund"), ("adjustment", "Admin Adjustment")], db_index=True, max_length=12)),
                ("currency", models.CharField(choices=[("inr", "INR"), ("diamonds", "Diamonds"), ("coins", "Coins"), ("fan_tokens", "Fan Tokens")], max_length=12)),
                ("quantity", models.PositiveIntegerField(default=0)),
                ("amount_inr", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=10)),
                ("status", models.CharField(choices=[("pending", "Pending"), ("completed", "Completed"), ("rejected", "Rejected")], db_index=True, default="completed", max_length=12)),
                ("reference", models.CharField(blank=True, db_index=True, max_length=100)),
                ("description", models.CharField(blank=True, max_length=250)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("player", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="tournament_ledger_entries", to=settings.AUTH_USER_MODEL)),
                ("registration", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="ledger_entries", to="tournaments.registration")),
                ("tournament", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="ledger_entries", to="tournaments.tournament")),
            ],
            options={"ordering": ("-created_at", "-pk")},
        ),
    ]
