# Initial tournament and match-evidence schema.
from decimal import Decimal
import django.core.validators
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True
    dependencies = [("accounts", "0001_initial")]
    operations = [
        migrations.CreateModel(
            name="Tournament",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=120)),
                ("mode", models.CharField(choices=[("BR", "Battle Royale"), ("VS", "Clash Squad VS")], db_index=True, default="BR", max_length=2)),
                ("vs_format", models.CharField(blank=True, choices=[("1v1", "1 vs 1"), ("2v2", "2 vs 2"), ("3v3", "3 vs 3"), ("4v4", "4 vs 4")], default="", max_length=3)),
                ("description", models.TextField(blank=True)),
                ("entry_fee", models.DecimalField(decimal_places=2, default=Decimal("10.00"), max_digits=8, validators=[django.core.validators.MinValueValidator(Decimal("0.00"))])),
                ("prize_pool", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=10, validators=[django.core.validators.MinValueValidator(Decimal("0.00"))])),
                ("max_players", models.PositiveSmallIntegerField(default=49, validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(49)])),
                ("start_time", models.DateTimeField()),
                ("status", models.CharField(choices=[("draft", "Draft"), ("upcoming", "Upcoming"), ("live", "Live"), ("completed", "Completed"), ("cancelled", "Cancelled")], db_index=True, default="draft", max_length=15)),
                ("room_id", models.CharField(blank=True, max_length=100)),
                ("room_password", models.CharField(blank=True, max_length=100)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["start_time"]},
        ),
        migrations.CreateModel(
            name="Registration",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("free_fire_uid", models.CharField(max_length=30)),
                ("entry_fee_paid", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=8, validators=[django.core.validators.MinValueValidator(Decimal("0.00"))])),
                ("payment_verified", models.BooleanField(default=False)),
                ("status", models.CharField(choices=[("pending_payment", "Pending Payment"), ("confirmed", "Confirmed"), ("waiting_ready", "Waiting for Confirmation"), ("ready", "Ready to Play"), ("not_playing", "Not Playing"), ("cancelled", "Cancelled"), ("refunded", "Refunded")], db_index=True, default="pending_payment", max_length=20)),
                ("room_details_sent", models.BooleanField(default=False)),
                ("ready_deadline", models.DateTimeField(blank=True, null=True)),
                ("ready_confirmed_at", models.DateTimeField(blank=True, null=True)),
                ("refund_processed", models.BooleanField(default=False)),
                ("refund_processed_at", models.DateTimeField(blank=True, null=True)),
                ("refund_reference", models.CharField(blank=True, default="", max_length=100)),
                ("registered_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("player", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="tournament_registrations", to=settings.AUTH_USER_MODEL)),
                ("tournament", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="registrations", to="tournaments.tournament")),
            ],
            options={"ordering": ["registered_at"]},
        ),
        migrations.CreateModel(
            name="KillSubmission",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("registered_uid", models.CharField(max_length=32)),
                ("free_fire_uid", models.CharField(max_length=32)),
                ("history_video", models.FileField(upload_to="kill-evidence/videos/")),
                ("history_image_one", models.ImageField(upload_to="kill-evidence/images/")),
                ("history_image_two", models.ImageField(upload_to="kill-evidence/images/")),
                ("ai_proposed_kills", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("approved_kills", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("proposed_reward", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=10)),
                ("approved_reward", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=10)),
                ("status", models.CharField(choices=[("pending", "Pending Admin Review"), ("approved", "Approved"), ("rejected", "Rejected")], db_index=True, default="pending", max_length=12)),
                ("admin_notes", models.TextField(blank=True)),
                ("payout_reference", models.CharField(blank=True, default="", max_length=100)),
                ("submitted_at", models.DateTimeField(auto_now_add=True)),
                ("reviewed_at", models.DateTimeField(blank=True, null=True)),
                ("player", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="kill_submissions", to=settings.AUTH_USER_MODEL)),
                ("registration", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="kill_submissions", to="tournaments.registration")),
                ("tournament", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="kill_submissions", to="tournaments.tournament")),
            ],
            options={"ordering": ["-submitted_at"]},
        ),
        migrations.AddConstraint(
            model_name="registration",
            constraint=models.UniqueConstraint(fields=("tournament", "player"), name="unique_player_tournament_registration"),
        ),
        migrations.AddConstraint(
            model_name="registration",
            constraint=models.CheckConstraint(condition=models.Q(("entry_fee_paid__gte", Decimal("0.00"))), name="registration_entry_fee_nonnegative"),
        ),
    ]
