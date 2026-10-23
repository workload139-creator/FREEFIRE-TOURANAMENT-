from django import forms
from django.contrib.auth.forms import UserCreationForm

from .models import User


class PlayerRegistrationForm(UserCreationForm):
    email = forms.EmailField(
        required=True,
        label="Email Address",
    )

    phone_number = forms.CharField(
        max_length=15,
        required=True,
        label="Mobile Number",
    )

    free_fire_uid = forms.CharField(
        max_length=32,
        required=True,
        label="Free Fire UID",
    )

    class Meta:
        model = User
        fields = (
            "username",
            "email",
            "phone_number",
            "free_fire_uid",
            "password1",
            "password2",
        )

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()

        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(
                "Ye email pehle se registered hai."
            )

        return email

    def clean_phone_number(self):
        phone = self.cleaned_data["phone_number"].strip()

        if not phone.isdigit() or not 10 <= len(phone) <= 15:
            raise forms.ValidationError(
                "Sahi mobile number enter karein."
            )

        if User.objects.filter(phone_number=phone).exists():
            raise forms.ValidationError(
                "Ye mobile number pehle se registered hai."
            )

        return phone

    def clean_free_fire_uid(self):
        uid = self.cleaned_data["free_fire_uid"].strip()

        if not uid.isdigit():
            raise forms.ValidationError(
                "Free Fire UID sirf numbers mein enter karein."
            )

        if User.objects.filter(free_fire_uid=uid).exists():
            raise forms.ValidationError(
                "Ye Free Fire UID pehle se registered hai."
            )

        return uid
