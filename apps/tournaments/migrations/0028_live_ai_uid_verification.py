from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("tournaments", "0027_live_ai_slots_and_kill_events"),
    ]

    operations = [
        migrations.AddField(
            model_name="liveaiagentslot",
            name="identity_verified_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="liveaiagentslot",
            name="identity_ocr_confidence",
            field=models.DecimalField(decimal_places=4, default=0, max_digits=5),
        ),
    ]
