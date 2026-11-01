from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("tournaments", "0029_live_ai_payment_assessment"),
    ]

    operations = [
        migrations.AddField(
            model_name="livekillevent",
            name="attributed_player_name",
            field=models.CharField(blank=True, default="", max_length=80),
        ),
    ]
