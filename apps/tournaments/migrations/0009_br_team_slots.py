from django.db import migrations, models


def set_existing_unlimited_rounds_to_solo(apps, schema_editor):
    Tournament = apps.get_model("tournaments", "Tournament")
    Tournament.objects.filter(is_unlimited_br=True, is_free_fan_tournament=False, br_format="").update(br_format="solo", max_players=49)


class Migration(migrations.Migration):
    dependencies = [("tournaments", "0008_seed_free_fan_tournament")]
    operations = [
        migrations.AddField(model_name="registration", name="team_number", field=models.PositiveSmallIntegerField(blank=True, db_index=True, null=True)),
        migrations.AddField(model_name="registration", name="team_position", field=models.PositiveSmallIntegerField(blank=True, null=True)),
        migrations.AddField(model_name="killsubmission", name="proposed_coins_reward", field=models.PositiveSmallIntegerField(default=0)),
        migrations.AddField(model_name="killsubmission", name="approved_coins_reward", field=models.PositiveSmallIntegerField(default=0)),
        migrations.RunPython(set_existing_unlimited_rounds_to_solo, migrations.RunPython.noop),
    ]
