from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [("accounts", "0001_initial")]
    operations = [migrations.AddField(model_name="user", name="profile_visibility", field=models.CharField(choices=[("public", "Public"), ("private", "Private")], db_index=True, default="public", help_text="Private profiles are visible only to followers.", max_length=10))]
