from django.db import migrations


class Migration(migrations.Migration):
    # Join the Free Fan seed branch with the Unlimited Tournament notification branch.
    # This migration intentionally changes no schema or data.
    dependencies = [
        ("tournaments", "0008_seed_free_fan_tournament"),
        ("tournaments", "0012_unlimited_tournament_notifications"),
    ]

    operations = []
