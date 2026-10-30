from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("tournaments", "0014_freefantournament"),
    ]

    operations = [
        migrations.AddField(
            model_name="tournament",
            name="br_format",
            field=models.CharField(blank=True, choices=[("solo", "Solo"), ("duo", "Duo"), ("squad", "Squad")], default="", help_text="Battle Royale format: Solo, Duo or Squad.", max_length=8),
        ),
        migrations.AddField(
            model_name="tournament",
            name="winner_team_uids",
            field=models.TextField(blank=True, default="", help_text="BR winning team ke registered Free Fire UIDs; har line ya comma mein ek UID. Har eligible player ko 10 Fan Tokens + 50 Coins."),
        ),
    ]
