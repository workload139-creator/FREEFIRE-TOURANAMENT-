import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("accounts", "0003_user_profile_photo"),
        ("social", "0001_initial"),
    ]
    operations = [
        migrations.CreateModel(
            name="Conversation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("user_one", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="conversations_as_user_one", to=settings.AUTH_USER_MODEL)),
                ("user_two", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="conversations_as_user_two", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ("-updated_at",)},
        ),
        migrations.CreateModel(
            name="Message",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("body", models.CharField(max_length=2000)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("read_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("conversation", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="messages", to="chat.conversation")),
                ("sender", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="sent_chat_messages", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ("created_at", "pk")},
        ),
        migrations.AddConstraint(model_name="conversation", constraint=models.UniqueConstraint(fields=("user_one", "user_two"), name="chat_unique_conversation_pair")),
        migrations.AddConstraint(model_name="conversation", constraint=models.CheckConstraint(condition=models.Q(("user_one", models.F("user_two")), _negated=True), name="chat_no_self_conversation")),
    ]
