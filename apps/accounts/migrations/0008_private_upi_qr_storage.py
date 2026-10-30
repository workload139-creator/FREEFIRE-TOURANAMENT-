import apps.core.storage
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0007_user_gender"),
    ]

    operations = [
        migrations.AlterField(
            model_name="user",
            name="upi_qr_code",
            field=models.ImageField(
                blank=True,
                null=True,
                storage=apps.core.storage.PrivateMediaStorage(),
                upload_to="player_upi_qr/",
            ),
        ),
    ]
