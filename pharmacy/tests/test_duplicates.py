"""Prove pharmacy.duplicates against sets read off fixture rows.

Every expected value here is derived from how the fixture was built, never
snapshotted from the function's current output — test-plan.md §2 risk #3
names that anti-pattern explicitly.
"""

from datetime import date

from django.test import SimpleTestCase, TestCase

from households.models import Household
from pharmacy.duplicates import ItemListView, Overlap, build_list_view, classify, substance_keys
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


def make_substance(name: str, name_key: str) -> Substance:
    return Substance.objects.create(name=name, name_key=name_key)


def link(product: Product, substance: Substance, order: int = 0, **overrides: object) -> ProductSubstance:
    defaults: dict[str, object] = {
        'product': product,
        'substance': substance,
        'source_field': SourceField.SUBSTANCE_ROW,
        'source_order': order,
    }
    defaults.update(overrides)
    return ProductSubstance.objects.create(**defaults)


class ClassifyTests(SimpleTestCase):
    """Pure-logic tests: no DB, no household, no request."""

    def test_identical_sets_are_full(self) -> None:
        self.assertEqual(
            classify(frozenset({'paracetamol'}), frozenset({'paracetamol'})),
            Overlap.FULL,
        )

    def test_disjoint_sets_are_none(self) -> None:
        self.assertEqual(
            classify(frozenset({'paracetamol'}), frozenset({'ibuprofen'})),
            Overlap.NONE,
        )

    def test_containment_overlap_is_partial(self) -> None:
        self.assertEqual(
            classify(frozenset({'paracetamol'}), frozenset({'paracetamol', 'pseudoefedryna'})),
            Overlap.PARTIAL,
        )

    def test_crossing_overlap_is_partial(self) -> None:
        self.assertEqual(
            classify(frozenset({'a', 'b'}), frozenset({'b', 'c'})),
            Overlap.PARTIAL,
        )

    def test_left_empty_is_none(self) -> None:
        self.assertEqual(classify(frozenset(), frozenset({'paracetamol'})), Overlap.NONE)

    def test_right_empty_is_none(self) -> None:
        self.assertEqual(classify(frozenset({'paracetamol'}), frozenset()), Overlap.NONE)

    def test_both_empty_is_none_not_full(self) -> None:
        # The primary correctness guard: frozenset() == frozenset() is True
        # in Python, so this case must be checked before the equality test,
        # not left to fall through to it.
        self.assertEqual(classify(frozenset(), frozenset()), Overlap.NONE)


class SubstanceKeysTests(TestCase):
    def test_repeated_pair_at_different_amounts_collapses_to_one_key(self) -> None:
        # ProductSubstance carries no unique constraint on (product,
        # substance): 89 real rows repeat a substance on the same product at
        # a different amount. The frozenset must collapse that, not treat
        # the product as carrying two identities.
        substance = make_substance('Paracetamol', 'paracetamol')
        repeated = make_product('1', name='Combo')
        link(repeated, substance, order=0, amount='250')
        link(repeated, substance, order=1, amount='500')
        single = make_product('2', name='Single')
        link(single, substance, order=0, amount='500')

        self.assertEqual(substance_keys(repeated), frozenset({'paracetamol'}))
        self.assertEqual(classify(substance_keys(repeated), substance_keys(single)), Overlap.FULL)

    def test_reads_name_key_not_display_name(self) -> None:
        # name and name_key deliberately differ, as they do in real rows
        # (name_key is a normalized identity, name is only a display form).
        # A comparison keyed on `.name` instead of `.name_key` would produce
        # a different set here and miss a real duplicate elsewhere.
        # `Substance.name_key` is unique at the DB level, so two rows can
        # never literally share a name_key with different names by the time
        # they reach this table — the parser's first-seen-wins merge
        # resolves that upstream (registry/models.py:28-34). What this test
        # can and does prove is that `substance_keys` reads the identity
        # column, not the display column.
        substance = make_substance('Paracetamolum', 'paracetamol')
        product = make_product('3', name='Apap')
        link(product, substance)

        self.assertEqual(substance_keys(product), frozenset({'paracetamol'}))

    def test_empty_when_product_has_no_links(self) -> None:
        product = make_product('4', name='Peditrace')

        self.assertEqual(substance_keys(product), frozenset())


