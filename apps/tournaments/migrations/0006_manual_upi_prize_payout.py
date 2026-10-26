from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("tournaments", "0005_registration_payment_reference"),
    ]

    operations = [
        migrations.AlterField(
            model_name="killsubmission",
            name="payout_reference",
            field=models.CharField(
                blank=True,
                default="",
                help_text="After sending prize manually to the player's UPI ID/QR, enter the real UPI transaction reference here and use the admin action to mark it paid.",
                max_length=100,
            ),
        ),
        migrations.AddField(
            model_name="killsubmission",
            name="payout_status",
            field=models.CharField(
                choices=[("pending", "Pending Manual UPI Payout"), ("paid", "Paid by UPI")],
                db_index=True,
                default="pending",
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name="killsubmission",
            name="payout_paid_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
