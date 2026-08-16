"""Answer "is the registry data fresh?" in exactly one place.

Both the read-only admin changelist and `manage.py registry_status` call
`get_verdict()`, so the two surfaces can never disagree with each other.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from django.utils import timezone

from .models import ImportRun, RunStatus

# 48h, not the PRD's literal "about a day": infrastructure.md's Unknown
# Unknowns record that the platform's cron silently drops a scheduled run and
# fires ±minutes late, so the threshold has to tolerate one dropped run plus
# drift, or the signal gets ignored as noise.
STALE_AFTER = timedelta(hours=48)


@dataclass(frozen=True)
class FreshnessVerdict:
    """The single freshness fact, derived from run history.

    `source_as_of` is carried for display and diagnosis only — it is
    deliberately NOT part of `is_stale`. The decision was to collapse
    freshness to one number, and that number is when the pipeline last
    *succeeded*, not what date the registry's own snapshot claims.
    """

    last_success_at: datetime | None
    source_as_of: date | None
    age: timedelta | None
    is_stale: bool


def get_verdict() -> FreshnessVerdict:
    """Stale means no successful run at all, or one older than STALE_AFTER.

    Deliberately trigger-agnostic: a recent `trigger=manual` run reads fresh
    just like a scheduled one. Narrowing this to scheduled runs only would
    make a healthy hand-run import look stale, which is not what this
    function is for — see the test pinning this in test_freshness.py.
    """
    last_success = (
        ImportRun.objects.filter(status=RunStatus.SUCCESS).order_by('-started_at').first()
    )
    if last_success is None:
        return FreshnessVerdict(last_success_at=None, source_as_of=None, age=None, is_stale=True)

    age = timezone.now() - last_success.started_at
    return FreshnessVerdict(
        last_success_at=last_success.started_at,
        source_as_of=last_success.source_as_of,
        age=age,
        is_stale=age > STALE_AFTER,
    )
