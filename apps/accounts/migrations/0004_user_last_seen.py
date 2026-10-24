from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0003_user_profile_photo"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="last_seen",
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
    ]
