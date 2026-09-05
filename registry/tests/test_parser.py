"""Pin every measured edge case in the fixture, so breaking one fails CI.

Expectations here are the ones documented in `fixtures/README.md`; that file and
this one must move together.
"""

import tempfile
from datetime import date
from pathlib import Path

from django.test import TestCase

from registry.denylist import DENYLISTED_SUBSTANCE_KEYS
from registry.models import SourceField
from registry.parser import (
    ParseResult,
    ProductRecord,
    RegistryParseError,
    namespace_for_url,
    parse_registry,
)

FIXTURE = Path(__file__).parent / 'fixtures' / 'sample-products.xml'
# The fixture's own declared namespace, spelled out rather than derived: a test
# that asked namespace_for_url() for it could not fail when both are wrong.
NAMESPACE = 'http://rejestry.ezdrowie.gov.pl/rpl/eksport-danych-v6.0.0'
NAMESPACE_7 = 'http://rejestry.ezdrowie.gov.pl/rpl/eksport-danych-v7.0.0'


class ParserTestCase(TestCase):
    """Parses the fixture once; every subclass reads the same result."""

    result: ParseResult

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.result = parse_registry(FIXTURE, NAMESPACE)

    def product(self, name: str) -> ProductRecord:
        matches = [product for product in self.result.products if product.name == name]
        self.assertEqual(len(matches), 1, f'expected exactly one {name!r}')
        return matches[0]


class ProductParsingTests(ParserTestCase):
    def test_source_as_of_read_from_root(self) -> None:
        self.assertEqual(self.result.source_as_of, date(2026, 8, 7))

    def test_counts_match_the_documented_fixture(self) -> None:
        self.assertEqual(self.result.products_in_file, 14)
        self.assertEqual(len(self.result.products), 12)
        self.assertEqual(self.result.substance_row_links, 50)
        self.assertEqual(self.result.common_name_links, 1)
        self.assertEqual(self.result.products_without_links, 2)
        self.assertEqual(len(self.result.substances), 37)

    def test_single_substance_product_keeps_amount_and_unit_verbatim(self) -> None:
        (link,) = self.product('Nalgesin').links

        self.assertEqual(link.name, 'Naproxenum natricum')
        self.assertEqual(link.amount, '275')
        self.assertEqual(link.unit, 'mg')
        self.assertEqual(link.source_field, SourceField.SUBSTANCE_ROW)

    def test_repeated_substance_on_one_product_keeps_both_rows(self) -> None:
        # The non-uniqueness guard: 89 rows across the real export repeat a
        # substance on the same product at a different amount.
        links = self.product('Altacet').links

        self.assertEqual([link.name for link in links], ['Aluminii acetotartras'] * 2)
        self.assertEqual([link.amount for link in links], ['1000', '100'])
        self.assertEqual([link.source_order for link in links], [0, 1])

    def test_wide_product_keeps_every_substance_row(self) -> None:
        self.assertEqual(len(self.product('Vaminolact').links), 19)

    def test_free_text_amount_kept_as_text_with_decimal_comma(self) -> None:
        links = self.product('Peditrace').links
        first = links[0]

        self.assertEqual(len(links), 7)
        # Repeated at a different amount, six rows apart.
        self.assertEqual([link.name for link in links].count('Zinci chloridum'), 2)
        self.assertEqual(first.name, 'Zinci chloridum')
        self.assertEqual(first.amount_description, '521,00 mcg')
        self.assertEqual(first.amount, '')
        self.assertEqual(first.unit, '')

    def test_veterinary_products_are_absent(self) -> None:
        names = [product.name for product in self.result.products]

        self.assertNotIn('Parvoerysin', names)
        self.assertNotIn('ZmienićDIVENCE', names)

    def test_parallel_import_leaflet_attributes_are_read(self) -> None:
        # typProcedury="IR" products carry the leaflet under a different
        # attribute name; a plain elem.get('ulotka') returns None for all of them.
        product = self.product('Beto 200 ZK')

        self.assertTrue(product.leaflet_url.endswith('/parallel-import-files/LEAFLET/public'))
        self.assertTrue(
            product.characteristics_url.endswith('/parallel-import-files/PACKAGE_MARKING/public')
        )


