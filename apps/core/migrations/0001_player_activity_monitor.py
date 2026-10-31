import apps.core.models
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="PlayerActivityEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("event_key", models.CharField(default=apps.core.models.generate_event_key, max_length=32, unique=True)),
                ("category", models.CharField(choices=[("profile", "Profile"), ("wallet", "Wallet"), ("shop", "Shop"), ("withdrawal", "Withdrawal"), ("tournament", "Tournament"), ("social", "Social"), ("kill_review", "Kill Review"), ("system", "System")], db_index=True, max_length=20)),
                ("event_type", models.CharField(db_index=True, max_length=100)),
                ("object_type", models.CharField(blank=True, db_index=True, max_length=100)),
                ("object_id", models.CharField(blank=True, db_index=True, max_length=40)),
                ("object_status", models.CharField(blank=True, db_index=True, max_length=32)),
                ("summary", models.CharField(max_length=255)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("assessment_state", models.CharField(db_index=True, default="queued", max_length=16)),
                ("assessment_summary", models.TextField(blank=True)),
                ("agent_state", models.CharField(db_index=True, default="queued", max_length=16)),
                ("agent_summary", models.TextField(blank=True)),
                ("risk_level", models.CharField(choices=[("info", "Info"), ("low", "Low"), ("medium", "Medium"), ("high", "High"), ("critical", "Critical")], db_index=True, default="info", max_length=12)),
                ("risk_score", models.PositiveSmallIntegerField(default=0)),
                ("requires_admin_review", models.BooleanField(db_index=True, default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("resolved_at", models.DateTimeField(blank=True, null=True)),
                ("admin_note", models.CharField(blank=True, max_length=500)),
                ("player", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="activity_ai_events", to=settings.AUTH_USER_MODEL)),
                ("resolved_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="resolved_activity_ai_events", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ("-created_at", "-pk")},
        ),
        migrations.AddIndex(model_name="playeractivityevent", index=models.Index(fields=["category", "created_at"], name="core_act_cat_created")),
        migrations.AddIndex(model_name="playeractivityevent", index=models.Index(fields=["requires_admin_review", "risk_level", "created_at"], name="core_act_review_risk")),
        migrations.AddIndex(model_name="playeractivityevent", index=models.Index(fields=["player", "created_at"], name="core_act_player_created")),
        migrations.AddIndex(model_name="playeractivityevent", index=models.Index(fields=["object_type", "object_id"], name="core_act_object")),
    ]
