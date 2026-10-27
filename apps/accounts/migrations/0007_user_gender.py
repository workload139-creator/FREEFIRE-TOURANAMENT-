from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0006_user_upi_qr_code"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="gender",
            field=models.CharField(
                blank=True,
                choices=[("boy", "Boy"), ("girl", "Girl")],
                db_index=True,
                default="",
                help_text="Player-selected profile category used for gender-based tournaments.",
                max_length=10,
            ),
        ),
    ]
