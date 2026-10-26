from django import forms
from django.core.exceptions import ValidationError

from .models import KillSubmission, Registration
from .validators import validate_history_video, validate_history_images


class RegistrationForm(forms.Form):
    profile_uid = forms.CharField(
        label="Website Profile UID", max_length=20, strip=True,
        widget=forms.TextInput(attrs={"inputmode": "numeric", "placeholder": "Apna website Profile UID enter karein"}),
    )
    free_fire_uid = forms.CharField(
        label="Free Fire UID",
        min_length=5,
        max_length=30,
        strip=True,
        widget=forms.TextInput(attrs={
            "placeholder": "Apna Free Fire UID daalo",
            "autocomplete": "off",
            "inputmode": "numeric",
            "pattern": "[0-9]+",
        }),
    )

    payment_reference = forms.CharField(
        label="UPI UTR / Transaction Reference", min_length=6, max_length=50, required=False,
        widget=forms.TextInput(attrs={"autocomplete": "off", "placeholder": "Payment ke baad UTR / reference number"}),
        help_text="Payment app ke transaction details se UTR/reference number daalein.",
    )

    def __init__(self, *args, user=None, tournament=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.tournament = tournament
        if user is not None and not self.is_bound:
            self.initial["profile_uid"] = str(user.pk)
        if tournament is not None and tournament.entry_fee <= 0:
            self.fields["payment_reference"].required = False
        elif tournament is not None:
            self.fields["payment_reference"].required = True

    def clean_profile_uid(self):
        value = self.cleaned_data["profile_uid"].strip()
        if not value.isdigit() or self.user is None or value != str(self.user.pk):
            raise forms.ValidationError("Profile UID match nahi hui. Apni website profile ID sahi daalein.")
        return value

    def clean_payment_reference(self):
        value = self.cleaned_data.get("payment_reference", "").strip()
        if self.tournament is not None and self.tournament.entry_fee > 0:
            if not value or not value.replace("-", "").isalnum() or len(value) < 6:
                raise forms.ValidationError("Payment ke baad valid UTR/reference (kam-se-kam 6 letters/numbers) daalein.")
            if Registration.objects.filter(payment_reference__iexact=value).exists():
                raise forms.ValidationError("Ye UTR pehle submit ho chuka hai. Apna original transaction reference check karein.")
        return value

    def clean_free_fire_uid(self):
        uid = self.cleaned_data["free_fire_uid"]
        if not uid.isdigit():
            raise forms.ValidationError("Free Fire UID sirf numbers mein honi chahiye.")
        return uid


class KillSubmissionForm(forms.ModelForm):
    consent_ai_review = forms.BooleanField(
        required=True,
        label="I agree that my submitted evidence may be processed by the configured AI review provider.",
    )

    class Meta:
        model = KillSubmission
        fields = ("free_fire_uid", "history_video", "history_image_one", "history_image_two")
        widgets = {
            "free_fire_uid": forms.TextInput(attrs={
                "inputmode": "numeric",
                "pattern": "[0-9]+",
                "placeholder": "Registered Free Fire UID",
            }),
            "history_video": forms.ClearableFileInput(attrs={"accept": ".mp4,.mov,.webm,video/mp4,video/quicktime,video/webm"}),
            "history_image_one": forms.ClearableFileInput(attrs={"accept": ".jpg,.jpeg,.png,.webp,image/*"}),
            "history_image_two": forms.ClearableFileInput(attrs={"accept": ".jpg,.jpeg,.png,.webp,image/*"}),
        }

    def clean_free_fire_uid(self):
        uid = self.cleaned_data["free_fire_uid"].strip()
        if not uid.isdigit():
            raise ValidationError("Free Fire UID sirf numbers mein honi chahiye.")
        return uid

    def clean_history_video(self):
        video = self.cleaned_data["history_video"]
        validate_history_video(video)
        return video

    def clean(self):
        cleaned = super().clean()
        images = [cleaned.get("history_image_one"), cleaned.get("history_image_two")]
        if all(images):
            validate_history_images(images)
        return cleaned
