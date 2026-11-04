from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("chat", "0006_partyroom_draw_restart_phase"),
    ]

    operations = [
        migrations.AddField(
            model_name="partyroom",
            name="game_question_ids",
            field=models.JSONField(blank=True, default=list),
        ),
    ]
