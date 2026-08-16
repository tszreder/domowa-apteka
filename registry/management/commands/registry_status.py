"""Make freshness checkable without a browser session.

Also gives future alerting something to hang off with no code change: point a
second cron at this command and the platform's own failed-execution
notifications carry it. See registry/freshness.py for the verdict this reads.
"""

from typing import Any

from django.core.management.base import BaseCommand, CommandError

from registry.freshness import STALE_AFTER, get_verdict


class Command(BaseCommand):
    help = 'Print the registry freshness verdict. Exits non-zero when stale.'

    def handle(self, *args: Any, **options: Any) -> None:
        verdict = get_verdict()

        if verdict.last_success_at is None:
            self.stdout.write('No successful import has ever run.')
        else:
            self.stdout.write(
                f'Last successful import: {verdict.last_success_at} ({verdict.age} ago)'
            )
            self.stdout.write(f'Snapshot held: {verdict.source_as_of}')

        if verdict.is_stale:
            raise CommandError(
                f'Registry data is STALE (no success within {STALE_AFTER}).'
            )

        self.stdout.write(self.style.SUCCESS('Registry data is fresh.'))
