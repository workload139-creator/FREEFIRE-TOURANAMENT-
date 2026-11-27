from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("social", "0011_playershopwallettransaction"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="InstagramPromotionOrder",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("instagram_url", models.URLField(max_length=300)),
                ("service", models.CharField(choices=[("profile", "Profile discovery"), ("reels", "Reel/content reach"), ("engagement", "Community engagement")], max_length=16)),
                ("goal", models.CharField(blank=True, max_length=250)),
                ("status", models.CharField(choices=[("pending", "Pending review"), ("reviewing", "Reviewing"), ("completed", "Completed"), ("rejected", "Rejected")], db_index=True, default="pending", max_length=12)),
                ("admin_note", models.CharField(blank=True, max_length=500)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="instagram_promotion_orders", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ("-created_at",)},
        ),
    ]
