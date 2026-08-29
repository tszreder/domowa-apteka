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


class ProductCheckForm(forms.Form):
    """Validation for the check screen's `?product=` query parameter.

    A plain `Form`, not a `ModelForm`: the screen saves nothing, and its whole
    claim to the user is that asking costs nothing. `ModelChoiceField` does the
    work an ad-hoc `int()` cast would do badly — a non-numeric id, an id no
    longer in the registry, and an id F-01's loader has since marked inactive
    all land on one message, and it is `ItemAddForm`'s wording rather than a
    second phrasing for the same fact.

    The queryset carries the candidate's prefetch because `ModelChoiceField`
    is what issues the lookup: `check_candidate` reads `substance_links` on
    whatever this returns, so prefetching anywhere else would mean fetching
    the row twice. `HiddenInput` for the same reason `ItemAddForm` uses it —
    a default `Select` here would render 20k options if anyone ever emitted
    this form as a whole.
    """

    product = forms.ModelChoiceField(
        queryset=Product.objects.filter(is_active=True).prefetch_related(
            'substance_links__substance'
        ),
        widget=forms.HiddenInput,
        error_messages={
            'invalid_choice': 'Ten produkt nie jest już dostępny w rejestrze.',
        },
    )