class CommonNameFallbackTests(ParserTestCase):
    def test_fallback_resolves_against_a_later_product(self) -> None:
        # Beto 200 ZK has no substance row of its own. The row that validates
        # its common name sits on Beto 25 ZK, *after* it in the file — which is
        # why the fallback cannot be decided while streaming forward.
        names = [product.name for product in self.result.products]
        self.assertLess(names.index('Beto 200 ZK'), names.index('Beto 25 ZK'))

        (link,) = self.product('Beto 200 ZK').links

        self.assertEqual(link.name, 'Metoprololi succinas')
        self.assertEqual(link.source_field, SourceField.COMMON_NAME)
        self.assertEqual(link.source_order, 0)
        self.assertEqual(link.amount, '')

    def test_explicit_row_is_never_tagged_as_inferred(self) -> None:
        (link,) = self.product('Beto 25 ZK').links

        self.assertEqual(link.name, 'Metoprololi succinas')
        self.assertEqual(link.source_field, SourceField.SUBSTANCE_ROW)
        self.assertEqual(link.amount, '23,75')

    def test_vocabulary_spans_the_whole_file_but_substances_do_not(self) -> None:
        # Veterinary substance names widen the set of strings the fallback will
        # accept, without admitting any veterinary product or substance row.
        names = [name for name, _ in self.result.substances]

        self.assertNotIn('Inaktywowany szczep 2-5 Erysipelothrix rhusiopathiae, serotyp 2a', names)


class WholeFileVocabularyTests(TestCase):
    """The vocabulary is accumulated before the human-use filter runs.

    The fixture cannot prove this on its own — none of its human products fall
    back onto a name that only a veterinary product states — and the rule is
    invisible until it regresses: moving the accumulation inside the filter
    would silently narrow what the fallback accepts, lowering resolution
    quality with every test still green. Written inline rather than added to
    the fixture, so the fixture's documented contract stays as it is.
    """

    def test_veterinary_substance_name_can_validate_a_human_fallback(self) -> None:
        xml = f"""<?xml version='1.0' encoding='utf-8'?>
<produktyLecznicze xmlns="{NAMESPACE}" stanNaDzien="2026-08-07">
    <produktLeczniczy nazwaProduktu="Tylan" rodzajPreparatu="weterynaryjny" nazwaPowszechnieStosowana="" id="900000001">
        <substancjeCzynne>
            <substancjaCzynna nazwaSubstancji="Tylosinum" iloscSubstancji="100" jednostkaMiaryIlosciSubstancji="mg" iloscPreparatu="" jednostkaMiaryIlosciPreparatu="" innyOpisIlosci="" />
        </substancjeCzynne>
    </produktLeczniczy>
    <produktLeczniczy nazwaProduktu="Tylozyna ludzka" rodzajPreparatu="ludzki" nazwaPowszechnieStosowana="Tylosinum" id="900000002">
        <substancjeCzynne />
    </produktLeczniczy>
</produktyLecznicze>
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'vocabulary-across-kinds.xml'
            path.write_text(xml, encoding='utf-8')
            result = parse_registry(path, NAMESPACE)

        (product,) = result.products
        (link,) = product.links

        self.assertEqual(product.name, 'Tylozyna ludzka')
        self.assertEqual(link.name, 'Tylosinum')
        self.assertEqual(link.source_field, SourceField.COMMON_NAME)
        # And a name reaching the data only through a fallback still lands in
        # the emitted vocabulary, because a link now references it.
        self.assertEqual(result.substances, (('Tylosinum', 'tylosinum'),))


class DroppedRowNumberingTests(TestCase):
    """`source_order` counts emitted links, not source elements.

    The fixture cannot prove this: its only denylisted-row product ends with
    zero links, so no product mixes a dropped row with kept ones. Without this
    test, `enumerate(kept)` can be rewritten to number source positions —
    reintroducing exactly the hole `SubstanceLinkRecord.source_order`'s comment
    forbids — with every other test still green. Inline rather than in the
    fixture, so the fixture's documented contract stays as it is.
    """

    def parse_inline(self, rows: str, name: str) -> tuple:
        xml = f"""<?xml version='1.0' encoding='utf-8'?>
<produktyLecznicze xmlns="{NAMESPACE}" stanNaDzien="2026-08-07">
    <produktLeczniczy nazwaProduktu="Testowy" rodzajPreparatu="ludzki" nazwaPowszechnieStosowana="" id="900000010">
        <substancjeCzynne>
{rows}
        </substancjeCzynne>
    </produktLeczniczy>
