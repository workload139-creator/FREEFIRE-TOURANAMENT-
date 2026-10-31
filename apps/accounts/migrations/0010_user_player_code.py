import secrets

from django.db import migrations, models


def assign_player_codes(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    used_codes = set()
    for user in User.objects.only("pk").iterator():
        while True:
            code = str(secrets.randbelow(900000) + 100000)
            if code not in used_codes:
                used_codes.add(code)
                break
        User.objects.filter(pk=user.pk).update(player_code=code)


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0009_merge_profile_visibility_private_upi_qr"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="player_code",
            field=models.CharField(
                blank=True, editable=False, max_length=6, null=True, unique=True
            ),
        ),
        migrations.RunPython(assign_player_codes, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="user",
            name="player_code",
            field=models.CharField(
                blank=True, editable=False, max_length=6, unique=True
            ),
        ),
    ]
