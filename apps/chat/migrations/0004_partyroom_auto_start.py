from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("chat", "0003_partyroom_game_status"),
    ]

    operations = [
        migrations.AddField(
            model_name="partyroom",
            name="auto_start",
            field=models.BooleanField(default=False, help_text="Start the quiz automatically when the room reaches 12 members."),
        ),
    ]
