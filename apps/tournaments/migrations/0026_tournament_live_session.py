import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("tournaments", "0025_ensure_permanent_cs_slots"),
    ]

    operations = [
        migrations.CreateModel(
            name="TournamentLiveSession",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("session_uuid", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("room_name", models.CharField(max_length=120, unique=True)),
                ("participant_identity", models.CharField(max_length=120, unique=True)),
                ("status", models.CharField(choices=[("active", "Active"), ("ended", "Ended")], db_index=True, default="active", max_length=10)),
                ("background_warning_count", models.PositiveSmallIntegerField(default=0)),
                ("started_at", models.DateTimeField(auto_now_add=True)),
                ("ended_at", models.DateTimeField(blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("registration", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="live_sessions", to="tournaments.registration")),
                ("tournament", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="live_sessions", to="tournaments.tournament")),
            ],
            options={"ordering": ("-started_at",)},
        ),
        migrations.AddConstraint(
            model_name="tournamentlivesession",
            constraint=models.UniqueConstraint(condition=models.Q(("status", "active")), fields=("registration",), name="unique_active_live_session_registration"),
        ),
    ]
