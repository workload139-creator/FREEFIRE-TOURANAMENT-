from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("tournaments", "0007_tournament_gender_category"),
    ]

    operations = [
        migrations.AddField(
            model_name="registration",
            name="verification_photo",
            field=models.ImageField(
                blank=True,
                help_text="Private registration selfie for admin review in Girls vs Boys tournaments.",
                null=True,
                upload_to="tournament_verification/",
            ),
        ),
    ]
