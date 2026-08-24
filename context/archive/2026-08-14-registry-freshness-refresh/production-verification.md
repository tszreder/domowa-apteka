---
change_id: registry-freshness-refresh
status: verified
---

# Production verification — daily unattended cron

Confirms the platform's own `railway.cron.json` schedule fires
`registry-import-cron` **without a human triggering it**, distinct from the
manual "Run now" verification recorded in `context/deployment/deploy-plan.md`
right after Phase 3 landed. Plays the same role for F-02 that
`context/archive/2026-08-07-registry-substance-data/production-baseline.md`
played for F-01: a real number to compare future regressions against.

Three consecutive unattended fires were captured — one is enough to satisfy
the plan's criterion, three is what had actually accumulated by the time this
was written up, and the trend across them (drift shrinking, `products_loaded`
declining a handful of products a day) is itself useful signal.

## How these were confirmed as genuinely unattended, not manual

`railway api`'s `deploymentInstanceExecutions` query (scoped to
`registry-import-cron`'s service/environment IDs) lists every container
execution against a deployment, independent of what launched it. The three
executions below all ran against deployment `f519f1cd` — the `railway up`
that shipped the `5 23 * * *` schedule change (PR #23, merged `0fcebdc`) — at
times that land on that schedule, with no corresponding "Run now" dashboard
action or CLI command issued around them. Contrast the first row in
`deploy-plan.md`'s "Registry import cron" section, an explicit manual
trigger, which *is* attributable to a specific action taken in this session.

## Runs

### Run 1 — 2026-08-16

- Scheduled: 23:05:00 UTC. Actual `createdAt`: **23:07:02 UTC** (drift: +2m2s)
- `completedAt`: 23:07:10 UTC
- Snapshot `stanNaDzien`: 2026-08-16
- Products loaded: 20,242 (0 new)
- Products marked inactive: 3
- Substances created: 0 new
- Links created: 25,879 (`substance_row`: 25,465, `common_name`: 414)
- Resolved: 19,681 of 20,242 (97.2%)
- Elapsed (import_registry's own figure): 5.6 s
- Attempts: 1 (no retry — single clean download)
- Largest drift of the three: this was the schedule's first cycle after the
  config change deployed at 22:04:35 UTC the same day, less than an hour
  before this slot.

### Run 2 — 2026-08-17

- Scheduled: 23:05:00 UTC. Actual `createdAt`: **23:06:54 UTC** (drift: +1m54s)
- `completedAt`: 23:07:02 UTC
- Snapshot `stanNaDzien`: 2026-08-17
- Products loaded: 20,237 (0 new)
- Products marked inactive: 8
- Substances created: 0 new
- Links created: 25,871 (`substance_row`: 25,458, `common_name`: 413)
- Resolved: 19,676 of 20,237 (97.2%)
- Elapsed: 5.7 s
- Attempts: 1

### Run 3 — 2026-08-18

- Scheduled: 23:05:00 UTC. Actual `createdAt`: **23:05:09 UTC** (drift: +9s)
- `completedAt`: 23:05:24 UTC
- Snapshot `stanNaDzien`: 2026-08-18
- Products loaded: 20,227 (0 new)
- Products marked inactive: 18
- Substances created: 0 new
- Links created: 25,858 (`substance_row`: 25,445, `common_name`: 413)
- Resolved: 19,666 of 20,227 (97.2%)
- Elapsed: 5.7 s
- Attempts: 1

## Comparison against the F-01 production baseline

| | F-01 baseline (2026-08-13) | Run 1 (08-16) | Run 2 (08-17) | Run 3 (08-18) |
| --- | --- | --- | --- | --- |
| Products loaded | 20,245 | 20,242 | 20,237 | 20,227 |
| Products inactive (cumulative) | 0 | 3 | 8 | 18 |
| Substances created (new) | 3,391 | 0 | 0 | 0 |
| Links created | 25,884 | 25,879 | 25,871 | 25,858 |
| Resolved share | ≥95% (not printed at the time) | 97.2% | 97.2% | 97.2% |

The steady decline in `products_loaded` and the matching rise in
`products_inactive` is the deactivation sweep (`registry/loader.py`) doing
exactly what it's for: a handful of products drop out of each day's snapshot
and get flagged `is_active=False` rather than deleted, never reversed unless
the registry relists them. Zero new substances across all three runs is
expected — the vocabulary was already saturated by the 2026-08-13 baseline
load, and nothing in three days of drift introduced a genuinely new active
substance name. `resolved` sits comfortably above the plan's originally
targeted ≥95%.

## `ImportRun` rows — confirmed live, plus by construction

Unlike the manual-trigger verification in `deploy-plan.md` (which relied only
on the construction argument below), this round had a stronger check
available: the `web` service's dashboard **Console** tab gives a live shell
in the running container, so `manage.py registry_status` was run directly
against production, 2026-08-19:

```
$ python manage.py registry_status
Last successful import: 2026-08-18 23:05:11.469797+00:00 (22:45:01.378415 ago)
Snapshot held: 2026-08-18
Registry data is fresh.
```

Exit was 0 (no `CommandError`), and the timestamp matches Run 3's
`createdAt` (23:05:09) to within 2 seconds of container boot overhead — this
*is* Run 3's `ImportRun` row, read live, not inferred. `trigger=scheduled` on
that row still rests on construction (no admin UI screenshot or direct ORM
read this round), for the same reason as before: `handle()`'s success path
(`import_registry.py`) calls `run.save()` — stamping `status=success`,
`trigger=scheduled` (the only value `railway.cron.json`'s `startCommand`
ever passes), and the `LoadStats` counters — *before* `_report()` prints the
summary. Seeing that summary in each execution's logs, for three separate
unattended fires, is proof three `ImportRun` rows landed with exactly those
values.

## Schedule-vs-actual drift

All three drifts (+2m2s, +1m54s, +9s) are comfortably inside
`infrastructure.md`'s documented "±minutes" platform jitter and nowhere near
the 48h `STALE_AFTER` threshold `registry/freshness.py` uses. No evidence of
a dropped run in this window — three consecutive daily fires, three
consecutive successes.
