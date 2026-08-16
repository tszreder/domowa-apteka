"""Prove the run record is written on both paths.

The highest-value case here is the failure path surviving the import
transaction's rollback — see `test_failure_leaves_a_failed_row_and_no_data`.
Everything else follows `test_loader.py`'s conventions: the offline `--file`
path against the shared fixture, `override_settings` for the pinned registry
URL, no live network.
"""

from datetime import date
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from registry.models import ImportRun, Product, RunStatus, RunTrigger

FIXTURE = Path(__file__).parent / 'fixtures' / 'sample-products.xml'
REGISTRY_URL = (
    'https://rejestry.ezdrowie.gov.pl/api/rpl/medicinal-products/'
    'public-pl-report/6.0.0/overall.xml'
)
AS_OF = date(2026, 8, 7)


@override_settings(REGISTRY_OVERALL_URL=REGISTRY_URL)
class ImportRunTests(TestCase):
    def run_import(self, **extra_args: str) -> str:
        output = StringIO()
        args = ['--file', str(FIXTURE), '--min-products', '1']
        for key, value in extra_args.items():
            args.append(f'--{key.replace("_", "-")}')
            args.append(value)
        call_command('import_registry', *args, stdout=output)
        return output.getvalue()

    def test_success_records_status_and_counters_matching_the_summary(self) -> None:
        output = self.run_import()

        run = ImportRun.objects.get()
        self.assertEqual(run.status, RunStatus.SUCCESS)
        finished_at = run.finished_at
        assert finished_at is not None
        self.assertGreaterEqual(finished_at, run.started_at)
        self.assertEqual(run.source_as_of, AS_OF)
        self.assertEqual(run.trigger, RunTrigger.MANUAL)
        self.assertEqual(run.error, '')

        # Counters match the command's own printed summary, not re-derived.
        self.assertEqual(run.products_loaded, 12)
        self.assertEqual(run.products_created, 12)
        self.assertEqual(run.products_inactive, 0)
        self.assertEqual(run.substances_created, 37)
        self.assertEqual(run.links_created, 51)
        self.assertEqual(run.products_without_links, 2)
        self.assertIn('products loaded:    12 (12 new)', output)

    def test_failure_leaves_a_failed_row_and_no_data(self) -> None:
        # The min-products guard raises CommandError *inside* both
        # transaction.atomic() blocks (import_registry.py's _import), so a
        # failure record written in that scope would roll back with it. This
        # is the test that proves the ImportRun create/save calls sit outside
        # it — the single most likely defect in this change.
        with self.assertRaises(CommandError):
            self.run_import(min_products='999')

        run = ImportRun.objects.get()
        self.assertEqual(run.status, RunStatus.FAILED)
        self.assertIsNotNone(run.finished_at)
        self.assertIn('14 products in the file', run.error)
        self.assertIsNone(run.source_as_of)
        self.assertIsNone(run.products_loaded)

        # The guard's own rollback still holds: nothing else was written.
        self.assertEqual(Product.objects.count(), 0)

    def test_trigger_defaults_to_manual(self) -> None:
        self.run_import()

        self.assertEqual(ImportRun.objects.get().trigger, RunTrigger.MANUAL)

    def test_trigger_scheduled_is_recorded(self) -> None:
        self.run_import(trigger='scheduled')

        self.assertEqual(ImportRun.objects.get().trigger, RunTrigger.SCHEDULED)

    def test_missing_file_still_leaves_a_failed_row(self) -> None:
        # A failure before any download/parse work starts (namespace or file
        # validation) must still be recorded — the run is created before any
        # of that runs.
        with self.assertRaises(CommandError):
            call_command(
                'import_registry',
                '--file',
                str(FIXTURE.parent / 'does-not-exist.xml'),
                '--min-products',
                '1',
                stdout=StringIO(),
            )

        run = ImportRun.objects.get()
        self.assertEqual(run.status, RunStatus.FAILED)
        self.assertIn('No such snapshot file', run.error)

    def test_unexpected_exception_still_leaves_a_failed_row(self) -> None:
        # Not just CommandError: an unanticipated crash (a DatabaseError, a
        # bug) must not leave a row stuck at RUNNING with no error message —
        # that is exactly the silence this change exists to eliminate.
        with patch(
            'registry.management.commands.import_registry.namespace_for_url',
            side_effect=RuntimeError('boom'),
        ):
            with self.assertRaises(RuntimeError):
                self.run_import()

        run = ImportRun.objects.get()
        self.assertEqual(run.status, RunStatus.FAILED)
        self.assertIn('boom', run.error)

    def test_file_path_records_zero_download_attempts(self) -> None:
        self.run_import()

        self.assertEqual(ImportRun.objects.get().attempts, 0)
