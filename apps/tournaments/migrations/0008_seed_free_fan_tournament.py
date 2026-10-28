from decimal import Decimal
from django.db import migrations
from django.utils import timezone
from datetime import timedelta


def seed_free_fan_tournament(apps, schema_editor):
    Tournament = apps.get_model("tournaments", "Tournament")
    if Tournament.objects.filter(is_free_fan_tournament=True).exists():
        return
    Tournament.objects.create(
        title="Free Fan Arena - Round 1",
        mode="BR",
        vs_format="",
        gender_category="open",
        description="Free Battle Royale round. 49 verified players start the match. Every 2 approved kills earns 1 Fan Token; winner receives 20 Coins.",
        entry_fee=Decimal("0.00"),
        prize_pool=Decimal("0.00"),
        max_players=49,
        start_time=timezone.now() + timedelta(minutes=10),
        status="upcoming",
        is_unlimited_br=True,
        is_free_fan_tournament=True,
        winner_coins_prize=20,
        auto_start_at_capacity=True,
        auto_reopen=True,
    )


def unseed_free_fan_tournament(apps, schema_editor):
    # Keep tournament/player history; never delete live records in a reverse migration.
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("tournaments", "0007_free_fan_tournament"),
    ]

    operations = [
        migrations.RunPython(seed_free_fan_tournament, unseed_free_fan_tournament),
    ]
