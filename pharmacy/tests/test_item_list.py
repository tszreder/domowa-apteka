"""Household scoping, resolved vs unresolved rendering, and the prefetch contract.

`assertNumQueries` pins the `select_related`/`prefetch_related` contract
described in the plan's "Critical Implementation Details": a regression to
N+1 must fail CI, not be noticed in production.
"""

from datetime import date, timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

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

    def test_combination_product_badge_shows_both_partners_and_singles_show_only_combo(
        self,
    ) -> None:
        para = Substance.objects.create(name='Paracetamol', name_key='paracetamol')
        pseudo = Substance.objects.create(name='Pseudoefedryna', name_key='pseudoefedryna')

        combo = make_product('30', name='ManualTest Combo')
        ProductSubstance.objects.create(
            product=combo, substance=para, source_field=SourceField.SUBSTANCE_ROW, source_order=0
        )
        ProductSubstance.objects.create(
            product=combo, substance=pseudo, source_field=SourceField.SUBSTANCE_ROW, source_order=1
        )
        Item.objects.create(household=self.household, product=combo)

        para_only = make_product('31', name='Apap Extra')
        ProductSubstance.objects.create(
            product=para_only, substance=para, source_field=SourceField.SUBSTANCE_ROW, source_order=0
        )
        Item.objects.create(household=self.household, product=para_only)

        pseudo_only = make_product('32', name='Sudafeed')
        ProductSubstance.objects.create(
            product=pseudo_only, substance=pseudo, source_field=SourceField.SUBSTANCE_ROW, source_order=0
        )
        Item.objects.create(household=self.household, product=pseudo_only)

        response = self.client.get(reverse('pharmacy:item_list'))
        content = response.content.decode()

        self.assertContains(response, 'class="partial-overlap-badge"', count=3)
        self.assertContains(response, 'Częściowo wspólne substancje z innymi lekami', count=3)
        self.assertIn('Paracetamol: Apap Extra', content)
        self.assertIn('Pseudoefedryna: Sudafeed', content)

    def test_adding_to_an_older_cluster_moves_it_above_a_newer_single(self) -> None:
        """Pins the plan's ordering rule: a cluster sits at its newest member's `added_at`.

        Deliberately an integration test rather than a `build_list_view` unit
        test. The guarantee has two halves and the builder owns only one: its
        docstring hands newest-first ordering to the caller, so a future
        `.order_by(...)` on the view's queryset (`pharmacy/views.py`) would
        break the rule with a green unit suite. Product names are chosen so
        alphabetical order differs from `added_at` order — otherwise an
        `.order_by('product__name')` regression would coincidentally pass.
        """
        substance_x = Substance.objects.create(name='Substancja X', name_key='substancja-x')
        substance_y = Substance.objects.create(name='Substancja Y', name_key='substancja-y')

        oldest_product = make_product('40', name='Apap Stary')
        ProductSubstance.objects.create(
            product=oldest_product,
            substance=substance_x,
            source_field=SourceField.SUBSTANCE_ROW,
            source_order=0,
        )
        single_product = make_product('41', name='Metformina Srednia')
        ProductSubstance.objects.create(
            product=single_product,
            substance=substance_y,
            source_field=SourceField.SUBSTANCE_ROW,
            source_order=0,
        )
        newest_product = make_product('42', name='Zamiennik Nowy')
        ProductSubstance.objects.create(
            product=newest_product,
            substance=substance_x,
            source_field=SourceField.SUBSTANCE_ROW,
            source_order=0,
        )

        oldest = Item.objects.create(household=self.household, product=oldest_product)
        middle = Item.objects.create(household=self.household, product=single_product)
        newest = Item.objects.create(household=self.household, product=newest_product)

        # `added_at` is `auto_now_add`, so all three land within one tick and
        # cannot be set on create. Write the intended spread explicitly, so
        # the assertions below test grouping rather than clock resolution.
        base = timezone.now() - timedelta(days=3)
        Item.objects.filter(pk=oldest.pk).update(added_at=base)
        Item.objects.filter(pk=middle.pk).update(added_at=base + timedelta(days=1))
        Item.objects.filter(pk=newest.pk).update(added_at=base + timedelta(days=2))

        response = self.client.get(reverse('pharmacy:item_list'))
        content = response.content.decode()

        self.assertContains(response, 'class="duplicate-cluster"', count=1)
        self.assertLess(
            content.index('duplicate-cluster'),
            content.index('Metformina Srednia'),
            'the cluster its newest member joined must render above the older single',
        )
        self.assertLess(
            content.index('Zamiennik Nowy'),
            content.index('Apap Stary'),
            'within a cluster, the newest member must render first',
        )

    def test_item_with_no_overlap_renders_no_badge(self) -> None:
        substance = Substance.objects.create(name='Ibuprofen', name_key='ibuprofen')
        product = make_product('33', name='Ibum')
        ProductSubstance.objects.create(
            product=product, substance=substance, source_field=SourceField.SUBSTANCE_ROW, source_order=0
        )
        Item.objects.create(household=self.household, product=product)

        response = self.client.get(reverse('pharmacy:item_list'))

        self.assertNotContains(response, 'partial-overlap-badge')

    def test_unresolved_item_renders_no_badge(self) -> None:
        product = make_product('34', name='Peditrace')
        Item.objects.create(household=self.household, product=product)

        response = self.client.get(reverse('pharmacy:item_list'))

        self.assertNotContains(response, 'partial-overlap-badge')

    def test_containment_renders_as_partial_not_full(self) -> None:
        para = Substance.objects.create(name='Paracetamol', name_key='paracetamol')
        pseudo = Substance.objects.create(name='Pseudoefedryna', name_key='pseudoefedryna')

        combo = make_product('35', name='ManualTest Combo')
        ProductSubstance.objects.create(
            product=combo, substance=para, source_field=SourceField.SUBSTANCE_ROW, source_order=0
        )
        ProductSubstance.objects.create(
            product=combo, substance=pseudo, source_field=SourceField.SUBSTANCE_ROW, source_order=1
        )
        Item.objects.create(household=self.household, product=combo)

        para_only = make_product('36', name='Apap Extra')
        ProductSubstance.objects.create(
            product=para_only, substance=para, source_field=SourceField.SUBSTANCE_ROW, source_order=0
        )
        Item.objects.create(household=self.household, product=para_only)

        response = self.client.get(reverse('pharmacy:item_list'))

        # containment is partial, not full: no shared cluster, but a badge
        self.assertNotContains(response, 'class="duplicate-cluster"')
        self.assertContains(response, 'class="partial-overlap-badge"', count=2)

    def test_badge_emitted_once_per_cluster_not_once_per_member(self) -> None:
        cluster_substance = Substance.objects.create(name='Paracetamol', name_key='paracetamol')
        shared = Substance.objects.create(name='Pseudoefedryna', name_key='pseudoefedryna')

        # A 3-member full-duplicate cluster (combo products carrying both
        # substances, cross-product) that also partially overlaps a fourth,
        # single-substance item.
        for i, rid in enumerate(('37', '38', '39')):
            product = make_product(rid, name=f'ComboBrand {rid}')
            ProductSubstance.objects.create(
                product=product,
                substance=cluster_substance,
                source_field=SourceField.SUBSTANCE_ROW,
                source_order=0,
            )
            ProductSubstance.objects.create(
                product=product,
                substance=shared,
                source_field=SourceField.SUBSTANCE_ROW,
                source_order=1,
            )
            Item.objects.create(household=self.household, product=product)

        pseudo_only = make_product('40', name='Sudafeed')
        ProductSubstance.objects.create(
            product=pseudo_only, substance=shared, source_field=SourceField.SUBSTANCE_ROW, source_order=0
        )
        Item.objects.create(household=self.household, product=pseudo_only)

        response = self.client.get(reverse('pharmacy:item_list'))

        # one badge for the 3-member cluster, one for the single — never 3.
        self.assertContains(response, 'class="partial-overlap-badge"', count=2)

    def test_n_plus_one_guard_holds_with_partial_overlap_items_present(self) -> None:
        para = Substance.objects.create(name='Paracetamol', name_key='paracetamol')
        pseudo = Substance.objects.create(name='Pseudoefedryna', name_key='pseudoefedryna')

        combo = make_product('41', name='ManualTest Combo')
        ProductSubstance.objects.create(
            product=combo, substance=para, source_field=SourceField.SUBSTANCE_ROW, source_order=0
        )
        ProductSubstance.objects.create(
            product=combo, substance=pseudo, source_field=SourceField.SUBSTANCE_ROW, source_order=1
        )
        Item.objects.create(household=self.household, product=combo)

        para_only = make_product('42', name='Apap Extra')
        ProductSubstance.objects.create(
            product=para_only, substance=para, source_field=SourceField.SUBSTANCE_ROW, source_order=0
        )
        Item.objects.create(household=self.household, product=para_only)

        with self.assertNumQueries(7):
            response = self.client.get(reverse('pharmacy:item_list'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="partial-overlap-badge"', count=2)

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
        # Only the unresolved section's list — the groups <ul> must not be
        # emitted empty, which Pico would render as a stray vertical gap.
        self.assertContains(response, 'class="item-list"', count=1)

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
