from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("social", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.CreateModel(
            name="PhotoPost",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("photo", models.ImageField(upload_to="community_posts/")),
                ("caption", models.CharField(blank=True, max_length=180)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("is_hidden", models.BooleanField(default=False)),
                ("author", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="photo_posts", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ("-created_at",)},
        ),
        migrations.CreateModel(
            name="FFTickSubscription",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("amount", models.DecimalField(decimal_places=2, default=100, max_digits=7)),
                ("duration_months", models.PositiveSmallIntegerField(default=3)),
                ("payment_reference", models.CharField(blank=True, max_length=100)),
                ("payment_screenshot", models.ImageField(blank=True, null=True, upload_to="ff_tick_payments/")),
                ("status", models.CharField(choices=[("pending", "Pending admin verification"), ("active", "Active"), ("rejected", "Rejected")], default="pending", max_length=12)),
                ("submitted_at", models.DateTimeField(auto_now_add=True)),
                ("verified_at", models.DateTimeField(blank=True, null=True)),
                ("expires_at", models.DateTimeField(blank=True, null=True)),
                ("admin_note", models.CharField(blank=True, max_length=250)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="ff_tick_subscriptions", to=settings.AUTH_USER_MODEL)),
                ("verified_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="verified_ff_tick_payments", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ("-submitted_at",)},
        ),
    ]
