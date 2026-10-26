from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0004_user_last_seen"),
    ]

    operations = [
        migrations.AlterField(
            model_name="adminwallettransaction",
            name="transaction_type",
            field=models.CharField(
                choices=[
                    ("top_up", "Admin UPI Deposit / Top-up"),
                    ("entry_fee", "Demo Entry Fee"),
                    ("prize", "Demo Prize"),
                    ("refund", "Demo Refund"),
                    ("adjustment", "Demo Adjustment"),
                ],
                max_length=20,
            ),
        ),
    ]
