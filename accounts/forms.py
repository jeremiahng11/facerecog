from decimal import Decimal, InvalidOperation

from django import forms
from django.conf import settings
from django.contrib.auth.forms import AuthenticationForm
from .models import StaffUser


class StaffLoginForm(forms.Form):
    staff_id = forms.CharField(
        max_length=50,
        widget=forms.TextInput(attrs={
            'placeholder': 'Enter Staff ID',
            'autocomplete': 'username',
        })
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'placeholder': 'Enter Password',
            'autocomplete': 'current-password',
        })
    )


class StaffUserCreationForm(forms.ModelForm):
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'placeholder': 'Set password'}),
        min_length=6
    )
    password_confirm = forms.CharField(
        widget=forms.PasswordInput(attrs={'placeholder': 'Confirm password'}),
        label='Confirm Password'
    )

    # Credit controls (not model fields — handled in view)
    prorate_credit = forms.BooleanField(
        required=False, initial=True,
        label='Prorate credit for this month',
    )
    manual_credit = forms.DecimalField(
        required=False, max_digits=8, decimal_places=2,
        label='Initial credit amount',
    )

    class Meta:
        model = StaffUser
        fields = ['staff_id', 'email', 'full_name', 'department',
                  'monthly_credit', 'profile_picture']
        widgets = {
            'staff_id': forms.TextInput(attrs={'placeholder': 'e.g. EMP-001'}),
            'email': forms.EmailInput(attrs={'placeholder': 'staff@company.com'}),
            'full_name': forms.TextInput(attrs={'placeholder': 'Full Name'}),
            'department': forms.TextInput(attrs={'placeholder': 'Department (optional)'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        default_credit = Decimal(str(getattr(settings, 'DEFAULT_MONTHLY_CREDIT', 50)))
        self.fields['monthly_credit'].initial = default_credit
        self.fields['manual_credit'].initial = default_credit

    def clean(self):
        cleaned_data = super().clean()
        pw = cleaned_data.get('password')
        pw2 = cleaned_data.get('password_confirm')
        if pw and pw2 and pw != pw2:
            raise forms.ValidationError("Passwords do not match.")
        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password'])
        if commit:
            user.save()
        return user


class StaffUserEditForm(forms.ModelForm):
    class Meta:
        model = StaffUser
        # face_photo removed: Face ID enrollment is live-camera only.
        fields = ['email', 'full_name', 'department',
                  'profile_picture', 'face_enabled', 'is_active']
        widgets = {
            'email': forms.EmailInput(attrs={'placeholder': 'staff@company.com'}),
            'full_name': forms.TextInput(attrs={'placeholder': 'Full Name'}),
            'department': forms.TextInput(attrs={'placeholder': 'Department (optional)'}),
        }


class FacePhotoUploadForm(forms.ModelForm):
    """Form for users to update their profile picture and kiosk PIN."""
    class Meta:
        model = StaffUser
        fields = ['profile_picture', 'kiosk_pin']
