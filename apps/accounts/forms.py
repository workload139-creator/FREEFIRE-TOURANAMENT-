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



from django import forms
from decimal import Decimal

from .models import DepositRequest


class DepositRequestForm(forms.ModelForm):
    class Meta:
        model = DepositRequest
        fields = ["amount", "payment_reference"]

        widgets = {
            "amount": forms.NumberInput(
                attrs={
                    "min": "10",
                    "max": "5000",
                    "step": "0.01",
                    "placeholder": "Minimum ₹10",
                }
            ),
            "payment_reference": forms.TextInput(
                attrs={
                    "placeholder": "Payment reference (if available)",
                }
            ),
        }

    def clean_amount(self):
        amount = self.cleaned_data["amount"]

        if amount < Decimal("10.00"):
            raise forms.ValidationError("Minimum deposit ₹10 hai.")

        if amount > Decimal("5000.00"):
            raise forms.ValidationError("Ek deposit request ₹5000 se zyada nahi ho sakti.")

        return amount
