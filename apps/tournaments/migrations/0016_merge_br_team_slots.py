from django.db import migrations


class Migration(migrations.Migration):
    # Join the BR team/reward fields branch with the existing BR format branch.
    # Both branches add independent fields; no database schema operation is needed here.
    dependencies = [
        ("tournaments", "0009_br_team_slots"),
        ("tournaments", "0015_br_formats_and_team_rewards"),
    ]

    operations = []
