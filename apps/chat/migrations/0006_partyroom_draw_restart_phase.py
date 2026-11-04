from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("chat", "0005_party_quiz_game"),
    ]

    operations = [
        migrations.AlterField(
            model_name="partyroom",
            name="game_phase",
            field=models.CharField(
                choices=[
                    ("lobby", "Lobby"),
                    ("question", "Question"),
                    ("decision", "Decision"),
                    ("draw", "Draw — restarting"),
                    ("completed", "Completed"),
                ],
                db_index=True,
                default="lobby",
                max_length=12,
            ),
        ),
    ]
