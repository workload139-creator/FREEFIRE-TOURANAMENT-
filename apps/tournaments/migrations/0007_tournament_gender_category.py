from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("tournaments", "0006_manual_upi_prize_payout"),
    ]

    operations = [
        migrations.AddField(
            model_name="tournament",
            name="gender_category",
            field=models.CharField(
                choices=[
                    ("open", "Open to All"),
                    ("boys", "Boys Only"),
                    ("girls", "Girls Only"),
                    ("girls_vs_boys", "Girls vs Boys"),
                ],
                db_index=True,
                default="open",
                help_text="Choose Open, Boys Only, Girls Only, or Girls vs Boys event.",
                max_length=20,
            ),
        ),
    ]
