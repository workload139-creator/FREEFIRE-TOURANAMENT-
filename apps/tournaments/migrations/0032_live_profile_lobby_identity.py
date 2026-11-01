from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("tournaments", "0031_shared_live_monitor_session_state"),
    ]

    operations = [
        migrations.AddField(
            model_name="tournamentlivesession",
            name="verified_nickname",
            field=models.CharField(blank=True, default="", max_length=80),
        ),
        migrations.AddField(
            model_name="tournamentlivesession",
            name="lobby_nickname_verified_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
