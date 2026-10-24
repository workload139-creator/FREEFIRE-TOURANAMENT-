"""Create or update the configured Django superuser during deployment.

Configure DJANGO_SUPERUSER_USERNAME, DJANGO_SUPERUSER_EMAIL and
DJANGO_SUPERUSER_PASSWORD in the hosting provider's environment settings.
Never hard-code credentials in source control.
"""
import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.password_validation import validate_password


class Command(BaseCommand):
    help = "Create/update a Django superuser from environment variables."

    def handle(self, *args, **options):
        username = os.getenv("DJANGO_SUPERUSER_USERNAME", "").strip()
        email = os.getenv("DJANGO_SUPERUSER_EMAIL", "").strip()
        password = os.getenv("DJANGO_SUPERUSER_PASSWORD", "")

        if not username and not email and not password:
            self.stdout.write(
                self.style.WARNING(
                    "Admin setup skipped: configure DJANGO_SUPERUSER_USERNAME, "
                    "DJANGO_SUPERUSER_EMAIL and DJANGO_SUPERUSER_PASSWORD."
                )
            )
            return

        if not username or not email or not password:
            raise CommandError(
                "Admin setup needs all three variables: DJANGO_SUPERUSER_USERNAME, "
                "DJANGO_SUPERUSER_EMAIL and DJANGO_SUPERUSER_PASSWORD."
            )

        if len(password) < 12:
            raise CommandError("DJANGO_SUPERUSER_PASSWORD must be at least 12 characters.")

        User = get_user_model()
        user = User.objects.filter(username__iexact=username).first()
        if user is not None and not user.is_superuser:
            raise CommandError(
                "The configured username already belongs to a non-superuser account. "
                "Choose a different DJANGO_SUPERUSER_USERNAME."
            )

        if user is None:
            user = User(username=username, email=email, is_staff=True, is_superuser=True)
            validate_password(password, user=user)
            user.set_password(password)
            user.save()
            self.stdout.write(self.style.SUCCESS(f"Superuser '{username}' created."))
            return

        validate_password(password, user=user)
        user.username = username
        user.email = email
        user.is_staff = True
        user.is_superuser = True
        user.set_password(password)
        user.save(update_fields=["username", "email", "is_staff", "is_superuser", "password"])
        self.stdout.write(self.style.SUCCESS(f"Superuser '{username}' password updated from environment."))
