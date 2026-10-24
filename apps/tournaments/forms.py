from django import forms
from django.core.exceptions import ValidationError

from .models import KillSubmission
from .validators import validate_history_video, validate_history_images


class RegistrationForm(forms.Form):
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
