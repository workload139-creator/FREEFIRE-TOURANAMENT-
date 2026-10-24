from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("tournaments", "0001_initial")]
    operations = [
        migrations.AddField(
            model_name="killsubmission",
            name="ai_confidence",
            field=models.CharField(blank=True, default="", max_length=10),
        ),
        migrations.AddField(
            model_name="killsubmission",
            name="ai_uid_matches",
            field=models.BooleanField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="killsubmission",
            name="ai_review_notes",
            field=models.TextField(blank=True),
        ),
    ]
