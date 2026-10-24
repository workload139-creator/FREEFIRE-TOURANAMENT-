import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("accounts", "0003_user_profile_photo"),
    ]
    operations = [
        migrations.CreateModel(
            name="FriendRequest",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("status", models.CharField(choices=[("pending", "Pending"), ("accepted", "Accepted"), ("rejected", "Rejected")], default="pending", max_length=12)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("recipient", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="received_friend_requests", to=settings.AUTH_USER_MODEL)),
                ("requester", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="sent_friend_requests", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ("-created_at",)},
        ),
        migrations.CreateModel(
            name="UserBlock",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("blocked", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="blocked_by_users", to=settings.AUTH_USER_MODEL)),
                ("blocker", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="blocked_users", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ("-created_at",)},
        ),
        migrations.CreateModel(
            name="UserReport",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("reason", models.CharField(choices=[("harassment", "Harassment or abuse"), ("spam", "Spam"), ("scam", "Scam or fraud"), ("inappropriate", "Inappropriate content"), ("other", "Other")], max_length=20)),
                ("details", models.TextField(blank=True, max_length=1000)),
                ("status", models.CharField(choices=[("open", "Open"), ("reviewing", "Reviewing"), ("resolved", "Resolved"), ("dismissed", "Dismissed")], default="open", max_length=12)),
                ("admin_notes", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("reviewed_at", models.DateTimeField(blank=True, null=True)),
                ("reported_user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="received_user_reports", to=settings.AUTH_USER_MODEL)),
                ("reporter", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="submitted_user_reports", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ("-created_at",)},
        ),
        migrations.AddConstraint(model_name="friendrequest", constraint=models.UniqueConstraint(fields=("requester", "recipient"), name="social_unique_friend_request_direction")),
        migrations.AddConstraint(model_name="friendrequest", constraint=models.CheckConstraint(condition=models.Q(("requester", models.F("recipient")), _negated=True), name="social_no_self_friend_request")),
        migrations.AddConstraint(model_name="userblock", constraint=models.UniqueConstraint(fields=("blocker", "blocked"), name="social_unique_user_block")),
        migrations.AddConstraint(model_name="userblock", constraint=models.CheckConstraint(condition=models.Q(("blocker", models.F("blocked")), _negated=True), name="social_no_self_block")),
    ]
