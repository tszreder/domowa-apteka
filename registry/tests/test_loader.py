"""Prove the load is idempotent and non-destructive.

Those are the two properties a one-shot command hides until its second run, so
almost every case here imports twice. Expected counts come from
`fixtures/README.md`; that file, `test_parser.py`, and this one move together.

The variant snapshots are **built at test time** from the fixture's own text,
never committed: three near-copies would drift from the fixture and from each
other, and the fixture is the single source of truth for the documented
per-product expectations.
"""

import re
import shutil
import tempfile
from datetime import date
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import requests
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from registry.models import Product, ProductSubstance, SourceField, Substance

FIXTURE = Path(__file__).parent / 'fixtures' / 'sample-products.xml'
# Pinned, not inherited from the ambient setting: settings.py reads a .env, so a
# developer with REGISTRY_OVERALL_URL pointing at a 7.0.0 path would otherwise
# get a namespace mismatch on every test here.
REGISTRY_URL = (
    'https://rejestry.ezdrowie.gov.pl/api/rpl/medicinal-products/'
    'public-pl-report/6.0.0/overall.xml'
)

AS_OF = date(2026, 8, 7)
LATER = date(2026, 8, 8)

NALGESIN_ID = '100000037'
XANAX_ID = '100071994'
# Products 13 and 14: `Sodu fluorek` then `sodu fluorek`. Document order is part
# of the fixture's contract — see fixtures/README.md.
ADDAMEL_FIRST_ID = '100002792'
ADDAMEL_SECOND_ID = '100362527'


def fixture_text() -> str:
    return FIXTURE.read_text(encoding='utf-8')


def product_block(text: str, registry_id: str) -> str:
    """The verbatim `<produktLeczniczy>` block carrying `registry_id`."""
    pattern = rf'[ \t]*<produktLeczniczy\b[^>]*\bid="{registry_id}">.*?</produktLeczniczy>\n'
    match = re.search(pattern, text, re.DOTALL)
    if match is None:
        raise AssertionError(f'No product block with id={registry_id!r} in the fixture')
    return match.group(0)


def without_product(text: str, registry_id: str) -> str:
    return text.replace(product_block(text, registry_id), '')


def with_as_of(text: str, as_of: date) -> str:
    """Re-date the snapshot.

    Every reduced or reordered variant needs this: the loader decides what is
    still present by comparing `last_seen_as_of` against the snapshot's own
    date, so a second snapshot dated the same day as the first would leave a
    dropped product looking present.
    """
    return text.replace(f'stanNaDzien="{AS_OF}"', f'stanNaDzien="{as_of}"', 1)


def with_strength(text: str, registry_id: str, strength: str) -> str:
    block = product_block(text, registry_id)
    return text.replace(block, re.sub(r'moc="[^"]*"', f'moc="{strength}"', block, count=1))


def with_addamel_order_swapped(text: str) -> str:
    """Put `sodu fluorek` ahead of `Sodu fluorek` in the file."""
    first = product_block(text, ADDAMEL_FIRST_ID)
    second = product_block(text, ADDAMEL_SECOND_ID)
    placeholder = '<!-- swapped -->\n'
    return text.replace(first, placeholder).replace(second, first).replace(placeholder, second)


@override_settings(REGISTRY_OVERALL_URL=REGISTRY_URL)
class LoaderTestCase(TestCase):
    """Shared plumbing: run the command offline against a snapshot."""

    def run_import(
        self,
        path: Path = FIXTURE,
        min_products: str = '1',
        allow_older: bool = False,
    ) -> str:
        output = StringIO()
        args = ['--file', str(path), '--min-products', min_products]
        if allow_older:
            args.append('--allow-older')
        call_command('import_registry', *args, stdout=output)
        return output.getvalue()

    def write_variant(self, text: str, name: str) -> Path:
        directory = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, directory)
        path = Path(directory) / name
        path.write_text(text, encoding='utf-8')
        return path