</produktyLecznicze>
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / name
            path.write_text(xml, encoding='utf-8')
            result = parse_registry(path, NAMESPACE)

        (product,) = result.products
        return product.links

    def row(self, name: str) -> str:
        return (
            f'            <substancjaCzynna nazwaSubstancji="{name}" iloscSubstancji="1" '
            'jednostkaMiaryIlosciSubstancji="mg" iloscPreparatu="" '
            'jednostkaMiaryIlosciPreparatu="" innyOpisIlosci="" />'
        )

    def test_a_denylisted_row_between_two_kept_rows_closes_the_gap(self) -> None:
        links = self.parse_inline(
            '\n'.join(
                [self.row('Acidum ascorbicum'), self.row('Produkt złożony'), self.row('Thiaminum')]
            ),
            'denylisted-in-the-middle.xml',
        )

        self.assertEqual([link.name for link in links], ['Acidum ascorbicum', 'Thiaminum'])
        # 1, not 2: the dropped row leaves no hole.
        self.assertEqual([link.source_order for link in links], [0, 1])

    def test_a_blank_substance_name_is_skipped_and_closes_the_gap(self) -> None:
        links = self.parse_inline(
            '\n'.join([self.row(''), self.row('Thiaminum')]),
            'blank-name.xml',
        )

        self.assertEqual([link.name for link in links], ['Thiaminum'])
        self.assertEqual([link.source_order for link in links], [0])


class DenylistTests(ParserTestCase):
    def test_denylisted_substance_row_yields_no_link(self) -> None:
        # Cyclo 3 Fort states `Produkt złożony` in an ordinary substance row.
        product = self.product('Cyclo 3 Fort')

        self.assertEqual(product.links, ())
        self.assertEqual(product.common_name, 'Produkt złożony')

    def test_denylisted_common_name_blocks_the_fallback(self) -> None:
        # Moviprep carries no substance row at all, and `Produkt złożony` is in
        # the vocabulary (28 real rows use it), so only the denylist stops it.
        product = self.product('Moviprep')

        self.assertEqual(product.links, ())

    def test_denylisted_names_never_reach_the_resolved_substances(self) -> None:
        # The internal vocabulary still accumulates denylisted keys (parser.py:164-171);
        # _resolve_deferred blocks them at parser.py:287. This checks the post-resolution output.
        keys = {name_key for _, name_key in self.result.substances}

        self.assertEqual(keys & DENYLISTED_SUBSTANCE_KEYS, set())

    def test_specific_descriptive_name_survives_the_bare_category_word(self) -> None:
        # Exact match only: `wyciągi alergenowe` is denied, but the specific
        # extract that starts with those two words is an identity and is kept.
        self.assertIn('wyciągi alergenowe', DENYLISTED_SUBSTANCE_KEYS)

        (link,) = self.product('Staloral 300').links

        self.assertEqual(link.name, 'Wyciągi alergenowe roztoczy kurzu domowego')
        self.assertTrue(link.name_key.startswith('wyciągi alergenowe'))
        self.assertEqual(link.source_field, SourceField.SUBSTANCE_ROW)


class CaseFoldingTests(ParserTestCase):
    def test_case_only_variants_share_one_name_key(self) -> None:
        earlier, later = [
            product for product in self.result.products if product.name == 'Addamel N'
        ]

        self.assertEqual(earlier.links[5].name, 'Sodu fluorek')
        self.assertEqual(later.links[5].name, 'sodu fluorek')
        self.assertEqual(earlier.links[5].name_key, later.links[5].name_key)

    def test_first_seen_spelling_wins_in_the_substance_vocabulary(self) -> None:
        matches = [
            (name, name_key)
            for name, name_key in self.result.substances
            if name_key == 'sodu fluorek'
        ]

        self.assertEqual(matches, [('Sodu fluorek', 'sodu fluorek')])


class NamespaceGuardTests(TestCase):
    def test_wrong_expected_namespace_raises(self) -> None:
        with self.assertRaises(RegistryParseError):
            parse_registry(FIXTURE, NAMESPACE_7)

    def test_namespace_derived_from_the_configured_url(self) -> None:
        url = 'https://rejestry.ezdrowie.gov.pl/api/rpl/medicinal-products/public-pl-report/6.0.0/overall.xml'

        self.assertEqual(namespace_for_url(url), NAMESPACE)

    def test_a_new_version_url_yields_the_new_namespace(self) -> None:
        url = 'https://rejestry.ezdrowie.gov.pl/api/rpl/medicinal-products/public-pl-report/7.0.0/overall.xml'

        self.assertEqual(namespace_for_url(url), NAMESPACE_7)

    def test_url_without_a_version_segment_raises(self) -> None:
        with self.assertRaises(RegistryParseError):
            namespace_for_url('https://rejestry.ezdrowie.gov.pl/api/rpl/overall.xml')
