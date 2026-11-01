from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("tournaments", "0029_live_ai_payment_assessment"),
    ]

    operations = [
        migrations.AddField(
            model_name="tournamentlivesession",
            name="monitor_state",
            field=models.CharField(db_index=True, default="waiting", max_length=16),
        ),
        migrations.AddField(
            model_name="tournamentlivesession",
            name="monitor_frames_seen",
            field=models.PositiveBigIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="tournamentlivesession",
            name="monitor_detections_seen",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="tournamentlivesession",
            name="identity_verified_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="tournamentlivesession",
            name="identity_ocr_confidence",
            field=models.DecimalField(decimal_places=4, default=0, max_digits=5),
        ),
        migrations.AddField(
            model_name="tournamentlivesession",
            name="monitor_last_heartbeat_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="tournamentlivesession",
            name="monitor_last_error",
            field=models.CharField(blank=True, max_length=250),
        ),
    ]
