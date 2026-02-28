from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm

# Registration Form
class UserRegisterForm(UserCreationForm):
    email = forms.EmailField()

    class Meta:
        model = User
        fields = ['username', 'email', 'password1', 'password2']  


# User Update Form
class UserUpdateForm(forms.ModelForm):
    email = forms.EmailField()

    class Meta:
        model = User
        fields = ['username', 'email']  

# Profile Update Form (optional: just for future use)
class ProfileUpdateForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['password']  