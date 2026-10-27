from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("social", "0004_merge_follow_and_shop"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="DailySpin",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("currency", models.CharField(choices=[("diamonds", "Diamonds"), ("coins", "Coins")], max_length=12)),
                ("quantity", models.PositiveSmallIntegerField()),
                ("spun_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="daily_spins", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ("-spun_at",)},
        ),
    ]