class ImportTests(LoaderTestCase):
    def test_fixture_loads_with_the_documented_counts(self) -> None:
        self.run_import()

        self.assertEqual(Product.objects.count(), 12)
        self.assertEqual(Substance.objects.count(), 37)
        self.assertEqual(ProductSubstance.objects.count(), 51)
        self.assertEqual(
            ProductSubstance.objects.filter(source_field=SourceField.SUBSTANCE_ROW).count(),
            50,
        )
        self.assertEqual(
            ProductSubstance.objects.filter(source_field=SourceField.COMMON_NAME).count(),
            1,
        )
        self.assertEqual(Product.objects.filter(is_active=False).count(), 0)
        self.assertEqual(Product.objects.filter(last_seen_as_of=AS_OF).count(), 12)

    def test_veterinary_products_never_reach_the_database(self) -> None:
        self.run_import()

        self.assertFalse(Product.objects.filter(name='Parvoerysin').exists())
        self.assertEqual(Product.objects.exclude(kind='ludzki').count(), 0)

    def test_summary_reports_the_snapshot_date_and_link_split(self) -> None:
        output = self.run_import()

        self.assertIn('Registry snapshot 2026-08-07', output)
        self.assertIn('substance_row: 50', output)
        self.assertIn('common_name: 1', output)

    def test_repeated_substance_on_one_product_survives_the_load(self) -> None:
        # The through-table has no unique key on purpose; a load that silently
        # collapsed these two rows would still look successful.
        self.run_import()

        links = ProductSubstance.objects.filter(product__name='Altacet')

        self.assertEqual([link.amount for link in links], ['1000', '100'])
        self.assertEqual([link.source_order for link in links], [0, 1])


class IdempotencyTests(LoaderTestCase):
    def test_second_run_leaves_identical_rows_and_primary_keys(self) -> None:
        self.run_import()
        product_pks = dict(Product.objects.values_list('registry_id', 'pk'))
        substance_pks = dict(Substance.objects.values_list('name_key', 'pk'))
        link_count = ProductSubstance.objects.count()

        self.run_import()

        # Same PKs, not just same counts: an insert-instead-of-upsert would keep
        # the counts plausible while renumbering every row.
        self.assertEqual(dict(Product.objects.values_list('registry_id', 'pk')), product_pks)
        self.assertEqual(dict(Substance.objects.values_list('name_key', 'pk')), substance_pks)
        self.assertEqual(ProductSubstance.objects.count(), link_count)

    def test_second_run_creates_nothing_new(self) -> None:
        self.run_import()

        output = self.run_import()

        self.assertIn('products loaded:    12 (0 new)', output)
        self.assertIn('substances:         0 new', output)

    def test_changed_strength_is_updated_in_place(self) -> None:
        self.run_import()
        variant = self.write_variant(
            with_strength(fixture_text(), NALGESIN_ID, '500 mg'), 'restrengthened.xml'
        )

        self.run_import(variant)

        self.assertEqual(Product.objects.get(registry_id=NALGESIN_ID).strength, '500 mg')
        self.assertEqual(Product.objects.count(), 12)

    def test_substances_are_shared_across_products_not_duplicated(self) -> None:
        self.run_import()

        substance = Substance.objects.get(name_key='metoprololi succinas')

        # Beto 200 ZK reaches it through the fallback, Beto 25 ZK through an
        # explicit row — one Substance row, two links, two provenances.
        self.assertEqual(substance.product_links.count(), 2)
        self.assertEqual(
            sorted(link.source_field for link in substance.product_links.all()),
            [SourceField.COMMON_NAME, SourceField.SUBSTANCE_ROW],
        )


class WithdrawalTests(LoaderTestCase):
    def reduced_snapshot(self) -> Path:
        text = with_as_of(without_product(fixture_text(), XANAX_ID), LATER)
        return self.write_variant(text, 'without-xanax.xml')

    def test_absent_product_is_deactivated_not_deleted(self) -> None:
        self.run_import()
        links_before = list(
            ProductSubstance.objects.filter(product__registry_id=XANAX_ID).values_list(
                'substance__name_key', 'amount'
            )
        )
        self.assertEqual(len(links_before), 1)

        self.run_import(self.reduced_snapshot())

        xanax = Product.objects.get(registry_id=XANAX_ID)
        self.assertFalse(xanax.is_active)
        # Still the date of the last snapshot that listed it — which is the
        # whole point of the column.
        self.assertEqual(xanax.last_seen_as_of, AS_OF)
        self.assertEqual(
            list(xanax.substance_links.values_list('substance__name_key', 'amount')),
            links_before,
        )

    def test_products_still_present_stay_active_and_advance_their_date(self) -> None:
        self.run_import()

        self.run_import(self.reduced_snapshot())

        nalgesin = Product.objects.get(registry_id=NALGESIN_ID)
        self.assertTrue(nalgesin.is_active)
        self.assertEqual(nalgesin.last_seen_as_of, LATER)
        self.assertEqual(Product.objects.filter(is_active=False).count(), 1)

    def test_returning_product_is_reactivated(self) -> None:
        # Not in the plan's case list, but nothing else covers `is_active` in
        # the upsert's update_fields: drop it and a withdrawn-then-relisted
        # product stays invisible forever, with every other test still green.
        self.run_import()
        self.run_import(self.reduced_snapshot())
        returned = self.write_variant(with_as_of(fixture_text(), date(2026, 8, 9)), 'back.xml')

        self.run_import(returned)

        xanax = Product.objects.get(registry_id=XANAX_ID)
        self.assertTrue(xanax.is_active)
        self.assertEqual(xanax.last_seen_as_of, date(2026, 8, 9))


