from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    phone_number = models.CharField(
        max_length=15,
        unique=True,
        null=True,
        blank=True,
    )

    phone_verified = models.BooleanField(default=False)

    free_fire_uid = models.CharField(
        max_length=32,
        unique=True,
        null=True,
        blank=True,
    )

    uid_verified = models.BooleanField(default=False)

    upi_id = models.CharField(
        max_length=100,
        blank=True,
    )

    upi_verified = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.username
