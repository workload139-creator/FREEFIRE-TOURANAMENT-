from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("tournaments", "0028_live_ai_uid_verification"),
    ]

    operations = [
        migrations.CreateModel(
            name="LiveAIPaymentAssessment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("eligible", models.BooleanField(db_index=True, default=False)),
                ("proposed_kills", models.PositiveSmallIntegerField(default=0)),
                ("proposed_rewards", models.JSONField(blank=True, default=list)),
                ("checks", models.JSONField(blank=True, default=dict)),
                ("decision_reason", models.CharField(blank=True, max_length=250)),
                ("worker_version", models.CharField(default="payment-ai-v1", max_length=32)),
                ("assessed_at", models.DateTimeField(auto_now_add=True)),
                ("event", models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name="payment_assessment", to="tournaments.livekillevent")),
            ],
            options={"ordering": ("-assessed_at",)},
        ),
    ]
