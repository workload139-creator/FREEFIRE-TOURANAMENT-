from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("chat", "0004_partyroom_auto_start"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="partyroom",
            name="game_phase",
            field=models.CharField(choices=[("lobby", "Lobby"), ("question", "Question"), ("decision", "Decision"), ("completed", "Completed")], db_index=True, default="lobby", max_length=12),
        ),
        migrations.AddField(
            model_name="partyroom",
            name="phase_deadline",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="partyroom",
            name="decision_index",
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="partyroom",
            name="game_winner_awarded",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="partyroom",
            name="winner",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="party_quiz_wins", to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name="partyroommembership",
            name="is_eliminated",
            field=models.BooleanField(db_index=True, default=False),
        ),
        migrations.AddField(
            model_name="partyroommembership",
            name="eliminated_round",
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="partyroommembership",
            name="elimination_reason",
            field=models.CharField(blank=True, max_length=24),
        ),
        migrations.AddField(
            model_name="partyroommembership",
            name="current_answer",
            field=models.CharField(blank=True, max_length=1),
        ),
        migrations.AddField(
            model_name="partyroommembership",
            name="answered_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="partyroommembership",
            name="score",
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="partyroommembership",
            name="decision_done",
            field=models.BooleanField(default=False),
        ),
    ]
