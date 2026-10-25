from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("tournaments", "0001_initial")]

    operations = [
        migrations.AddField(model_name="tournament", name="is_unlimited_br", field=models.BooleanField(default=False)),
        migrations.AddField(model_name="tournament", name="auto_start_at_capacity", field=models.BooleanField(default=False)),
        migrations.AddField(model_name="tournament", name="auto_reopen", field=models.BooleanField(default=False)),
        migrations.AddField(
            model_name="tournament", name="series_root",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="series_rounds", to="tournaments.tournament"),
        ),
        migrations.AddField(model_name="tournament", name="winner_uid", field=models.CharField(blank=True, default="", max_length=30)),
        migrations.AddField(model_name="tournament", name="winner_prize_paid", field=models.BooleanField(default=False)),
        migrations.AddField(model_name="tournament", name="winner_prize_reference", field=models.CharField(blank=True, default="", max_length=100)),
    ]