class FirstSeenWinsTests(LoaderTestCase):
    def test_first_seen_spelling_survives_a_reordered_snapshot(self) -> None:
        self.run_import()
        self.assertEqual(Substance.objects.get(name_key='sodu fluorek').name, 'Sodu fluorek')
        reordered = self.write_variant(
            with_as_of(with_addamel_order_swapped(fixture_text()), LATER), 'reordered.xml'
        )

        self.run_import(reordered)

        # Insert-only is what makes this hold across runs: an upsert touching
        # `name` would be last-write-wins and flip the display spelling.
        self.assertEqual(Substance.objects.get(name_key='sodu fluorek').name, 'Sodu fluorek')
        self.assertEqual(Substance.objects.filter(name_key='sodu fluorek').count(), 1)


class PlausibilityGuardTests(LoaderTestCase):
    def test_snapshot_below_the_floor_is_rolled_back(self) -> None:
        with self.assertRaises(CommandError):
            self.run_import(min_products='999')

        # All three tables, not just Product: Substance is written first, so it
        # is what survives if the transaction nesting is wrong.
        self.assertEqual(Product.objects.count(), 0)
        self.assertEqual(Substance.objects.count(), 0)
        self.assertEqual(ProductSubstance.objects.count(), 0)

    def test_refusal_names_the_full_file_count_so_the_cause_is_diagnosable(self) -> None:
        # A short human-use count with a full file means the filter stopped
        # matching, not a truncated download. Without products_in_file in the
        # message the two are indistinguishable to whoever reads the log.
        with self.assertRaises(CommandError) as raised:
            self.run_import(min_products='999')

        self.assertIn('14 products in the file', str(raised.exception))

    def test_floor_does_not_reject_a_snapshot_that_meets_it(self) -> None:
        self.run_import(min_products='12')

        self.assertEqual(Product.objects.count(), 12)


class SummaryOutputTests(LoaderTestCase):
    def test_summary_reports_the_resolution_share(self) -> None:
        # Criterion 2.5 ("≥95% of human-use products resolve") had to be
        # reconstructed after the fact because no run ever printed it. It now
        # falls out of the summary. Counts are fixtures/README.md's: 14 products,
        # 12 human-use, 2 with no links (the denylisted row and the denylisted
        # common name), so 10 resolve.
        output = self.run_import()

        self.assertIn('products in file:   14 (all kinds)', output)
        self.assertIn('resolved:           10 of 12 (83.3%)', output)


class SnapshotOrderTests(LoaderTestCase):
    """An older snapshot must not rewind freshness or withdraw live products.

    `last_seen_as_of` is stamped unconditionally and the deactivation sweep
    selects on it, so without a guard a stale file silently rolls the column
    F-02 reads backwards and flags every product it predates as withdrawn.
    """

    def setUp(self) -> None:
        later = self.write_variant(with_as_of(fixture_text(), LATER), 'later.xml')
        self.run_import(later)

    def test_older_snapshot_is_refused_and_changes_nothing(self) -> None:
        # The fixture's own AS_OF is older than the LATER snapshot just loaded.
        with self.assertRaises(CommandError):
            self.run_import()

        for product in Product.objects.all():
            self.assertEqual(product.last_seen_as_of, LATER)
        self.assertEqual(Product.objects.filter(is_active=False).count(), 0)

    def test_allow_older_overrides_the_refusal(self) -> None:
        # The escape hatch has to actually work: reloading an archived snapshot
        # on purpose is legitimate, it just must not happen by accident.
        self.run_import(allow_older=True)

        self.assertEqual(Product.objects.filter(last_seen_as_of=AS_OF).count(), 12)

    def test_reimporting_the_same_date_is_not_treated_as_older(self) -> None:
        later = self.write_variant(with_as_of(fixture_text(), LATER), 'later-again.xml')

        self.run_import(later)

        self.assertEqual(Product.objects.filter(last_seen_as_of=LATER).count(), 12)


