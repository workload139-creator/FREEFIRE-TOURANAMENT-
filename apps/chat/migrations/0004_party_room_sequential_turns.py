from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("chat", "0003_party_room_quiz_game"),
    ]

    operations = [
        migrations.AddField(
            model_name="partyroom",
            name="current_turn_player",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="party_game_current_turns",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
