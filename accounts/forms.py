from django import forms
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

    class Meta:
        model = StaffUser
        # face_photo removed: Face ID enrollment is live-camera only.
        fields = ['staff_id', 'email', 'full_name', 'department',
                  'profile_picture']
        widgets = {
            'staff_id': forms.TextInput(attrs={'placeholder': 'e.g. EMP-001'}),
            'email': forms.EmailInput(attrs={'placeholder': 'staff@company.com'}),
            'full_name': forms.TextInput(attrs={'placeholder': 'Full Name'}),
            'department': forms.TextInput(attrs={'placeholder': 'Department (optional)'}),
        }

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
    """Form for users to update their profile picture (face_photo
    removed — Face ID enrollment is live-camera only)."""
    class Meta:
        model = StaffUser
        fields = ['profile_picture']
