from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("chat", "0002_party_rooms_and_community_tournaments"),
    ]

    operations = [
        migrations.AddField(
            model_name="partyroom",
            name="game_status",
            field=models.CharField(
                choices=[("lobby", "Lobby"), ("live", "Live"), ("completed", "Completed")],
                db_index=True,
                default="lobby",
                max_length=12,
            ),
        ),
        migrations.AddField(
            model_name="partyroom",
            name="current_round",
            field=models.PositiveSmallIntegerField(default=0),
        ),
    ]