class BuildListViewTests(TestCase):
    def setUp(self) -> None:
        self.household = Household.objects.create(name='Kowalscy')

    def make_item(self, product: Product, **overrides: object) -> Item:
        return Item.objects.create(household=self.household, product=product, **overrides)

    def _view(self) -> ItemListView:
        return build_list_view(
            Item.objects.filter(household=self.household)
            .select_related('product')
            .prefetch_related('product__substance_links__substance')
        )

    def test_two_unresolved_items_are_not_grouped_with_each_other(self) -> None:
        item_a = self.make_item(make_product('1', name='A'))
        item_b = self.make_item(make_product('2', name='B'))

        view = self._view()

        self.assertEqual(view.groups, [])
        self.assertCountEqual(view.unresolved, [item_a, item_b])

    def test_resolved_and_unresolved_are_never_grouped(self) -> None:
        substance = make_substance('Paracetamol', 'paracetamol')
        resolved_product = make_product('3', name='Apap')
        link(resolved_product, substance)
        resolved = self.make_item(resolved_product)
        unresolved = self.make_item(make_product('4', name='Peditrace'))

        view = self._view()

        self.assertEqual(len(view.groups), 1)
        self.assertEqual(view.groups[0].items, [resolved])
        self.assertEqual(view.unresolved, [unresolved])

    def test_same_product_cluster_is_labelled_distinctly_from_cross_product_cluster(self) -> None:
        substance_x = make_substance('Substancja X', 'substancja-x')
        product_a = make_product('5', name='Apap')
        link(product_a, substance_x)
        same_product_1 = self.make_item(product_a)
        self.make_item(product_a)

        substance_y = make_substance('Substancja Y', 'substancja-y')
        product_b = make_product('6', name='Panadol')
        link(product_b, substance_y)
        product_c = make_product('7', name='Codipar')
        link(product_c, substance_y)
        cross_product_1 = self.make_item(product_b)
        self.make_item(product_c)

        view = self._view()

        self.assertEqual(len(view.groups), 2)
        same_product_group = next(g for g in view.groups if same_product_1 in g.items)
        cross_product_group = next(g for g in view.groups if cross_product_1 in g.items)
        self.assertTrue(same_product_group.same_product)
        self.assertFalse(cross_product_group.same_product)

    def test_combination_product_lands_in_partner_lists_of_two_disjoint_items(self) -> None:
        para = make_substance('Paracetamol', 'paracetamol')
        pseudo = make_substance('Pseudoefedryna', 'pseudoefedryna')

        combo_product = make_product('8', name='Combo')
        link(combo_product, para, order=0)
        link(combo_product, pseudo, order=1)
        combo_item = self.make_item(combo_product)

        para_only_product = make_product('9', name='Apap')
        link(para_only_product, para)
        para_item = self.make_item(para_only_product)

        pseudo_only_product = make_product('10', name='Sudafed')
        link(pseudo_only_product, pseudo)
        pseudo_item = self.make_item(pseudo_only_product)

        view = self._view()

        combo_group = next(g for g in view.groups if combo_item in g.items)
        para_group = next(g for g in view.groups if para_item in g.items)
        pseudo_group = next(g for g in view.groups if pseudo_item in g.items)

        self.assertEqual(combo_group.partners.get('Paracetamol'), ['Apap'])
        self.assertEqual(combo_group.partners.get('Pseudoefedryna'), ['Sudafed'])
        self.assertEqual(para_group.partners.get('Paracetamol'), ['Combo'])
        self.assertEqual(pseudo_group.partners.get('Pseudoefedryna'), ['Combo'])
        # para_item and pseudo_item are mutually disjoint: neither appears
        # as the other's partner, only the combination product does.
        self.assertNotIn('Sudafed', para_group.partners.get('Paracetamol', []))
        self.assertNotIn('Apap', pseudo_group.partners.get('Pseudoefedryna', []))

    def test_shared_substances_are_ordered_alphabetically_not_by_set_iteration(self) -> None:
        """Pins badge order against per-process string-hash randomisation.

        `partners` is filled by iterating `key_a & key_b`, a `frozenset[str]`.
        Python randomises string hashing per process, so without an explicit
        sort two gunicorn workers render the same badge with its substances —
        and its `partner_names` — in different orders, and the text under an
        item changes as the user reloads. The links below are created in
        reverse alphabetical order so a pass cannot come from insertion order.
        """
        wit = make_substance('Witamina C', 'witamina-c')
        para = make_substance('Paracetamol', 'paracetamol')
        amox = make_substance('Amoksycylina', 'amoksycylina')
        ibu = make_substance('Ibuprofen', 'ibuprofen')

        broad_product = make_product('11', name='Szeroki')
        link(broad_product, wit, order=0)
        link(broad_product, para, order=1)
        link(broad_product, amox, order=2)
        link(broad_product, ibu, order=3)
        broad_item = self.make_item(broad_product)

        narrow_product = make_product('12', name='Wąski')
        link(narrow_product, wit, order=0)
        link(narrow_product, para, order=1)
        link(narrow_product, amox, order=2)
        narrow_item = self.make_item(narrow_product)

        view = self._view()
        broad_group = next(g for g in view.groups if broad_item in g.items)
        narrow_group = next(g for g in view.groups if narrow_item in g.items)

        self.assertEqual(
            list(broad_group.partners), ['Amoksycylina', 'Paracetamol', 'Witamina C']
        )
        self.assertEqual(
            list(narrow_group.partners), ['Amoksycylina', 'Paracetamol', 'Witamina C']
        )
