from django import forms


class RegistrationForm(forms.Form):
    free_fire_uid = forms.CharField(
        label="Free Fire UID",
        min_length=5,
        max_length=30,
        strip=True,
        widget=forms.TextInput(
            attrs={
                "placeholder": "Apna Free Fire UID daalo",
                "autocomplete": "off",
                "inputmode": "numeric",
            }
        ),
    )

    def clean_free_fire_uid(self):
        uid = self.cleaned_data["free_fire_uid"]

        if not uid.isdigit():
            raise forms.ValidationError(
                "Free Fire UID sirf numbers mein honi chahiye."
            )

        return uid
