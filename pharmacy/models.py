"""User-entered pharmaceutical items, scoped to a household.

Reads `registry` for reference data but never copies it: an item's
substances are read live through its `product` FK, so they always match
what the registry currently states.
"""

from django.conf import settings
from django.db import models

from households.models import Household
from registry.models import Product


class Item(models.Model):
    """One pharmaceutical box a household has at home.

    Carries no substance data of its own — see `unresolved`.
    """

    household = models.ForeignKey(
        Household,
        on_delete=models.CASCADE,
        related_name='items',
    )
    # PROTECT: F-01's loader marks absent products inactive rather than
    # deleting them, so this should never fire. If it does, that is the
    # correct outcome, not a silent cascade through user data.
    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name='items',
    )
    added_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='items_added',
    )
    added_at = models.DateTimeField(auto_now_add=True)
    # Distinguishes "the user picked this producer" from "this was the
    # tiebreak default" — the product FK alone cannot tell the two apart.
    # See pharmacy/views.py and pharmacy/static/pharmacy/js/autocomplete.js
    # for where this gets set.
    producer_confirmed = models.BooleanField(default=False)

    class Meta:
        ordering = ['-added_at']

    def __str__(self) -> str:
        return f'{self.product} ({self.household})'

    @property
    def unresolved(self) -> bool:
        """Whether the product has zero substance links.

        Must read `.all()`, not `.exists()`: the list view prefetches
        `product__substance_links`, and `.exists()` bypasses that cache and
        issues its own query per item.
        """
        return not self.product.substance_links.all()
