"""Prove pharmacy.duplicates against sets read off fixture rows.

Every expected value here is derived from how the fixture was built, never
snapshotted from the function's current output — test-plan.md §2 risk #3
names that anti-pattern explicitly.
"""

from collections.abc import Iterable
from datetime import date, timedelta

from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from households.models import Household
from pharmacy.duplicates import (
    CandidateCheck,
    ItemListView,
    ItemStack,
    MatchKind,
    Overlap,
    build_list_view,
    check_candidate,
    classify,
    substance_keys,
)
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


class CheckCandidateTests(TestCase):
    """One candidate product against a whole household.

    Every expectation below is read off how the fixture was built — which
    substances were linked to which product, and which product each box points
    at — never off what `check_candidate` happens to return today.
    """

    def setUp(self) -> None:
        self.household = Household.objects.create(name='Kowalscy')

    def make_item(self, product: Product, **overrides: object) -> Item:
        return Item.objects.create(household=self.household, product=product, **overrides)

    def _check(self, candidate: Product, items: Iterable[Item] | None = None) -> CandidateCheck:
        """Run the check the way the view will: both sides prefetched.

        `items` defaults to the household's own queryset in `Item.Meta.ordering`;
        pass an explicit list only where the test needs to control input order.
        """
        if items is None:
            items = (
                Item.objects.filter(household=self.household)
                .select_related('product')
                .prefetch_related('product__substance_links__substance')
            )
        return check_candidate(
            Product.objects.prefetch_related('substance_links__substance').get(pk=candidate.pk),
            items,
        )

    def test_unresolved_candidate_not_held_refuses_instead_of_reporting_no_match(self) -> None:
        """The candidate side of the silent-guess trap.

        A candidate with no substance links classifies as NONE against
        everything, so a naive screen would report "nothing at home matches" —
        a buy signal for a product we merely failed to resolve. `resolved` is
        what lets the caller tell the two apart. The household deliberately
        holds a product with a near-identical name and a different key: a name
        collision is not identity, and must not become one.
        """
        para = make_substance('Paracetamol', 'paracetamol')
        lookalike = make_product('1', name='Apap Extra')
        link(lookalike, para)
        self.make_item(lookalike)
        candidate = make_product('2', name='Apap')

        result = self._check(candidate)

        self.assertFalse(result.resolved)
        self.assertEqual(result.candidate_substances, [])
        self.assertEqual(result.matches, [])

    def test_unresolved_candidate_the_household_holds_is_still_confirmed_by_identity(self) -> None:
        """Pins identity as independent of resolution.

        This is the test that keeps `check_candidate` from over-refusing.
        Falsify it by gating the `product_id == candidate.pk` branch on a
        non-empty key set — the way a "we could not resolve it, so we cannot
        answer" reading of the rule would — and it goes red, because the
        household's own boxes disappear from an answer that never needed
        substances to be certain.
        """
        candidate = make_product('1', name='Peditrace')
        self.make_item(candidate)
        self.make_item(candidate)

        result = self._check(candidate)

        self.assertFalse(result.resolved)
        self.assertEqual([match.kind for match in result.matches], [MatchKind.SAME_PRODUCT])
        self.assertEqual(result.matches[0].pack_count, 2)

    def test_household_owning_the_identical_product_is_same_product_with_empty_shared(self) -> None:
        para = make_substance('Paracetamol', 'paracetamol')
        candidate = make_product('1', name='Apap')
        link(candidate, para)
        self.make_item(candidate)

        result = self._check(candidate)

        self.assertTrue(result.resolved)
        self.assertEqual([match.kind for match in result.matches], [MatchKind.SAME_PRODUCT])
        # Identical by definition, so there is nothing to name.
        self.assertEqual(result.matches[0].shared, [])

    def test_different_product_with_the_same_set_is_same_substances_not_same_product(self) -> None:
        # The split `MatchKind` exists for exactly this pair: both are FULL to
        # `classify`, and they are different facts to someone at the pharmacy.
        para = make_substance('Paracetamol', 'paracetamol')
        candidate = make_product('1', name='Apap')
        link(candidate, para)
        substitute = make_product('2', name='Paracetamol Hasco')
        link(substitute, para)
        self.make_item(substitute)

        result = self._check(candidate)

        self.assertEqual(len(result.matches), 1)
        match = result.matches[0]
        self.assertEqual(match.kind, MatchKind.SAME_SUBSTANCES)
        self.assertFalse(match.is_same_product)
        self.assertEqual(match.product.pk, substitute.pk)
        self.assertEqual(match.shared, [])

    def test_combination_candidate_shares_exactly_the_intersection(self) -> None:
        para = make_substance('Paracetamol', 'paracetamol')
        pseudo = make_substance('Pseudoefedryna', 'pseudoefedryna')
        candidate = make_product('1', name='Combo')
        link(candidate, para, order=0)
        link(candidate, pseudo, order=1)
        para_only = make_product('2', name='Apap')
        link(para_only, para)
        self.make_item(para_only)

        result = self._check(candidate)

        self.assertEqual([match.kind for match in result.matches], [MatchKind.SHARED_SUBSTANCE])
        # Pseudoefedryna is on the candidate only, so it is not shared.
        self.assertEqual(result.matches[0].shared, ['Paracetamol'])
        self.assertEqual(result.candidate_substances, ['Paracetamol', 'Pseudoefedryna'])

    def test_disjoint_household_item_produces_no_match(self) -> None:
        para = make_substance('Paracetamol', 'paracetamol')
        ibu = make_substance('Ibuprofen', 'ibuprofen')
        candidate = make_product('1', name='Apap')
        link(candidate, para)
        unrelated = make_product('2', name='Ibuprom')
        link(unrelated, ibu)
        self.make_item(unrelated)

        result = self._check(candidate)

        self.assertTrue(result.resolved)
        self.assertEqual(result.matches, [])
        # Resolved, just disjoint — nothing was skipped, so nothing to disclose.
        self.assertEqual(result.uncomparable_count, 0)

    def test_unresolved_household_items_are_counted_and_never_matched(self) -> None:
        """The household side of the silent-guess trap.

        Items whose own products never resolved classify as NONE against
        everything and so vanish from `matches`. Without the count travelling
        alongside, a "nothing at home matches" verdict would be computed over a
        household the comparison only partly saw.
        """
        para = make_substance('Paracetamol', 'paracetamol')
        candidate = make_product('1', name='Apap')
        link(candidate, para)
        substitute = make_product('2', name='Paracetamol Hasco')
        link(substitute, para)
        self.make_item(substitute)
        self.make_item(make_product('3', name='Peditrace'))
        self.make_item(make_product('4', name='Nutriflex'))

        result = self._check(candidate)

        self.assertEqual([match.kind for match in result.matches], [MatchKind.SAME_SUBSTANCES])
        self.assertEqual(result.uncomparable_count, 2)

    def test_the_candidates_own_unresolved_box_is_matched_by_identity_and_still_counted(self) -> None:
        """`uncomparable_count` is computed the same way whether or not the candidate resolved.

        The candidate's own box matched on identity, not on substances, so it
        genuinely took no part in a substance comparison and belongs in the
        count. The screen — not this function — decides that the count is not
        worth showing when `resolved` is false, because the refusal message
        already says no comparison ran.
        """
        candidate = make_product('1', name='Peditrace')
        self.make_item(candidate)
        self.make_item(make_product('2', name='Nutriflex'))

        result = self._check(candidate)

        self.assertFalse(result.resolved)
        self.assertEqual([match.kind for match in result.matches], [MatchKind.SAME_PRODUCT])
        self.assertEqual(result.uncomparable_count, 2)

    def test_three_boxes_of_one_product_collapse_to_one_match(self) -> None:
        para = make_substance('Paracetamol', 'paracetamol')
        candidate = make_product('1', name='Apap')
        link(candidate, para)
        substitute = make_product('2', name='Paracetamol Hasco')
        link(substitute, para)
        for _ in range(3):
            self.make_item(substitute)

        result = self._check(candidate)

        self.assertEqual(len(result.matches), 1)
        # One Item is one physical box, so pack_count has no second source.
        self.assertEqual(result.matches[0].pack_count, 3)
        self.assertEqual(len(result.matches[0].items), 3)

    def test_matches_are_ordered_strongest_first(self) -> None:
        """Ordering comes from the tier, not from the order items arrive in.

        `items` is handed over in deliberately reversed tier order, so a pass
        cannot come from the caller's ordering surviving untouched.
        """
        para = make_substance('Paracetamol', 'paracetamol')
        pseudo = make_substance('Pseudoefedryna', 'pseudoefedryna')

        candidate = make_product('1', name='Combo')
        link(candidate, para, order=0)
        link(candidate, pseudo, order=1)
        same_set = make_product('2', name='Combo Hasco')
        link(same_set, para, order=0)
        link(same_set, pseudo, order=1)
        para_only = make_product('3', name='Apap')
        link(para_only, para)

        shared_item = self.make_item(para_only)
        same_substances_item = self.make_item(same_set)
        same_product_item = self.make_item(candidate)

        result = self._check(
            candidate,
            items=[shared_item, same_substances_item, same_product_item],
        )

        self.assertEqual(
            [match.kind for match in result.matches],
            [MatchKind.SAME_PRODUCT, MatchKind.SAME_SUBSTANCES, MatchKind.SHARED_SUBSTANCE],
        )

    def test_within_tier_order_is_newest_first(self) -> None:
        """`Item.Meta.ordering` (`-added_at`) survives the tier sort for free.

        This module's Critical Implementation Details documents that the tier
        sort is stable, so newest-first survives inside each tier — the same
        property `build_list_view` relies on. `test_matches_are_ordered_strongest_first`
        does not pin this: it places one match per tier, so it only proves tier
        boundaries. Replacing the sort key with
        `(_MATCH_ORDER.index(match.kind), match.product.name)` would destroy
        the documented stability and still pass that test.
        """
        para = make_substance('Paracetamol', 'paracetamol')
        pseudo = make_substance('Pseudoefedryna', 'pseudoefedryna')

        candidate = make_product('1', name='Combo')
        link(candidate, para, order=0)
        link(candidate, pseudo, order=1)
        older_match = make_product('2', name='Apap')
        link(older_match, para)
        newer_match = make_product('3', name='Sudafed')
        link(newer_match, pseudo)

        older_item = self.make_item(older_match)
        newer_item = self.make_item(newer_match)
        # `added_at` is `auto_now_add`, so both land within one tick and
        # cannot be spread on create. Write the intended spread explicitly,
        # the way `test_item_list.py` does for the same reason.
        base = timezone.now() - timedelta(days=1)
        Item.objects.filter(pk=older_item.pk).update(added_at=base)
        Item.objects.filter(pk=newer_item.pk).update(added_at=base + timedelta(hours=1))

        result = self._check(candidate)

        self.assertEqual(
            [match.kind for match in result.matches],
            [MatchKind.SHARED_SUBSTANCE, MatchKind.SHARED_SUBSTANCE],
        )
        self.assertEqual(
            [match.product.pk for match in result.matches],
            [newer_match.pk, older_match.pk],
        )

    def test_shared_substances_are_ordered_alphabetically_not_by_set_iteration(self) -> None:
        """Pins `shared` and `candidate_substances` against per-process hash randomisation.

        Both are built from `frozenset[str]` contents, and Python randomises
        string hashing per process, so without an explicit sort two gunicorn
        workers would name the same match's shared substances in different
        orders. The links are created in reverse alphabetical order so a pass
        cannot come from insertion order.
        """
        wit = make_substance('Witamina C', 'witamina-c')
        para = make_substance('Paracetamol', 'paracetamol')
        amox = make_substance('Amoksycylina', 'amoksycylina')
        ibu = make_substance('Ibuprofen', 'ibuprofen')

        candidate = make_product('1', name='Szeroki')
        link(candidate, wit, order=0)
        link(candidate, para, order=1)
        link(candidate, amox, order=2)
        link(candidate, ibu, order=3)

        narrow = make_product('2', name='Wąski')
        link(narrow, wit, order=0)
        link(narrow, para, order=1)
        link(narrow, amox, order=2)
        self.make_item(narrow)

        result = self._check(candidate)

        self.assertEqual([match.kind for match in result.matches], [MatchKind.SHARED_SUBSTANCE])
        self.assertEqual(result.matches[0].shared, ['Amoksycylina', 'Paracetamol', 'Witamina C'])
        self.assertEqual(
            result.candidate_substances,
            ['Amoksycylina', 'Ibuprofen', 'Paracetamol', 'Witamina C'],
        )


