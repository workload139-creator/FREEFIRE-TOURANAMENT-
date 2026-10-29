import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("chat", "0001_initial"),
    ]
    operations = [
        migrations.CreateModel(
            name="PartyRoom",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=70)),
                ("description", models.CharField(blank=True, max_length=240)),
                ("theme", models.CharField(choices=[("violet", "Violet"), ("gold", "Gold"), ("ocean", "Ocean"), ("fire", "Fire")], default="violet", max_length=16)),
                ("visibility", models.CharField(choices=[("public", "Public"), ("private", "Private")], default="public", max_length=10)),
                ("passcode", models.CharField(blank=True, max_length=24)),
                ("max_members", models.PositiveSmallIntegerField(default=12)),
                ("is_open", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("host", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="hosted_party_rooms", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ("-updated_at",)},
        ),
        migrations.CreateModel(
            name="PartyRoomMembership",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("joined_at", models.DateTimeField(auto_now_add=True)),
                ("last_seen_at", models.DateTimeField(auto_now=True)),
                ("is_muted", models.BooleanField(default=False)),
                ("room", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="memberships", to="chat.partyroom")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="party_room_memberships", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ("joined_at",)},
        ),
        migrations.CreateModel(
            name="PartyRoomMessage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("body", models.CharField(max_length=1000)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("room", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="room_messages", to="chat.partyroom")),
                ("sender", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="party_room_messages", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ("created_at", "pk")},
        ),
        migrations.CreateModel(
            name="PartyRoomGift",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("gift_code", models.CharField(max_length=20)),
                ("currency", models.CharField(choices=[("diamonds", "Diamonds"), ("coins", "Coins"), ("fan_tokens", "Fan Tokens")], max_length=12)),
                ("quantity", models.PositiveIntegerField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("recipient", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="party_room_gifts_received", to=settings.AUTH_USER_MODEL)),
                ("room", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="room_gifts", to="chat.partyroom")),
                ("sender", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="party_room_gifts_sent", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name="CommunityTournament",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=90)),
                ("game_mode", models.CharField(choices=[("BR", "Battle Royale"), ("CS_1V1", "CS 1v1"), ("CS_2V2", "CS 2v2"), ("CS_3V3", "CS 3v3"), ("CS_4V4", "CS 4v4")], max_length=20)),
                ("description", models.CharField(blank=True, max_length=500)),
                ("starts_at", models.DateTimeField()),
                ("max_players", models.PositiveSmallIntegerField(default=12)),
                ("entry_note", models.CharField(blank=True, help_text="Use this to describe free entry or rules. This community feature does not collect entry fees.", max_length=120)),
                ("status", models.CharField(choices=[("open", "Registration open"), ("live", "Live"), ("completed", "Completed"), ("cancelled", "Cancelled")], db_index=True, default="open", max_length=12)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("host", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="community_tournaments", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ("starts_at", "-created_at")},
        ),
        migrations.CreateModel(
            name="CommunityTournamentEntry",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("tournament", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="entries", to="chat.communitytournament")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="community_tournament_entries", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ("created_at",)},
        ),
        migrations.AddConstraint(model_name="partyroommembership", constraint=models.UniqueConstraint(fields=("room", "user"), name="chat_party_room_unique_member")),
        migrations.AddConstraint(model_name="communitytournamententry", constraint=models.UniqueConstraint(fields=("tournament", "user"), name="chat_community_tournament_unique_entry")),
    ]
