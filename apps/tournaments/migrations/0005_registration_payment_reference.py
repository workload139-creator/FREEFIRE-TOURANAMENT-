from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("tournaments", "0004_kill_prize_batch"),
    ]

    operations = [
        migrations.AddField(
            model_name="registration",
            name="payment_reference",
            field=models.CharField(blank=True, db_index=True, default="", max_length=100),
        ),
        migrations.AddField(
            model_name="registration",
            name="payment_submitted_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