class ItemStackTests(TestCase):
    def setUp(self) -> None:
        self.household = Household.objects.create(name='Kowalscy')

    def make_item(self, product: Product, **overrides: object) -> Item:
        return Item.objects.create(household=self.household, product=product, **overrides)

    def test_stacks_aggregate_identical_products(self) -> None:
        substance = make_substance('Paracetamol', 'paracetamol')
        product = make_product('1', name='Apap')
        link(product, substance)
        self.make_item(product)
        self.make_item(product)
        self.make_item(product)

        view = build_list_view(
            Item.objects.filter(household=self.household)
            .select_related('product')
            .prefetch_related('product__substance_links__substance')
        )

        self.assertEqual(len(view.groups), 1)
        stacks = view.groups[0].stacks
        self.assertEqual(len(stacks), 1)
        self.assertEqual(stacks[0].count, 3)
        self.assertIsInstance(stacks[0], ItemStack)

    def test_stacks_separate_different_products_with_same_substances(self) -> None:
        substance = make_substance('Paracetamol', 'paracetamol')
        product_a = make_product('1', name='Apap')
        link(product_a, substance)
        product_b = make_product('2', name='Panadol')
        link(product_b, substance)
        self.make_item(product_a)
        self.make_item(product_b)

        view = build_list_view(
            Item.objects.filter(household=self.household)
            .select_related('product')
            .prefetch_related('product__substance_links__substance')
        )

        self.assertEqual(len(view.groups), 1)
        stacks = view.groups[0].stacks
        self.assertEqual(len(stacks), 2)
        self.assertEqual(stacks[0].count, 1)
        self.assertEqual(stacks[1].count, 1)
