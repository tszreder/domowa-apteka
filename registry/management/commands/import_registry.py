"""The roadmap's "one repeatable command": snapshot in, local tables out.

Downloads (or reads) one `overall.xml`, parses it offline, and loads the result
in a single transaction. Running it twice on the same input leaves the database
in an identical state.
"""

import tempfile
import time
from datetime import date
from pathlib import Path
from typing import Any

import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from registry.loader import LoadStats, load_parse_result
from registry.models import ImportRun, Product, RunStatus, RunTrigger
from registry.parser import RegistryParseError, namespace_for_url, parse_registry

# Comfortably below the 20,187 human-use products measured on 2026-08-07, and
# far above anything a truncated download would yield. Overridable per-run
# because the test fixture holds 14 products: a bare constant would fail every
# loader test, and applying the guard only on the URL path would leave it
# untested on the path the tests actually exercise.
MIN_EXPECTED_PRODUCTS = 10_000

# (connect, read) seconds. The read timeout is per-chunk, not for the whole
# 74 MB body, so it can stay short enough to notice a stalled transfer.
DOWNLOAD_TIMEOUT = (10, 60)
CHUNK_SIZE = 1024 * 1024

# A bounded retry for a transient network blip on a ~74 MB transfer. Sized so
# the worst case (DOWNLOAD_MAX_ATTEMPTS attempts, each possibly stalling for
# the full per-chunk DOWNLOAD_TIMEOUT read timeout, plus the backoff sleeps
# between them) stays orders of magnitude below the 24 h schedule interval.
DOWNLOAD_MAX_ATTEMPTS = 3
DOWNLOAD_RETRY_BACKOFF = (5, 15)  # seconds, between attempts 1→2 and 2→3
# Gates retry ATTEMPTS, not total wall clock — checked before each retry, not
# during a transfer. A single hung transfer is bounded by DOWNLOAD_TIMEOUT's
# per-chunk read timeout, not by this constant. The two are easy to confuse.
RUN_DEADLINE_SECONDS = 600

# Patched by tests to skip the real wait: a backoff short enough not to slow
# down `manage.py test` would be too short to help a real transfer, so the
# constants stay realistic and the sleep itself becomes the seam instead.
_sleep = time.sleep


