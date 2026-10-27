from decimal import Decimal

from django import forms
from django.contrib.auth.forms import UserCreationForm

from .models import DepositRequest, User


class PlayerRegistrationForm(UserCreationForm):
    email = forms.EmailField(required=True, label="Email Address")

    class Meta:
        model = User
        fields = (
            "username", "email", "gender",
            "password1", "password2",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # A non-model field is added here so ModelForm's Meta.fields whitelist
        # does not accidentally remove the required legal-consent checkbox.
        self.fields["gender"].label = "Player category"
        self.fields["gender"].required = True
        self.fields["gender"].help_text = "Choose Boy or Girl. This is used to show eligible gender-based tournaments."
        self.fields["accept_terms"] = forms.BooleanField(
            required=True,
            label="I agree to the Terms & Conditions and Privacy Policy",
        )

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        if not User.objects.filter(username__iexact=username).exists():
            return username

        # Keep the player's chosen name as a base and add a unique numeric suffix.
        base = username[:147]
        number = 2
        while True:
            suffix = f"{number:02d}"
            candidate = f"{base[:150 - len(suffix)]}{suffix}"
            if not User.objects.filter(username__iexact=candidate).exists():
                return candidate
            number += 1

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Ye email pehle se registered hai.")
        return email

    def clean_phone_number(self):
        phone = self.cleaned_data["phone_number"].strip()
        if not phone.isdigit() or not 10 <= len(phone) <= 15:
            raise forms.ValidationError("Sahi mobile number enter karein.")
        if User.objects.filter(phone_number=phone).exists():
            raise forms.ValidationError("Ye mobile number pehle se registered hai.")
        return phone

    def clean_profile_photo(self):
        photo = self.cleaned_data.get("profile_photo")
        if photo and photo.size > 2 * 1024 * 1024:
            raise forms.ValidationError("Profile photo 2 MB se chhoti honi chahiye.")
        if photo and hasattr(photo, "content_type") and photo.content_type not in ("image/jpeg", "image/png", "image/webp"):
            raise forms.ValidationError("JPG, PNG ya WebP photo upload karein.")
        return photo
