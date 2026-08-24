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

    def test_identical_substances_on_different_products_render_as_zamienniki_cluster(
        self,
    ) -> None:
        substance = Substance.objects.create(name='Paracetamol', name_key='paracetamol')
        product_a = make_product('10', name='Apap Extra')
        product_b = make_product('11', name='Panadol')
        for product in (product_a, product_b):
            ProductSubstance.objects.create(
                product=product,
                substance=substance,
                source_field=SourceField.SUBSTANCE_ROW,
                source_order=0,
            )
        Item.objects.create(household=self.household, product=product_a)
        Item.objects.create(household=self.household, product=product_b)

        response = self.client.get(reverse('pharmacy:item_list'))

        self.assertContains(response, 'class="duplicate-cluster"')
        self.assertContains(response, 'Zamienniki')
        self.assertNotContains(response, 'Ten sam produkt')

    def test_same_product_repeated_renders_as_same_product_cluster_not_zamienniki(
        self,
    ) -> None:
        substance = Substance.objects.create(name='Paracetamol', name_key='paracetamol')
        product = make_product('12', name='Apap Extra')
        ProductSubstance.objects.create(
            product=product,
            substance=substance,
            source_field=SourceField.SUBSTANCE_ROW,
            source_order=0,
        )
        Item.objects.create(household=self.household, product=product)
        Item.objects.create(household=self.household, product=product)

        response = self.client.get(reverse('pharmacy:item_list'))

        self.assertContains(response, 'class="duplicate-cluster"')
        self.assertContains(response, 'Ten sam produkt')
        self.assertNotContains(response, 'Zamienniki')

    def test_disjoint_substances_render_as_singles_in_no_cluster(self) -> None:
        substance_a = Substance.objects.create(name='Paracetamol', name_key='paracetamol')
        substance_b = Substance.objects.create(name='Ibuprofen', name_key='ibuprofen')
        product_a = make_product('13', name='Apap Extra')
        ProductSubstance.objects.create(
            product=product_a,
            substance=substance_a,
            source_field=SourceField.SUBSTANCE_ROW,
            source_order=0,
        )
        product_b = make_product('14', name='Ibum')
        ProductSubstance.objects.create(
            product=product_b,
            substance=substance_b,
            source_field=SourceField.SUBSTANCE_ROW,
            source_order=0,
        )
        Item.objects.create(household=self.household, product=product_a)
        Item.objects.create(household=self.household, product=product_b)

        response = self.client.get(reverse('pharmacy:item_list'))

        self.assertNotContains(response, 'class="duplicate-cluster"')
        self.assertContains(response, 'Apap Extra')
        self.assertContains(response, 'Ibum')

    def test_two_unresolved_items_are_not_grouped_and_appear_in_unresolved_section(
        self,
    ) -> None:
        product_a = make_product('15', name='Peditrace')
        product_b = make_product('16', name='Nifedypina')
        Item.objects.create(household=self.household, product=product_a)
        Item.objects.create(household=self.household, product=product_b)

        response = self.client.get(reverse('pharmacy:item_list'))

        self.assertContains(response, 'class="unresolved-section"')
        self.assertNotContains(response, 'class="duplicate-cluster"')
        self.assertContains(response, 'Peditrace')
        self.assertContains(response, 'Nifedypina')

    def test_unresolved_item_and_resolved_item_are_never_grouped(self) -> None:
        substance = Substance.objects.create(name='Paracetamol', name_key='paracetamol')
        resolved_product = make_product('17', name='Apap Extra')
        ProductSubstance.objects.create(
            product=resolved_product,
            substance=substance,
            source_field=SourceField.SUBSTANCE_ROW,
            source_order=0,
        )
        unresolved_product = make_product('18', name='Peditrace')
        Item.objects.create(household=self.household, product=resolved_product)
        Item.objects.create(household=self.household, product=unresolved_product)

        response = self.client.get(reverse('pharmacy:item_list'))

        self.assertNotContains(response, 'class="duplicate-cluster"')
        self.assertContains(response, 'class="unresolved-section"')

    def test_n_plus_one_guard_holds_with_cluster_single_and_unresolved_present(
        self,
    ) -> None:
        substance = Substance.objects.create(name='Paracetamol', name_key='paracetamol')

        cluster_product_a = make_product('19', name='Apap Extra')
        cluster_product_b = make_product('20', name='Panadol')
        for product in (cluster_product_a, cluster_product_b):
            ProductSubstance.objects.create(
                product=product,
                substance=substance,
                source_field=SourceField.SUBSTANCE_ROW,
                source_order=0,
            )
            Item.objects.create(household=self.household, product=product)

        single_substance = Substance.objects.create(name='Ibuprofen', name_key='ibuprofen')
        single_product = make_product('21', name='Ibum')
        ProductSubstance.objects.create(
            product=single_product,
            substance=single_substance,
            source_field=SourceField.SUBSTANCE_ROW,
            source_order=0,
        )
        Item.objects.create(household=self.household, product=single_product)

        unresolved_product = make_product('22', name='Peditrace')
        Item.objects.create(household=self.household, product=unresolved_product)

        with self.assertNumQueries(7):
            response = self.client.get(reverse('pharmacy:item_list'))

        self.assertEqual(response.status_code, 200)
