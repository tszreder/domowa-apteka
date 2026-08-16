"""Pin the grouping and default-product tiebreak rules.

Fixtures are hand-built to reproduce the shapes measured against the real
data during planning (see plan.md "Key Discoveries") — not the real
snapshot, matching F-01's offline-CI convention.
"""

from datetime import date

from django.test import TestCase

from registry.models import Product, ProductSubstance, SourceField, Substance
from registry.suggestions import search_presentations

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


def link(product: Product, substance: Substance, order: int = 0) -> ProductSubstance:
    return ProductSubstance.objects.create(
        product=product,
        substance=substance,
        source_field=SourceField.SUBSTANCE_ROW,
        source_order=order,
    )


class GroupingTests(TestCase):
    def test_rows_sharing_name_strength_form_collapse_to_one_presentation_with_n_producers(
        self,
    ) -> None:
        # The `Concor Cor 2,5` shape: 28 rows across 8 distinct holders.
        for i, holder in enumerate(['Merck', 'Zentiva', 'Actavis'], start=1):
            make_product(
                str(i), name='Concor Cor 2,5', strength='2,5 mg',
                pharmaceutical_form='Tabletki', marketing_holder=holder,
            )

        results = search_presentations('concor')

        self.assertEqual(len(results), 1)
        self.assertEqual(len(results[0].producers), 3)
        self.assertEqual(
            [p.holder for p in results[0].producers], ['Actavis', 'Merck', 'Zentiva']
        )

    def test_rows_sharing_a_holder_collapse_to_one_producer(self) -> None:
        # The real `Concor Cor 2,5` shape: 28 rows, only 8 distinct holders.
        # One producer per row would offer 28 options the user cannot tell
        # apart — the flaw grouping exists to remove, one level down. Worse,
        # identical-looking options carry different `product_id`s, so a
        # distinction the user cannot see becomes a substance set they did
        # not knowingly choose.
        holders = ['Delfarma', 'Merck', 'Zentiva', 'Actavis']
        for i in range(28):
            make_product(
                str(i), name='Concor Cor 2,5', strength='2,5 mg',
                pharmaceutical_form='Tabletki', marketing_holder=holders[i % len(holders)],
            )

        results = search_presentations('concor')

        self.assertEqual(len(results), 1)
        self.assertEqual(
            [p.holder for p in results[0].producers],
            ['Actavis', 'Delfarma', 'Merck', 'Zentiva'],
        )

    def test_producer_representative_row_uses_the_default_product_tiebreak(self) -> None:
        # Which of a holder's rows is offered is not arbitrary: it reuses
        # `_default_product`, so the picked row prefers one carrying substance
        # links. One tiebreak rule in the module, not two.
        substance = Substance.objects.create(name='Bisoprololum', name_key='bisoprololum')
        without_links = make_product(
            '1', name='Concor Cor 2,5', marketing_holder='Delfarma',
        )
        with_links = make_product(
            '2', name='Concor Cor 2,5', marketing_holder='Delfarma',
        )
        link(with_links, substance)

        results = search_presentations('concor')

        self.assertEqual(len(results[0].producers), 1)
        self.assertEqual(results[0].producers[0].product_id, with_links.id)
        self.assertNotEqual(results[0].producers[0].product_id, without_links.id)

    def test_same_name_different_strengths_are_separate_presentations(self) -> None:
        # The `Xanax` shape.
        make_product('1', name='Xanax', strength='0,25 mg')
        make_product('2', name='Xanax', strength='1 mg')

        results = search_presentations('xanax')

        self.assertEqual(len(results), 2)
        self.assertEqual({r.strength for r in results}, {'0,25 mg', '1 mg'})

    def test_inactive_products_are_excluded(self) -> None:
        make_product('1', name='Withdrawn Drug', is_active=False)

        results = search_presentations('withdrawn')

        self.assertEqual(results, [])

    def test_icontains_matches_mid_string_case_insensitively(self) -> None:
        make_product('1', name='Concor Cor 2,5')

        results = search_presentations('COR')

        self.assertEqual(len(results), 1)

    def test_limit_is_respected(self) -> None:
        for i in range(15):
            make_product(str(i), name=f'Apap {i}')

        results = search_presentations('apap', limit=10)

        self.assertEqual(len(results), 10)

    def test_query_shorter_than_two_chars_returns_no_results(self) -> None:
        make_product('1', name='Apap')

        self.assertEqual(search_presentations('a'), [])


class DefaultProductTiebreakTests(TestCase):
    def test_default_is_the_row_with_links_when_another_row_has_none(self) -> None:
        # The `Peditrace` / `Moviprep` shape: one importer's row carries no links.
        substance = Substance.objects.create(name='Cynku chlorek', name_key='cynku_chlorek')
        with_links = make_product('2', name='Peditrace', marketing_holder='Fresenius')
        link(with_links, substance)
        make_product('1', name='Peditrace', marketing_holder='OtherCo')

        results = search_presentations('peditrace')

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].default_product_id, with_links.id)
        self.assertEqual(results[0].substances, ['Cynku chlorek'])

    def test_default_is_lowest_registry_id_when_rows_disagree_on_substances(self) -> None:
        # The `Sortis 20` salt-variant shape: both rows have links but disagree.
        # This is one of two defensible answers — chosen for determinism, not
        # asserted to be medically "correct". See plan.md "Accepted limitations".
        atorvastatinum = Substance.objects.create(name='Atorvastatinum', name_key='atorvastatinum')
        atorvastatinum_calcicum = Substance.objects.create(
            name='Atorvastatinum calcicum', name_key='atorvastatinum_calcicum'
        )
        higher = make_product('200', name='Sortis 20')
        link(higher, atorvastatinum_calcicum)
        lower = make_product('100', name='Sortis 20')
        link(lower, atorvastatinum)

        results = search_presentations('sortis')

        self.assertEqual(results[0].default_product_id, lower.id)
        self.assertEqual(results[0].substances, ['Atorvastatinum'])

    def test_group_with_no_links_anywhere_returns_empty_substance_list(self) -> None:
        # The 428-group shape: a valid pick that still resolves to nothing.
        make_product('1', name='Unresolvable Drug')

        results = search_presentations('unresolvable')

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].substances, [])
