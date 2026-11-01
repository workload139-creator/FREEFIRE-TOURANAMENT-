from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("tournaments", "0033_room_invite_and_ready_no_count"),
    ]

    operations = [
        migrations.AddField(
            model_name="tournamentlivesession",
            name="observed_player_nickname",
            field=models.CharField(blank=True, default="", max_length=80),
        ),
        migrations.AddField(
            model_name="tournamentlivesession",
            name="nickname_ocr_confidence",
            field=models.DecimalField(decimal_places=4, default=0, max_digits=5),
        ),
        migrations.AddField(
            model_name="tournamentlivesession",
            name="nickname_verified_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="tournamentlivesession",
            name="nickname_last_seen_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
