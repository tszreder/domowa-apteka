"""Pin `Item.unresolved` and the FK on-delete contracts.

Fixtures are hand-built registry rows, not the real snapshot — see
`registry/tests/test_suggestions.py` for the same convention applied to the
grouping rules.
"""

from datetime import date

from django.contrib.auth.models import User
from django.db.models import ProtectedError
from django.test import TestCase

from households.models import Household, Membership
from pharmacy.models import Item
from registry.models import Product, ProductSubstance, SourceField, Substance

AS_OF = date(2026, 8, 13)


def make_product(registry_id: str, name: str = 'Apap', **overrides: object) -> Product:
    defaults: dict[str, object] = {
        'registry_id': registry_id,
        'name': name,
        'kind': 'ludzki',
        'last_seen_as_of': AS_OF,
        'is_active': True,
    }
    defaults.update(overrides)
    return Product.objects.create(**defaults)


class ItemUnresolvedTests(TestCase):
    def test_unresolved_true_when_product_has_no_substance_links(self) -> None:
        product = make_product('1')
        item = Item(product=product)

        self.assertTrue(item.unresolved)

    def test_unresolved_false_when_product_has_a_substance_link(self) -> None:
        product = make_product('2')
        substance = Substance.objects.create(name='Paracetamol', name_key='paracetamol')
        ProductSubstance.objects.create(
            product=product,
            substance=substance,
            source_field=SourceField.SUBSTANCE_ROW,
            source_order=0,
        )
        item = Item(product=product)

        self.assertFalse(item.unresolved)


class ItemFieldDefaultsTests(TestCase):
    def setUp(self) -> None:
        self.household = Household.objects.create(name='Kowalscy')
        self.product = make_product('3')

    def test_producer_confirmed_defaults_to_false(self) -> None:
        item = Item.objects.create(household=self.household, product=self.product)

        self.assertFalse(item.producer_confirmed)

    def test_added_by_set_null_when_user_deleted(self) -> None:
        user = User.objects.create_user(username='alice@example.com', password='pass12345')
        Membership.objects.create(user=user, household=self.household)
        item = Item.objects.create(
            household=self.household, product=self.product, added_by=user
        )

        user.delete()
        item.refresh_from_db()

        self.assertIsNone(item.added_by)

    def test_product_protected_from_deletion_while_item_exists(self) -> None:
        Item.objects.create(household=self.household, product=self.product)

        with self.assertRaises(ProtectedError):
            self.product.delete()
