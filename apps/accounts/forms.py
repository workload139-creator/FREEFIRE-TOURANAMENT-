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


class CurrencyWithdrawalRequestForm(forms.Form):
    currency = forms.ChoiceField(
        choices=(("diamonds", "Diamonds"), ("coins", "Coins")),
        label="Currency to withdraw",
    )
    quantity = forms.IntegerField(min_value=1, label="Quantity to convert")
    upi_id = forms.CharField(
        max_length=100,
        label="UPI ID",
        widget=forms.TextInput(attrs={"placeholder": "yourname@upi"}),
    )
    upi_qr_code = forms.ImageField(
        required=True,
        label="Your UPI QR Code image (required)",
        help_text="Apne UPI app ka QR screenshot/image upload karein (JPG, PNG, WebP; max 5 MB).",
    )

    def clean_upi_id(self):
        value = self.cleaned_data["upi_id"].strip()
        if "@" not in value or any(char.isspace() for char in value):
            raise forms.ValidationError("Valid UPI ID enter karein.")
        return value

    def clean_upi_qr_code(self):
        image = self.cleaned_data["upi_qr_code"]
        if image.size > 5 * 1024 * 1024:
            raise forms.ValidationError("UPI QR image 5 MB se chhoti honi chahiye.")
        if getattr(image, "content_type", "") not in ("image/jpeg", "image/png", "image/webp"):
            raise forms.ValidationError("UPI QR ke liye JPG, PNG ya WebP image upload karein.")
        return image


class ProfileUpdateForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ("username", "email", "gender", "profile_photo", "profile_visibility")
        widgets = {
            "username": forms.TextInput(attrs={"autocomplete": "username"}),
            "email": forms.EmailInput(attrs={"autocomplete": "email"}),
            # Use FileInput instead of ClearableFileInput: the Clear checkbox
            # conflicts with a newly selected upload and blocks profile saves.
            "profile_photo": forms.FileInput(attrs={
                "accept": "image/jpeg,image/png,image/webp",
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["gender"].label = "Player category (Boy/Girl)"
        self.fields["gender"].required = True
        self.fields["gender"].help_text = "Used to filter Boys-only and Girls-only tournaments."
        self.fields["username"].label = "Username / Player ID name"
        self.fields["email"].label = "Email address"
        self.fields["profile_photo"].label = "Profile photo"
        self.fields["profile_photo"].required = False
        self.fields["profile_visibility"].label = "Profile / Player ID visibility"
        self.fields["profile_visibility"].help_text = "Public: players can view your profile. Private: follow first to view your profile."

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

    def clean_profile_photo(self):
        photo = self.cleaned_data.get("profile_photo")
        if photo and photo.size > 2 * 1024 * 1024:
            raise forms.ValidationError("Profile photo 2 MB se chhoti honi chahiye.")
        if photo and hasattr(photo, "content_type") and photo.content_type not in ("image/jpeg", "image/png", "image/webp"):
            raise forms.ValidationError("JPG, PNG ya WebP photo upload karein.")
        return photo
