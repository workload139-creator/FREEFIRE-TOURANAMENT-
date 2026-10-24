from decimal import Decimal

from django import forms
from django.contrib.auth.forms import UserCreationForm

from .models import DepositRequest, User


class PlayerRegistrationForm(UserCreationForm):
    email = forms.EmailField(required=True, label="Email Address")
    phone_number = forms.CharField(max_length=15, required=True, label="Mobile Number")

    class Meta:
        model = User
        fields = (
            "username", "email", "phone_number",
            "password1", "password2",
        )

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError(
                "Ye username pehle se registered hai. Login karein ya doosra username chunein."
            )
        return username

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


class DepositRequestForm(forms.ModelForm):
    class Meta:
        model = DepositRequest
        fields = ["amount", "payment_reference"]
        widgets = {
            "amount": forms.NumberInput(attrs={
                "min": "10", "max": "5000", "step": "0.01",
                "placeholder": "Minimum ₹10",
            }),
            "payment_reference": forms.TextInput(attrs={
                "placeholder": "UPI/payment reference (admin receipt check karega)",
            }),
        }

    def clean_amount(self):
        amount = self.cleaned_data["amount"]
        if amount < Decimal("10.00"):
            raise forms.ValidationError("Minimum deposit ₹10 hai.")
        if amount > Decimal("5000.00"):
            raise forms.ValidationError("Ek deposit request ₹5000 se zyada nahi ho sakti.")
        return amount


class WithdrawalRequestForm(forms.Form):
    amount = forms.DecimalField(
        min_value=Decimal("10.00"),
        max_digits=12,
        decimal_places=2,
        label="Withdrawal amount (₹)",
        widget=forms.NumberInput(attrs={"min": "10", "step": "0.01"}),
    )
    upi_id = forms.CharField(
        max_length=100,
        label="UPI ID",
        widget=forms.TextInput(attrs={"placeholder": "yourname@upi"}),
    )

    def clean_upi_id(self):
        upi_id = self.cleaned_data["upi_id"].strip()
        if "@" not in upi_id or any(char.isspace() for char in upi_id):
            raise forms.ValidationError("Valid UPI ID enter karein.")
        return upi_id
