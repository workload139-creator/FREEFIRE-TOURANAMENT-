from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("tournaments", "0021_diwali_offer_tournament"),
    ]

    operations = [
        migrations.AddField(
            model_name="killsubmission",
            name="ai_reviewer_reports",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="killsubmission",
            name="evidence_sha256",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
