from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("social", "0006_currency_withdrawal_qr"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="playershopwallet",
            name="fan_tokens",
            field=models.PositiveIntegerField(default=0, help_text="Non-cash tokens earned for every 10 followers; cannot be withdrawn."),
        ),
        migrations.CreateModel(
            name="FanTokenAward",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("follower_milestone", models.PositiveIntegerField(help_text="Follower count milestone, in multiples of 10.")),
                ("quantity", models.PositiveSmallIntegerField(default=1)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="fan_token_awards", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ("-created_at",)},
        ),
        migrations.AddConstraint(
            model_name="fantokenaward",
            constraint=models.UniqueConstraint(fields=("user", "follower_milestone"), name="social_unique_fan_token_milestone"),
        ),
    ]
