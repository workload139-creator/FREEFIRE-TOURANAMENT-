import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("chat", "0002_party_rooms_and_community_tournaments"),
    ]

    operations = [
        migrations.AddField(
            model_name="partyroom",
            name="game_status",
            field=models.CharField(choices=[("waiting", "Waiting"), ("live", "Live"), ("break", "Round result"), ("finished", "Finished")], db_index=True, default="waiting", max_length=12),
        ),
        migrations.AddField(model_name="partyroom", name="game_round", field=models.PositiveSmallIntegerField(default=0)),
        migrations.AddField(model_name="partyroom", name="game_question", field=models.CharField(blank=True, max_length=240)),
        migrations.AddField(model_name="partyroom", name="game_answer", field=models.CharField(blank=True, max_length=80)),
        migrations.AddField(model_name="partyroom", name="game_deadline", field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name="partyroom", name="game_result", field=models.CharField(blank=True, max_length=300)),
        migrations.AddField(model_name="partyroom", name="game_winner", field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="party_game_wins", to=settings.AUTH_USER_MODEL)),
        migrations.AddField(model_name="partyroom", name="reward_awarded", field=models.BooleanField(default=False)),
        migrations.CreateModel(
            name="PartyRoomGameAnswer",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("round_number", models.PositiveSmallIntegerField()),
                ("answer", models.CharField(max_length=240)),
                ("is_correct", models.BooleanField(default=False)),
                ("answered_at", models.DateTimeField(auto_now_add=True)),
                ("player", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="party_game_answers", to=settings.AUTH_USER_MODEL)),
                ("room", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="game_answers", to="chat.partyroom")),
            ],
            options={"ordering": ("answered_at", "pk")},
        ),
        migrations.AddConstraint(
            model_name="partyroomgameanswer",
            constraint=models.UniqueConstraint(fields=("room", "round_number", "player"), name="chat_party_game_one_answer_per_round"),
        ),
    ]
