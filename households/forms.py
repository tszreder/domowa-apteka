from typing import Any

from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User

from .models import Household


class SignupForm(UserCreationForm):
    email = forms.EmailField(
        label='Adres e-mail',
        widget=forms.EmailInput(attrs={'autofocus': True, 'autocomplete': 'email'}),
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ('email',)

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.fields['password1'].widget.attrs['autocomplete'] = 'new-password'
        self.fields['password2'].widget.attrs['autocomplete'] = 'new-password'

    def clean_email(self) -> str:
        email = self.cleaned_data['email'].lower()
        if User.objects.filter(username=email).exists():
            raise forms.ValidationError('Konto z tym adresem e-mail już istnieje.')
        return email

    def save(self, commit: bool = True) -> User:
        user = super().save(commit=False)
        email = self.cleaned_data['email']
        user.username = email
        user.email = email
        if commit:
            user.save()
        return user


class EmailAuthenticationForm(AuthenticationForm):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.fields['username'].label = 'Adres e-mail'
        self.fields['username'].widget = forms.EmailInput(
            attrs={'autofocus': True, 'autocomplete': 'email'},
        )
        self.fields['password'].widget.attrs['autocomplete'] = 'current-password'

    def clean_username(self) -> str:
        return self.cleaned_data['username'].lower()


class HouseholdCreateForm(forms.ModelForm):
    class Meta:
        model = Household
        fields = ('name',)
        labels = {'name': 'Nazwa gospodarstwa domowego'}
