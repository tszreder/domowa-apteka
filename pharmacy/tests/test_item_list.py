"""Household scoping, resolved vs unresolved rendering, and the prefetch contract.

`assertNumQueries` pins the `select_related`/`prefetch_related` contract
described in the plan's "Critical Implementation Details": a regression to
N+1 must fail CI, not be noticed in production.
"""

from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

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


class ItemListScopingTests(TestCase):
    def setUp(self) -> None:
        self.household_a = Household.objects.create(name='Kowalscy')
        self.household_b = Household.objects.create(name='Nowakowie')
        self.member_a = User.objects.create_user(username='alice@example.com', password='pass12345')
        self.member_b = User.objects.create_user(username='bob@example.com', password='pass12345')
        Membership.objects.create(user=self.member_a, household=self.household_a)
        Membership.objects.create(user=self.member_b, household=self.household_b)
        self.product = make_product('1', name='Apap Extra')
        self.item_a = Item.objects.create(household=self.household_a, product=self.product)

    def test_item_in_household_a_never_appears_for_member_of_household_b(self) -> None:
        self.client.force_login(self.member_b)

        response = self.client.get(reverse('pharmacy:item_list'))

        self.assertNotContains(response, 'Apap Extra')

    def test_item_in_household_a_appears_for_member_of_household_a(self) -> None:
        self.client.force_login(self.member_a)

        response = self.client.get(reverse('pharmacy:item_list'))

        self.assertContains(response, 'Apap Extra')


class ItemListRenderingTests(TestCase):
    def setUp(self) -> None:
        self.household = Household.objects.create(name='Kowalscy')
        self.member = User.objects.create_user(username='alice@example.com', password='pass12345')
        Membership.objects.create(user=self.member, household=self.household)
        self.client.force_login(self.member)

    def test_resolved_item_shows_its_substance_names(self) -> None:
        product = make_product('1', name='Apap Extra')
        substance = Substance.objects.create(name='Paracetamol', name_key='paracetamol')
        ProductSubstance.objects.create(
            product=product,
            substance=substance,
            source_field=SourceField.SUBSTANCE_ROW,
            source_order=0,
        )
        Item.objects.create(household=self.household, product=product)

        response = self.client.get(reverse('pharmacy:item_list'))

        self.assertContains(response, 'Paracetamol')
        self.assertNotContains(response, 'unresolved')

    def test_unresolved_item_renders_distinctly(self) -> None:
        product = make_product('2', name='Peditrace')
        Item.objects.create(household=self.household, product=product)

        response = self.client.get(reverse('pharmacy:item_list'))

        self.assertContains(response, 'class="unresolved"')

    def test_producer_shown_only_when_confirmed(self) -> None:
        product = make_product('3', name='Concor Cor 2,5', marketing_holder='Merck')
        Item.objects.create(
            household=self.household, product=product, producer_confirmed=True
        )

        response = self.client.get(reverse('pharmacy:item_list'))

        self.assertContains(response, 'Merck')

    def test_producer_not_shown_when_not_confirmed(self) -> None:
        product = make_product('4', name='Concor Cor 2,5', marketing_holder='Merck')
        Item.objects.create(
            household=self.household, product=product, producer_confirmed=False
        )

        response = self.client.get(reverse('pharmacy:item_list'))

        self.assertNotContains(response, 'Merck')

    def test_list_view_does_not_n_plus_one_on_resolved_items(self) -> None:
        substance = Substance.objects.create(name='Paracetamol', name_key='paracetamol')
        for i in range(5):
            product = make_product(str(i), name=f'Product {i}')
            ProductSubstance.objects.create(
                product=product,
                substance=substance,
                source_field=SourceField.SUBSTANCE_ROW,
                source_order=0,
            )
            Item.objects.create(household=self.household, product=product)

        # 4 queries are request plumbing (session, user, membership,
        # household) that run regardless of item count; the other 3 are
        # items+product (select_related), substance_links, and substances
        # (prefetch_related) — each a single query no matter how many items,
        # which is the N+1 guard this test exists to pin.
        with self.assertNumQueries(7):
            response = self.client.get(reverse('pharmacy:item_list'))

        self.assertEqual(response.status_code, 200)
