from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0005_adminwallet_top_up_choice"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="upi_qr_code",
            field=models.ImageField(blank=True, null=True, upload_to="player_upi_qr/"),
        ),
    ]
