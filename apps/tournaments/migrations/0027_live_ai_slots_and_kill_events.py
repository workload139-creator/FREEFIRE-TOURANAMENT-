# Separate per-player Live and Payment agent slots plus deduplicated kill candidates.
import uuid
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import apps.core.storage


class Migration(migrations.Migration):
    dependencies = [
        ("tournaments", "0026_tournament_live_session"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="LiveAIAgentSlot",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("kind", models.CharField(choices=[("live", "Live Kill AI"), ("payment", "Payment & Reward AI")], max_length=12)),
                ("slot_number", models.PositiveSmallIntegerField()),
                ("state", models.CharField(choices=[("waiting", "Waiting for stream"), ("connected", "Connected"), ("processing", "Processing"), ("degraded", "Worker issue"), ("stopped", "Stopped")], db_index=True, default="waiting", max_length=12)),
                ("last_heartbeat_at", models.DateTimeField(blank=True, null=True)),
                ("frames_seen", models.PositiveBigIntegerField(default=0)),
                ("detections_seen", models.PositiveIntegerField(default=0)),
                ("last_error", models.CharField(blank=True, max_length=250)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("registration", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="live_ai_slots", to="tournaments.registration")),
                ("session", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="ai_slots", to="tournaments.tournamentlivesession")),
                ("tournament", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="live_ai_slots", to="tournaments.tournament")),
            ],
            options={"ordering": ("tournament_id", "kind", "slot_number")},
        ),
        migrations.AddConstraint(model_name="liveaiagentslot", constraint=models.UniqueConstraint(fields=("session", "kind"), name="unique_live_ai_kind_per_session")),
        migrations.AddConstraint(model_name="liveaiagentslot", constraint=models.UniqueConstraint(fields=("tournament", "kind", "slot_number"), name="unique_live_ai_slot_per_tournament")),
        migrations.AddConstraint(model_name="liveaiagentslot", constraint=models.CheckConstraint(condition=models.Q(("slot_number__gte", 1), ("slot_number__lte", 50)), name="live_ai_slot_number_1_50")),
        migrations.CreateModel(
            name="LiveKillEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("event_uuid", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("event_fingerprint", models.CharField(max_length=64, unique=True)),
                ("match_id", models.CharField(blank=True, db_index=True, max_length=100)),
                ("kill_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("detected_text", models.TextField(blank=True)),
                ("confidence", models.DecimalField(decimal_places=4, default=0, max_digits=5)),
                ("evidence_image", models.ImageField(blank=True, null=True, storage=apps.core.storage.PrivateMediaStorage(), upload_to="live-kill-candidates/")),
                ("status", models.CharField(choices=[("review", "Needs Admin Review"), ("verified", "Verified"), ("rejected", "Rejected")], db_index=True, default="review", max_length=12)),
                ("review_reason", models.CharField(blank=True, max_length=250)),
                ("reward_reference", models.CharField(blank=True, max_length=120, null=True, unique=True)),
                ("reward_payload", models.JSONField(blank=True, default=dict)),
                ("detected_at", models.DateTimeField(auto_now_add=True)),
                ("reviewed_at", models.DateTimeField(blank=True, null=True)),
                ("registration", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="live_kill_events", to="tournaments.registration")),
                ("reviewed_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="reviewed_live_kill_events", to=settings.AUTH_USER_MODEL)),
                ("session", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="kill_events", to="tournaments.tournamentlivesession")),
                ("tournament", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="live_kill_events", to="tournaments.tournament")),
            ],
            options={"ordering": ("-detected_at",)},
        ),
        migrations.AddIndex(model_name="livekillevent", index=models.Index(fields=["tournament", "registration", "status"], name="live_kill_review_idx")),
    ]
