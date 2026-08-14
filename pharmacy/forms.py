from django import forms

from registry.models import Product

from .models import Item


class ItemAddForm(forms.ModelForm):
    # HiddenInput is not cosmetic: a ModelForm on a FK defaults to a Select,
    # and rendering 20,245 <option> tags would violate the one-second NFR.
    # The JavaScript autocomplete (Phase 3 § 4) sets this field's value.
    product = forms.ModelChoiceField(
        queryset=Product.objects.filter(is_active=True),
        widget=forms.HiddenInput,
        error_messages={
            'invalid_choice': 'Ten produkt nie jest już dostępny w rejestrze.',
        },
    )
    producer_confirmed = forms.BooleanField(required=False, widget=forms.HiddenInput)

    class Meta:
        model = Item
        fields = ('product', 'producer_confirmed')