class Command(BaseCommand):
    help = 'Import products and active substances from the national registry snapshot.'

    # Number of download attempts made this run, including a --file run
    # (which makes none). Set on the instance rather than threaded through
    # return values so handle()'s except clause can read it after _run_import
    # raises partway through.
    _attempts: int = 0

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            '--file',
            help='Parse a local snapshot instead of downloading. Makes the command '
            'offline-repeatable, which is what the tests use.',
        )
        parser.add_argument(
            '--url',
            help='Override REGISTRY_OVERALL_URL. Also selects the expected XML '
            'namespace, so it is meaningful alongside --file when checking a '
            'snapshot from a different export version.',
        )
        parser.add_argument(
            '--min-products',
            type=int,
            default=MIN_EXPECTED_PRODUCTS,
            help='Refuse to commit a snapshot with fewer human-use products than '
            f'this (default: {MIN_EXPECTED_PRODUCTS}). A truncated download '
            'otherwise looks like a successful load of 300 products.',
        )
        parser.add_argument(
            '--keep-download',
            action='store_true',
            help='Leave the downloaded snapshot on disk instead of deleting it.',
        )
        parser.add_argument(
            '--allow-older',
            action='store_true',
            help='Load a snapshot older than the newest already imported. Off by '
            'default: an older snapshot rewinds last_seen_as_of on every shared '
            'product and deactivates the ones it predates.',
        )
        parser.add_argument(
            '--trigger',
            choices=[RunTrigger.MANUAL.value, RunTrigger.SCHEDULED.value],
            default=RunTrigger.MANUAL.value,
            help='Who started this run, recorded on the ImportRun row (default: '
            'manual). The cron service passes --trigger scheduled.',
        )

    def handle(self, *args: Any, **options: Any) -> None:
        started = time.monotonic()

        # Created before any work — including URL/namespace validation — so
        # even the earliest failure leaves a row behind. Updated after this
        # try block exits, never inside it, so it cannot share a transaction
        # with anything import-related.
        run = ImportRun.objects.create(
            started_at=timezone.now(),
            trigger=options['trigger'],
        )
        self._attempts = 0
        try:
            stats = self._run_import(options)
        except Exception as exc:
            run.finished_at = timezone.now()
            run.status = RunStatus.FAILED
            run.attempts = self._attempts
            run.error = str(exc)
            run.save()
            raise

        run.finished_at = timezone.now()
        run.status = RunStatus.SUCCESS
        run.attempts = self._attempts
        run.source_as_of = stats.source_as_of
        run.products_loaded = stats.products_loaded
        run.products_created = stats.products_created
        run.products_inactive = stats.products_inactive
        run.substances_created = stats.substances_created
        run.links_created = stats.links_created
        run.products_without_links = stats.products_without_links
        run.save()

        self._report(stats, time.monotonic() - started)

    def _run_import(self, options: dict[str, Any]) -> LoadStats:
        """The download/parse/load path, unchanged from before the run record.

        Split out from `handle()` so run-record bookkeeping can wrap it in one
        `try/except` without disturbing the existing `try/finally` that owns
        temp-file cleanup.
        """
        # Whichever URL is in play decides the namespace, so the two cannot
        # drift apart. See registry/parser.py::namespace_for_url.
        url: str = options['url'] or settings.REGISTRY_OVERALL_URL
        try:
            expected_namespace = namespace_for_url(url)
        except RegistryParseError as exc:
            raise CommandError(str(exc)) from exc

        downloaded: Path | None = None
        if options['file']:
            path = Path(options['file'])
            if not path.is_file():
                raise CommandError(f'No such snapshot file: {path}')
        else:
            # Created here rather than inside _download so the `finally` below
            # owns cleanup on every failure path, including a mid-transfer one.
            with tempfile.NamedTemporaryFile(
                prefix='registry-', suffix='.xml', delete=False
            ) as handle:
                downloaded = Path(handle.name)
            path = downloaded

        try:
            if downloaded is not None:
                self._download(url, downloaded)
            stats = self._import(
                path,
                expected_namespace,
                options['min_products'],
                options['allow_older'],
            )
        finally:
            if downloaded is not None:
                if options['keep_download']:
                    self.stdout.write(f'Downloaded snapshot kept at {downloaded}')
                else:
                    downloaded.unlink(missing_ok=True)

        return stats

    def _download(self, url: str, destination: Path) -> None:
        """Stream the snapshot to disk, never parsing off the live response.

        A mid-parse network blip would otherwise leave a half-applied load.

        Retries only `requests.RequestException` — a transient network blip —
        up to `DOWNLOAD_MAX_ATTEMPTS` times with a short ascending backoff,
        bounded by `RUN_DEADLINE_SECONDS` on when a *retry* may still start.
        `OSError` (a full disk) fails immediately: the write side of this loop
        is just as much a boundary as the read side, but retrying it would not
        help. Every attempt is recorded on `self._attempts` regardless of
        outcome, so the run record shows how many were made even on failure.
        """
        self.stdout.write(f'Downloading {url}')
        deadline = time.monotonic() + RUN_DEADLINE_SECONDS
        last_exc: Exception | None = None
        for attempt in range(1, DOWNLOAD_MAX_ATTEMPTS + 1):
            self._attempts = attempt
            try:
                response = requests.get(url, stream=True, timeout=DOWNLOAD_TIMEOUT)
                response.raise_for_status()
                with destination.open('wb') as handle:
                    for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                        handle.write(chunk)
                return
            except requests.RequestException as exc:
                last_exc = exc
                if attempt == DOWNLOAD_MAX_ATTEMPTS or time.monotonic() >= deadline:
                    break
                backoff = DOWNLOAD_RETRY_BACKOFF[min(attempt - 1, len(DOWNLOAD_RETRY_BACKOFF) - 1)]
                self.stdout.write(
                    f'Download attempt {attempt} failed ({exc}); retrying in {backoff}s'
                )
                _sleep(backoff)
            except OSError as exc:
                raise CommandError(f'Could not download {url}: {exc}') from exc
        raise CommandError(
            f'Could not download {url} after {self._attempts} attempt(s): {last_exc}'
        ) from last_exc

    def _import(
        self,
        path: Path,
        expected_namespace: str,
        min_products: int,
        allow_older: bool,
    ) -> LoadStats:
        try:
            result = parse_registry(path, expected_namespace)
        except RegistryParseError as exc:
            raise CommandError(str(exc)) from exc

        with transaction.atomic():
            if not allow_older:
                self._reject_older_snapshot(result.source_as_of, path)
            stats = load_parse_result(result)
            # Inside the transaction, so a snapshot that fails the guard leaves
            # nothing behind — not even the substances written first.
            if stats.products_loaded < min_products:
                raise CommandError(
                    f'Only {stats.products_loaded} human-use products in {path} '
                    f'(expected at least {min_products}), out of '
                    f'{stats.products_in_file} products in the file. Refusing to '
                    'load it; nothing was written. A low count with a full file '
                    'means the human-use filter stopped matching, not a truncated '
                    'download.'
                )
        return stats

    def _reject_older_snapshot(self, source_as_of: date, path: Path) -> None:
        """Refuse to rewind freshness.

        `last_seen_as_of` is stamped unconditionally and the deactivation sweep
        selects on it, so an older snapshot both rewinds the column F-02 reads
        as freshness and flags every product it predates as withdrawn — while
        reporting success. This is reachable through the documented path rather
        than only by operator error: REGISTRY_OVERALL_URL exists so the export
        version can be repointed, and 5.0.0 is still served.

        Lives here rather than in the loader: which snapshots are acceptable is
        a policy decision, and the loader is deliberately dumb about policy.
        """
        newest = Product.objects.aggregate(newest=Max('last_seen_as_of'))['newest']
        if newest is not None and source_as_of < newest:
            raise CommandError(
                f'{path} is dated {source_as_of}, older than the {newest} already '
                'loaded. Loading it would rewind last_seen_as_of on every shared '
                'product and deactivate the ones absent from it. Pass --allow-older '
                'to do it anyway.'
            )

    def _report(self, stats: LoadStats, elapsed: float) -> None:
        self.stdout.write(f'Registry snapshot {stats.source_as_of}')
        self.stdout.write(f'  products in file:   {stats.products_in_file} (all kinds)')
        self.stdout.write(
            f'  products loaded:    {stats.products_loaded} '
            f'({stats.products_created} new)'
        )
        self.stdout.write(f'  products inactive:  {stats.products_inactive}')
        self.stdout.write(
            f'  substances:         {stats.substances_created} new'
        )
        self.stdout.write(f'  links:              {stats.links_created}')
        for source_field, count in stats.links_by_source_field.items():
            self.stdout.write(f'    {source_field}: {count}')
        # The plan's criterion 2.5 is "≥95% of human-use products resolve to at
        # least one substance". Printing it means the number is recorded by any
        # ordinary run instead of having to be reconstructed afterwards.
        resolved = stats.products_loaded - stats.products_without_links
        share = resolved / stats.products_loaded * 100 if stats.products_loaded else 0.0
        self.stdout.write(
            f'  resolved:           {resolved} of {stats.products_loaded} ({share:.1f}%)'
        )
        self.stdout.write(self.style.SUCCESS(f'  elapsed:            {elapsed:.1f} s'))
