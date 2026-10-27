from decimal import Decimal

from django import forms
from django.contrib.auth.forms import UserCreationForm

from .models import DepositRequest, User


class PlayerRegistrationForm(UserCreationForm):
    email = forms.EmailField(required=True, label="Email Address")
    phone_number = forms.CharField(max_length=15, required=True, label="Mobile Number")
    upi_id = forms.CharField(max_length=100, required=False, label="UPI ID for tournament prize payout (enter UPI ID or upload QR)")
    upi_qr_code = forms.ImageField(required=False, label="Upload your UPI QR code (UPI ID or QR required)")

    class Meta:
        model = User
        fields = (
            "username", "email", "phone_number", "gender", "upi_id", "upi_qr_code",
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

    def clean_upi_id(self):
        upi_id = (self.cleaned_data.get("upi_id") or "").strip()
        if upi_id and ("@" not in upi_id or any(char.isspace() for char in upi_id)):
            raise forms.ValidationError("Valid UPI ID enter karein, jaise name@upi.")
        return upi_id

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("upi_id") and not cleaned.get("upi_qr_code"):
            raise forms.ValidationError("Prize receive karne ke liye apni UPI ID ya UPI QR code mein se kam-se-kam ek add karein.")
        return cleaned

    def clean_upi_qr_code(self):
        qr = self.cleaned_data.get("upi_qr_code")
        if qr and qr.size > 2 * 1024 * 1024:
            raise forms.ValidationError("UPI QR image 2 MB se chhoti honi chahiye.")
        if qr and hasattr(qr, "content_type") and qr.content_type not in ("image/jpeg", "image/png", "image/webp", "image/jpg"):
            raise forms.ValidationError("UPI QR ke liye JPG, PNG ya WebP image upload karein.")
        return qr


class DepositRequestForm(forms.ModelForm):
    class Meta:
        model = DepositRequest
        fields = ["amount"]
        widgets = {
            "amount": forms.NumberInput(attrs={
                "min": "10", "max": "5000", "step": "0.01",
                "placeholder": "Minimum ₹10",
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


class ProfileUpdateForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ("username", "email", "phone_number", "gender", "profile_photo", "upi_id", "upi_qr_code")
        widgets = {
            "username": forms.TextInput(attrs={"autocomplete": "username"}),
            "email": forms.EmailInput(attrs={"autocomplete": "email"}),
            "phone_number": forms.TextInput(attrs={"autocomplete": "tel", "inputmode": "numeric"}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.get("instance")
        super().__init__(*args, **kwargs)
        self.fields["gender"].label = "Player category (Boy/Girl)"
        self.fields["gender"].required = True
        self.fields["gender"].help_text = "Used to filter Boys-only and Girls-only tournaments."
        self.fields["username"].label = "Username / Player ID name"
        self.fields["email"].label = "Email address"
        self.fields["phone_number"].label = "Mobile number"
        self.fields["profile_photo"].label = "Profile photo"
        self.fields["upi_id"].label = "UPI ID for tournament prize payout"
        self.fields["upi_id"].required = False
        self.fields["upi_qr_code"].label = "UPI QR code for prize payout"
        self.fields["upi_qr_code"].required = False
        self.fields["profile_photo"].required = False

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        existing = User.objects.filter(username__iexact=username)
        if self.instance and self.instance.pk:
            existing = existing.exclude(pk=self.instance.pk)
        if existing.exists():
            raise forms.ValidationError("Ye username kisi aur player ne le rakha hai.")
        return username

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        existing = User.objects.filter(email__iexact=email)
        if self.instance and self.instance.pk:
            existing = existing.exclude(pk=self.instance.pk)
        if existing.exists():
            raise forms.ValidationError("Ye email kisi aur account se linked hai.")
        return email

    def clean_phone_number(self):
        phone = self.cleaned_data["phone_number"].strip()
        if not phone.isdigit() or not 10 <= len(phone) <= 15:
            raise forms.ValidationError("10 se 15 digits ka valid mobile number enter karein.")
        existing = User.objects.filter(phone_number=phone)
        if self.instance and self.instance.pk:
            existing = existing.exclude(pk=self.instance.pk)
        if existing.exists():
            raise forms.ValidationError("Ye mobile number kisi aur account se linked hai.")
        return phone

    def clean_upi_id(self):
        upi_id = (self.cleaned_data.get("upi_id") or "").strip()
        if upi_id and ("@" not in upi_id or any(char.isspace() for char in upi_id)):
            raise forms.ValidationError("Valid UPI ID enter karein.")
        return upi_id

    def clean_upi_qr_code(self):
        qr = self.cleaned_data.get("upi_qr_code")
        if qr and qr.size > 2 * 1024 * 1024:
            raise forms.ValidationError("UPI QR image 2 MB se chhoti honi chahiye.")
        if qr and hasattr(qr, "content_type") and qr.content_type not in ("image/jpeg", "image/png", "image/webp"):
            raise forms.ValidationError("UPI QR ke liye JPG, PNG ya WebP image upload karein.")
        return qr

    def clean_profile_photo(self):
        photo = self.cleaned_data.get("profile_photo")
        if photo and photo.size > 2 * 1024 * 1024:
            raise forms.ValidationError("Profile photo 2 MB se chhoti honi chahiye.")
        if photo and hasattr(photo, "content_type") and photo.content_type not in ("image/jpeg", "image/png", "image/webp"):
            raise forms.ValidationError("JPG, PNG ya WebP photo upload karein.")
        return photo
