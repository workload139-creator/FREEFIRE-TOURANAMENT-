from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("tournaments", "0031_shared_live_monitor_session_state"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="TournamentLiveMessage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("body", models.CharField(max_length=500)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("read_at", models.DateTimeField(blank=True, null=True)),
                ("registration", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="live_control_messages",
                    to="tournaments.registration",
                )),
                ("sender", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="sent_live_control_messages",
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={"ordering": ("created_at",)},
        ),
        migrations.AddIndex(
            model_name="tournamentlivemessage",
            index=models.Index(fields=["registration", "created_at"], name="live_msg_reg_created_idx"),
        ),
    ]