class DownloadPathTests(LoaderTestCase):
    """The download boundary — the one path `--file` deliberately never touches.

    Both failure modes have to arrive as a `CommandError`: the read side
    (network) and the write side (disk). A traceback here is indistinguishable
    to an operator from a crash in the load itself.
    """

    REQUESTS_GET = 'registry.management.commands.import_registry.requests.get'
    # A connection error is retried DOWNLOAD_MAX_ATTEMPTS times with a real
    # backoff between attempts; patching the sleep keeps these tests fast
    # without touching the retry constants themselves (a backoff short enough
    # not to slow the suite would be too short to help a real transfer).
    SLEEP = 'registry.management.commands.import_registry._sleep'

    def leftover_downloads(self) -> set[Path]:
        return set(Path(tempfile.gettempdir()).glob('registry-*.xml'))

    def run_download(self) -> None:
        # No --file, so the command takes the URL path and creates a temp file.
        call_command('import_registry', '--min-products', '1', stdout=StringIO())

    def test_network_failure_becomes_a_command_error(self) -> None:
        with patch(self.SLEEP):
            with patch(self.REQUESTS_GET, side_effect=requests.ConnectionError('no route')):
                with self.assertRaises(CommandError):
                    self.run_download()

        self.assertEqual(Product.objects.count(), 0)

    def test_network_failure_is_retried_up_to_the_attempt_ceiling(self) -> None:
        # Pins the retry count itself, not just that a CommandError eventually
        # surfaces — the highest-value thing to prove about the retry loop
        # without coupling to _download's call shape.
        from registry.management.commands.import_registry import DOWNLOAD_MAX_ATTEMPTS
        from registry.models import ImportRun

        with patch(self.SLEEP):
            with patch(
                self.REQUESTS_GET, side_effect=requests.ConnectionError('no route')
            ) as requests_get:
                with self.assertRaises(CommandError):
                    self.run_download()

        self.assertEqual(requests_get.call_count, DOWNLOAD_MAX_ATTEMPTS)
        run = ImportRun.objects.get()
        self.assertEqual(run.attempts, DOWNLOAD_MAX_ATTEMPTS)

    def test_disk_failure_becomes_a_command_error(self) -> None:
        # Without OSError in the except clause this escapes as a traceback: the
        # write side of the download loop is a boundary just like the read side.
        response = MagicMock()
        response.iter_content.return_value = [b'<xml/>']
        with patch(self.REQUESTS_GET, return_value=response):
            with patch.object(Path, 'open', side_effect=OSError('No space left')):
                with self.assertRaises(CommandError):
                    self.run_download()

        self.assertEqual(Product.objects.count(), 0)

    def test_temp_file_is_removed_after_a_failed_download(self) -> None:
        before = self.leftover_downloads()

        with patch(self.SLEEP):
            with patch(self.REQUESTS_GET, side_effect=requests.ConnectionError('no route')):
                with self.assertRaises(CommandError):
                    self.run_download()

        self.assertEqual(self.leftover_downloads() - before, set())


class OfflinePathTests(LoaderTestCase):
    def test_file_option_never_touches_the_network(self) -> None:
        with patch(
            'registry.management.commands.import_registry.requests.get'
        ) as requests_get:
            self.run_import()

        requests_get.assert_not_called()

    def test_missing_file_fails_before_any_write(self) -> None:
        with self.assertRaises(CommandError):
            self.run_import(FIXTURE.parent / 'does-not-exist.xml')

        self.assertEqual(Product.objects.count(), 0)

    def test_truncated_snapshot_fails_as_a_command_error(self) -> None:
        # A truncated download is malformed XML far more often than it is a
        # short-but-valid file, so this — not --min-products — is the path a
        # real truncation takes. ET.ParseError subclasses SyntaxError, so
        # without the parser's re-raise it escapes as a traceback instead.
        truncated = self.write_variant(fixture_text()[:20_000], 'truncated.xml')

        with self.assertRaises(CommandError):
            self.run_import(truncated)

        self.assertEqual(Product.objects.count(), 0)
        self.assertEqual(Substance.objects.count(), 0)

    def test_url_without_a_version_segment_fails_loudly(self) -> None:
        # The namespace is derived from the URL, so an unparseable one has to
        # fail before the import rather than defaulting to some version.
        with self.assertRaises(CommandError):
            call_command(
                'import_registry',
                '--file',
                str(FIXTURE),
                '--url',
                'https://rejestry.ezdrowie.gov.pl/api/rpl/overall.xml',
                stdout=StringIO(),
            )
