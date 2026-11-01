from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("tournaments", "0032_tournament_live_message"),
    ]

    operations = [
        migrations.AddField(
            model_name="tournament",
            name="room_invite_link",
            field=models.URLField(blank=True, default="", help_text="Official Free Fire India / MAX room invite link from ffshare.garena.com.", max_length=1500),
        ),
        migrations.AddField(
            model_name="registration",
            name="no_response_count",
            field=models.PositiveSmallIntegerField(
                default=0,
                help_text="NO responses or expired ready-check windows; refund after three.",
            ),
        ),
    ]
