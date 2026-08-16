"""Pin the verdict at its boundaries and prove both surfaces agree.

Every case here asserts something a later reader could plausibly "fix" by
accident: the trigger-agnostic decision, the collapse-to-one-number decision,
and the STALE_AFTER boundary itself. Each assertion exists because removing it
would let that mistake back in silently.
"""

from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone

from registry.freshness import STALE_AFTER, get_verdict
from registry.models import ImportRun, RunStatus, RunTrigger


def make_run(
    *,
    started_at,
    status: str = RunStatus.SUCCESS,
    trigger: str = RunTrigger.MANUAL,
    source_as_of=None,
) -> ImportRun:
    return ImportRun.objects.create(
        started_at=started_at,
        finished_at=started_at,
        status=status,
        trigger=trigger,
        source_as_of=source_as_of,
    )


class VerdictTests(TestCase):
    def test_no_runs_at_all_reads_as_stale(self) -> None:
        verdict = get_verdict()

        self.assertTrue(verdict.is_stale)
        self.assertIsNone(verdict.last_success_at)

    def test_a_failed_run_does_not_count_as_success(self) -> None:
        make_run(started_at=timezone.now(), status=RunStatus.FAILED)

        verdict = get_verdict()

        self.assertTrue(verdict.is_stale)
        self.assertIsNone(verdict.last_success_at)

    def test_success_just_under_stale_after_reads_fresh(self) -> None:
        make_run(started_at=timezone.now() - STALE_AFTER + timedelta(minutes=1))

        self.assertFalse(get_verdict().is_stale)

    def test_success_just_over_stale_after_reads_stale(self) -> None:
        make_run(started_at=timezone.now() - STALE_AFTER - timedelta(minutes=1))

        self.assertTrue(get_verdict().is_stale)

    def test_success_exactly_at_stale_after_reads_fresh(self) -> None:
        # is_stale is age > STALE_AFTER, not >=: the boundary itself belongs
        # to "fresh". "Now" has to be frozen to one instant for both the run's
        # started_at and get_verdict()'s own timezone.now() call: without it,
        # the two calls land microseconds apart, age ends up a hair over
        # STALE_AFTER, and this test fails more often than it passes.
        frozen_now = timezone.now()
        make_run(started_at=frozen_now - STALE_AFTER)

        with patch('registry.freshness.timezone.now', return_value=frozen_now):
            verdict = get_verdict()

        self.assertEqual(verdict.age, STALE_AFTER)
        self.assertFalse(verdict.is_stale)

    def test_old_source_as_of_on_a_recent_success_still_reads_fresh(self) -> None:
        # Pins the collapse-to-one-number decision: last-successful-run is the
        # headline, not the snapshot's own date. A later reader must not "fix"
        # this by folding source_as_of into is_stale.
        make_run(
            started_at=timezone.now(),
            source_as_of=timezone.now().date() - timedelta(days=400),
        )

        verdict = get_verdict()

        self.assertFalse(verdict.is_stale)
        self.assertEqual(verdict.source_as_of, timezone.now().date() - timedelta(days=400))

    def test_recent_manual_run_reads_fresh(self) -> None:
        # The verdict is deliberately trigger-agnostic. Without this
        # assertion the next reader adds a trigger=scheduled filter and no
        # test objects.
        make_run(started_at=timezone.now(), trigger=RunTrigger.MANUAL)

        self.assertFalse(get_verdict().is_stale)

    def test_most_recent_success_wins_over_an_older_one(self) -> None:
        make_run(started_at=timezone.now() - timedelta(days=10))
        make_run(started_at=timezone.now() - timedelta(hours=1))

        verdict = get_verdict()

        age = verdict.age
        assert age is not None
        self.assertLess(age, timedelta(hours=2))


class RegistryStatusCommandTests(TestCase):
    def run_status(self) -> tuple[str, CommandError | None]:
        output = StringIO()
        try:
            call_command('registry_status', stdout=output)
        except CommandError as exc:
            return output.getvalue(), exc
        return output.getvalue(), None

    def test_exits_non_zero_when_stale(self) -> None:
        output, error = self.run_status()

        self.assertIsNotNone(error)
        self.assertIn('No successful import has ever run.', output)

    def test_exits_zero_when_fresh(self) -> None:
        make_run(started_at=timezone.now())

        output, error = self.run_status()

        self.assertIsNone(error)
        self.assertIn('Registry data is fresh.', output)

    def test_agrees_with_the_admin_verdict_for_the_same_data(self) -> None:
        make_run(started_at=timezone.now() - STALE_AFTER - timedelta(hours=1))

        _, error = self.run_status()
        verdict = get_verdict()

        self.assertEqual(error is not None, verdict.is_stale)
