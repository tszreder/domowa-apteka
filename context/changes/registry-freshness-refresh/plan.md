# Registry Freshness Refresh (F-02) Implementation Plan

## Overview

Put the registry snapshot import on a daily schedule, and give the app its own
persistent record of every import attempt so that "when did the data last
successfully refresh?" is answered by the application, not inferred from the
scheduler. The platform's cron silently *drops* a run when the previous
execution is still active and fires ±minutes late
(`context/foundation/infrastructure.md` § Unknown Unknowns), so "the cron is
scheduled" and even "the cron fired" are documented **not** to be evidence of
freshness. An app-side run record is.

## Current State Analysis

F-01 (`registry-substance-data`, archived) left a deliberate seam here. Its plan
states outright: *"No `ImportRun` / snapshot model. Freshness lives on the
product as `last_seen_as_of`. F-02 owns the run record and the scheduler."*
(`context/archive/2026-08-07-registry-substance-data/plan.md:104-106`).

What exists:

- `registry/management/commands/import_registry.py` — downloads (or reads)
  `overall.xml`, parses it offline, loads it in one transaction. Idempotent:
  the production baseline recorded two consecutive runs producing identical row
  counts (`context/archive/2026-08-07-registry-substance-data/production-baseline.md`).
  Elapsed ~6 s in production for download + parse + write.
- `registry/loader.py` — `load_parse_result()`, deliberately dumb about policy.
- `registry/models.py` — `Product.last_seen_as_of` is the snapshot's
  `stanNaDzien`, described in the model docstring as *"the freshness value, and
  the one F-02 reads"*.
- `registry/admin.py` — read-only admin over `Product` / `Substance`,
  structurally incapable of writing.
- `.github/workflows/deploy.yml` — `check` gates PRs; `deploy` runs
  `railway up --service web --ci` on push to `main`.
- `railway.json` at the repo root — the **web** service's config: a gunicorn
  `startCommand`, `healthcheckPath: /health/`, `numReplicas: 1`.

What is missing:

- Any record that an import ran at all — success or failure. Today a failed
  import leaves nothing behind but a log line in an ephemeral stream.
- Any schedule. The import has only ever been run by hand (once, via a
  temporary `startCommand`, since reverted).
- `settings.py` has **no** `EMAIL_BACKEND`, `ADMINS`, `SERVER_EMAIL`, or
  `LOGGING` block (verified — zero matches). Any future email alerting starts
  from nothing.

## Desired End State

A Railway cron service runs `manage.py import_registry` once a day. Every
attempt — successful or not — writes an `ImportRun` row that survives the
import's own transaction rollback. A single freshness verdict, derived from the
most recent *successful* run against one named 48-hour constant, is readable in
two places: a read-only Django admin changelist, and a `manage.py
registry_status` command that exits non-zero when stale.

Verify by: loading `/admin/registry/importrun/` and seeing yesterday's run with
its counts; running `manage.py registry_status` and getting exit 0 with a
recent timestamp; confirming a deliberately failed run (bad `--url`) leaves a
`failed` row behind rather than nothing.

### Key Discoveries:

- **The transaction trap.** `import_registry.py:147` opens
  `transaction.atomic()`, `loader.py:89` opens another inside it, and the
  min-products guard raises `CommandError` **inside** both
  (`import_registry.py:153-161`) precisely so a bad snapshot writes nothing. A
  failure record written in that scope rolls back with it — destroying exactly
  the evidence this change exists to capture. This holds under Django's
  `TestCase` too, since a nested `atomic()` uses a savepoint that unwinds on the
  propagating exception, so the test for it is meaningful rather than vacuous.
- **`deploy.cronSchedule` is real.** Confirmed against the official
  `https://railway.com/railway.schema.json` (fetched 2026-08-14, HTTP 200):
  `deploy` accepts `cronSchedule` (string|null), and `restartPolicyType` accepts
  `NEVER`. A cron service *can* be config-as-code.
- **UNVERIFIED, and Phase 3 must settle it empirically:** how a second Railway
  service selects a config file other than the repo-root `railway.json`.
  `railway up --help` exposes `--service` but **no** config-path flag, and
  `railway service --help` lists no config subcommand. Recorded as unverified
  rather than omitted, per `context/foundation/lessons.md` § "Verify a platform
  limitation before registering it as a risk".
- **Freshness has two facts, and only one is the headline.**
  `max(Product.last_seen_as_of)` is the registry's own as-of date; the run
  record answers "did our pipeline work". This plan makes **last successful
  run** the single headline number (decision below), recording `source_as_of` on
  the run for diagnosis but keeping it out of the verdict.
- **Retry has a hard edge.** The registry publishes daily with no `ETag` and no
  `Last-Modified` (`context/archive/.../options.md` § 2), so there is no cheap
  "has it changed?" — every run re-downloads ~74 MB. Retrying a *network*
  failure is worth it; retrying a parse failure or the min-products guard is
  not, because both are deterministic in the file.

## What We're NOT Doing

- **No alerting.** "The app knows when it last succeeded" is not "someone gets
  paged". This change lays the seam (a verdict function plus a non-zero-exit
  command) and stops. Wiring email or a webhook means SMTP credentials or a
  webhook secret and new env vars — past the roadmap's stated outcome for F-02.
- **No user-facing staleness banner.** The roadmap sequences F-02 before S-02 is
  built, so there is no substance-facing screen to warn on.
  `infrastructure.md`'s own risk-register mitigation says "surfaced in **admin**".
  A user-visible banner belongs to S-02/S-03.
- **No lock or mutex.** See Phase 1's wall-clock ceiling; a stale lock would
  reintroduce the silent-skip failure this change exists to eliminate.
- **No conditional GET / delta ingestion.** Settled in F-01: the publisher emits
  no `status` attribute on any product and no HTTP validators. Full-snapshot
  replace is the only supported mode. Do not design a diff pipeline.
- **No changes to parsing, normalization, or the substance model.** F-01 owns
  all of it.
- **No pruning or retention policy** for `ImportRun`. One row per day is ~365
  rows a year; revisit if it ever matters.
- **No `SECURE_SSL_REDIRECT` / HSTS work.** Parked in the roadmap; unrelated.

## Implementation Approach

Three layers, then verification. The write side (Phase 1) has to be right
before anything reads it, so the run record and its failure-path safety land
first. The read side (Phase 2) derives one verdict and exposes it twice, with
both surfaces calling the same function so they cannot disagree. The scheduler
(Phase 3) comes last because it is the only part that touches production
infrastructure, and because a schedule that fires before there is anything to
record is worthless. Phase 4 is separate because it can only be checked after a
real scheduled execution has fired.

## Critical Implementation Details

**State sequencing — the run record must not share the import's transaction.**
The `ImportRun` row is created *before* `transaction.atomic()` is entered and
updated *after* the block has exited, on both the success and the exception
path. This is the single most likely defect in the change and the reason
criterion 1.3 exists.

**Timing & lifecycle — deploy order matters.** The cron service and the web
service deploy from the same repo, but only the web service's `startCommand`
runs `migrate`. `deploy.yml` must deploy `web` first and the cron service
second, so a cron execution can never hit a schema the database has not
migrated to yet.

---

## Phase 1: `ImportRun` record and failure-safe recording

### Overview

Add the model, and make `import_registry` write a run record that survives its
own rollback. Add a bounded network retry with a hard wall-clock ceiling.

### Changes Required:

#### 1. The run record model

**File**: `registry/models.py`

**Intent**: Persist one row per import attempt so the app can answer "when did a
refresh last succeed?" without asking the scheduler, and so a failed attempt
leaves evidence rather than silence.

**Contract**: An `ImportRun` model plus a `RunStatus` / `RunTrigger`
`TextChoices` pair, following the `SourceField` precedent already in this file.
Fields: `started_at` (indexed — every read orders on it), `finished_at`
(nullable), `status`, `trigger`, `attempts`, `source_as_of` (nullable — a failed
run never learned one), `error` (blank), and the `LoadStats` counters
(`products_loaded`, `products_created`, `products_inactive`,
`substances_created`, `links_created`, `products_without_links`), all nullable
because a failure has none of them. `Meta.ordering = ['-started_at']`, newest
first, since that is the only order any surface wants.

`trigger` distinguishes a scheduled execution from a hand-run one. It exists for
diagnosis only — the verdict in Phase 2 is deliberately trigger-agnostic — but
without it a manual import would make a dead cron look healthy.

#### 2. Migration

**File**: `registry/migrations/0002_importrun.py`

**Intent**: Create the table.

**Contract**: Generated by `makemigrations registry`; additive, no changes to
existing tables, so it is safe to apply ahead of the code that writes to it.

#### 3. Wire the record into the import command

**File**: `registry/management/commands/import_registry.py`

**Intent**: Open a run record at the top of `handle()`, close it as succeeded or
failed at the bottom, without ever putting either write inside the import's
transaction.

**Contract**: `handle()` creates the `ImportRun` before any of the existing
work, then wraps the download/import in `try/except CommandError/else`. The
success path stamps `finished_at`, `status`, `source_as_of` and the `LoadStats`
counters; the failure path stamps `finished_at`, `status` and `error` and
re-raises so the process still exits non-zero. A new `--trigger` option
(`manual` default, `scheduled` for the cron) records which. The existing
`--file`, `--url`, `--min-products`, `--keep-download` and `--allow-older`
options and every existing guard are unchanged.

The ordering is load-bearing: the `create()` must precede `_import()` (which
opens `transaction.atomic()` at line 147) and the failure `save()` must follow
the block unwinding, so both run in autocommit and neither is rolled back by the
guard at lines 153-161.

#### 4. Bounded download retry

**File**: `registry/management/commands/import_registry.py`

**Intent**: Stop a transient network blip on a ~74 MB transfer from costing a
whole day of freshness, without letting a run stretch far enough to collide with
the next scheduled one.

**Contract**: Three module constants — `DOWNLOAD_MAX_ATTEMPTS`,
`DOWNLOAD_RETRY_BACKOFF` (a short ascending sequence), and
`RUN_DEADLINE_SECONDS` — sized so the worst case stays orders of magnitude below
the 24 h schedule interval. `_download` retries only on
`requests.RequestException`; `OSError` (a full disk) fails immediately.
`RegistryParseError` is not retried because it is deterministic in the file.

**The min-products guard is not retried either, but not because it is
deterministic — on the URL path each attempt downloads a fresh temp file, so a
truncated transfer genuinely could differ next time.** It is not retried because
`stats.products_loaded < min_products` cannot distinguish a truncated download
from the source's `rodzajPreparatu` vocabulary changing — which is exactly what
the guard's own error message says (`import_registry.py:158-160`) — and
re-downloading 74 MB on a vocabulary change is pure waste. The failed run record
plus the printed `products_in_file` denominator are what let a human tell the
two apart afterwards.

`RUN_DEADLINE_SECONDS` gates **retry attempts**, not total wall clock: it is
checked before each retry, so a single hung transfer is bounded by
`DOWNLOAD_TIMEOUT`'s per-chunk read timeout rather than by this constant. Stated
plainly because the two are easy to confuse. The number of attempts made is
recorded on the run record.

#### 5. Tests

**File**: `registry/tests/test_import_run.py`

**Intent**: Prove the run record is written on both paths, and specifically that
a failure record survives the import transaction's rollback.

**Contract**: New test module following `test_loader.py`'s conventions — the
offline `--file` path against `registry/tests/fixtures/sample-products.xml`,
`override_settings` for the pinned registry URL, no live network. Cases: a
successful run records status, `source_as_of` and counters matching the
command's own summary; a run rejected by the min-products guard leaves a
`failed` row *and* leaves the database otherwise untouched; `--trigger` is
recorded.

### Success Criteria:

#### Automated Verification:

- Migration applies cleanly: `uv run python manage.py migrate`
- Migration state is complete: `uv run python manage.py makemigrations --check --dry-run`
- The failure-path test proves a `failed` row survives the guard's rollback
- Full suite passes: `uv run python manage.py test`
- Type checking passes: `uv run mypy`
- Django system checks pass: `uv run python manage.py check`

#### Manual Verification:

- A local `import_registry --file <fixture> --min-products 1` run creates one `success` row with counters matching the printed summary
- A deliberately bad `--url` produces a `failed` row carrying a readable error message

**Implementation Note**: After completing this phase and all automated
verification passes, pause here for manual confirmation from the human before
proceeding to the next phase.

---

## Phase 2: Freshness verdict and its two surfaces

### Overview

Derive one verdict from the run history and expose it in admin and as a
command. Both read the same function.

### Changes Required:

#### 1. The verdict

**File**: `registry/freshness.py` (new)

**Intent**: Answer "is the registry data fresh?" in exactly one place, so the
admin page and the status command can never disagree.

**Contract**: One named module constant `STALE_AFTER` = 48 hours, and a function
returning a small frozen dataclass carrying the most recent successful run's
timestamp, its `source_as_of`, the age, and an `is_stale` boolean. Stale means
*no successful run at all*, or an age exceeding `STALE_AFTER`.

`source_as_of` is carried for display and diagnosis but is deliberately **not**
part of the verdict: the decision was to collapse freshness to one number, and
that number is last-successful-run. The accepted consequence is recorded under
Open Risks in the brief. 48 h rather than the PRD's literal "about a day"
because it must tolerate the one dropped run and ±minutes drift the platform is
documented to produce, or the signal gets ignored as noise.

#### 2. Read-only admin

**File**: `registry/admin.py`

**Intent**: Give an operator the run history and the verdict at a glance,
following the read-only pattern this module already establishes.

**Contract**: An `ImportRunAdmin` registered on `ImportRun` with
`has_add_permission` / `has_change_permission` / `has_delete_permission`
returning `False` and `has_view_permission` deliberately left alone — the same
shape as `ProductAdmin`, and for the same reason. `list_display` covers status,
started/finished, trigger, `source_as_of` and the headline counters;
`list_filter` on status and trigger. The changelist injects the verdict via
`changelist_view`'s `extra_context`.

#### 3. Verdict banner template

**File**: `registry/templates/admin/registry/importrun/change_list.html` (new)

**Intent**: Render the verdict above the run list.

**Contract**: Extends `admin/change_list.html` and renders the injected verdict
in an existing block. App-level template directory, matching how `households`
ships its templates.

#### 4. Status command

**File**: `registry/management/commands/registry_status.py` (new)

**Intent**: Make freshness checkable without a browser session, and give future
alerting something to hang off with no code change — point a second cron at this
command and the platform's own failed-execution notifications carry it.

**Contract**: Prints the last successful run, its age, the snapshot date held,
and the verdict. Exits non-zero when stale by raising `CommandError` with the
same message, which is Django's own convention for a failing command. No
options; no new settings.

#### 5. Tests

**File**: `registry/tests/test_freshness.py` (new)

**Intent**: Pin the verdict at its boundaries and prove both surfaces agree.

**Contract**: Cases at and either side of `STALE_AFTER`; no runs at all reads as
stale; a `failed` run does not count as success; a successful run whose
`source_as_of` is old still reads fresh (the collapse-to-one-number decision,
asserted so a later reader does not "fix" it); **a recent `trigger=manual` run
reads fresh** — the verdict is deliberately trigger-agnostic, and without this
assertion the next reader adds a `trigger=scheduled` filter to it and no test
objects; `registry_status` exits non-zero when stale and zero when fresh.

### Success Criteria:

#### Automated Verification:

- Boundary tests pass at, just under, and just over `STALE_AFTER`
- `registry_status` exits non-zero when stale and zero when fresh
- Full suite passes: `uv run python manage.py test`
- Type checking passes: `uv run mypy`
- Django system checks pass: `uv run python manage.py check`

#### Manual Verification:

- `/admin/registry/importrun/` renders the run list with the verdict visible above it
- The admin page offers no add, change or delete affordance
- `uv run python manage.py registry_status` prints a readable summary locally

**Implementation Note**: After completing this phase and all automated
verification passes, pause here for manual confirmation from the human before
proceeding to the next phase.

---

## Phase 3: Railway cron service, configured in-repo

### Overview

Stand up a second Railway service that runs the import on a daily schedule,
with its schedule versioned in the repo. Step 1 is an empirical check, because
one part of this is genuinely unverified.

### Changes Required:

#### 1. Establish how a second service selects its config file

**File**: none (investigation), result recorded in `context/deployment/deploy-plan.md`

**Intent**: Settle the one unverified claim in this plan before building on it.

**Contract**: Determine, empirically, how a Railway service is pointed at a
config file other than the repo-root `railway.json`. Avenues, cheapest first:
Railway's GitHub-hosted markdown docs; `railway api` against the GraphQL schema
(a service-instance update field is the likely carrier); the dashboard's service
settings. Record what was found — including "could not be done from the CLI" if
that is the answer.

**Documented fallback so this phase cannot deadlock**: if the config path can
only be set in the dashboard, set it there and record it in `deploy-plan.md` as
an explicit non-code step, with the schedule still living in the committed file.
That keeps the schedule reviewable even when the pointer to it is not.

#### 2. Cron service config

**File**: `railway.cron.json` (new)

**Intent**: Version the schedule and the command the cron service runs.

**Contract**: `$schema` pointing at `https://railway.com/railway.schema.json`,
matching the existing `railway.json`. `deploy.startCommand` runs
`python manage.py import_registry --trigger scheduled`; `deploy.cronSchedule`
carries the daily expression; `deploy.restartPolicyType` is `NEVER` (a cron
execution that failed must not restart-loop — the enum value is confirmed
present in the fetched schema); no `healthcheckPath` and no `numReplicas`, both
of which are web-service concerns. The schedule should sit in the early morning
UTC, after the publisher's daily refresh, and must not be `@daily`-style
midnight where platform contention is worst.

Add `jsonschema` as a dev dependency with `uv add --dev jsonschema` (never pip —
`uv sync --locked` gates every PR and Railway's build) so criterion 3.1 has
something to validate with.

#### 3. Deploy the cron service from CI

**File**: `.github/workflows/deploy.yml`

**Intent**: Ship the cron service on the same merge that ships the web service.

**Contract**: A second `railway up --service <cron-service> --ci` step in the
existing `deploy` job, **after** the `web` step — the web service's
`startCommand` is what runs `migrate`, so reversing the order lets a cron
execution meet an unmigrated schema. Same `RAILWAY_TOKEN`, same pinned CLI
version, same `concurrency` group; the existing `paths-ignore` filter already
covers docs-only merges.

#### 4. Service variables

**File**: none in the repo — Railway service variables, recorded in `context/deployment/deploy-plan.md`

**Intent**: Give the cron service the environment `settings.py` reads at import
time, or it will fail before reaching the command.

**Contract**: `DATABASE_URL` (as the same `${{Postgres.DATABASE_URL}}` reference
the web service uses, so it resolves over private networking), `SECRET_KEY`,
`DEBUG`, `ALLOWED_HOSTS` and `REGISTRY_OVERALL_URL`. No new setting is
introduced by this change, so `.env.example` is unchanged.

#### 5. Document the deployed state

**File**: `context/deployment/deploy-plan.md`

**Intent**: Keep the post-deploy record honest about what is now running.

**Contract**: Add the cron service to the Railway resources table and its
variables to the wired-variables table; record the schedule and the config-path
mechanism (or the dashboard step, per the fallback); update the "Known gaps"
entry that currently says the daily ingestion cron is blocked on feature work.

### Success Criteria:

#### Automated Verification:

- `railway.cron.json` validates against the live schema. Fetch it at check time rather than trusting a local copy, and assert with `jsonschema` (added via `uv add --dev jsonschema`, never pip):
  `curl -sfL https://railway.com/railway.schema.json -o rw.schema.json && uv run python -c "import json,jsonschema; jsonschema.validate(json.load(open('railway.cron.json')), json.load(open('rw.schema.json')))"`
- CI `check` job stays green on the PR: `uv sync --locked`, `manage.py check`, `mypy`, `manage.py test`

#### Manual Verification:

- The cron service exists and its config file mechanism is confirmed and written down
- A manually triggered execution of the cron service completes and writes an `ImportRun` row with `trigger=scheduled`
- Reading the `deploy.yml` diff confirms the cron `railway up` step is sequenced after the `web` one
- `deploy-plan.md` reflects the new service, its variables, and the schedule

**Implementation Note**: After completing this phase and all automated
verification passes, pause here for manual confirmation from the human before
proceeding to the next phase.

---

## Phase 4: Production verification

### Overview

Confirm a genuinely scheduled execution — not a manual one — fires, lands, and
records. This is separate from Phase 3 because it cannot be checked until the
schedule has actually come around.

### Changes Required:

#### 1. Observe a real scheduled run

**File**: `context/changes/registry-freshness-refresh/production-verification.md` (new)

**Intent**: Record the first unattended run against F-01's production numbers,
so a future regression has a baseline to be measured against — the same role
`production-baseline.md` played for F-01.

**Contract**: Capture the scheduled execution's `ImportRun` row (timestamps,
trigger, counters, attempts) and compare the counters against
`context/archive/2026-08-07-registry-substance-data/production-baseline.md`
(20,245 products, 3,391 substances, 25,884 links on the 2026-08-13 snapshot).
Note the wall-clock gap between the configured schedule and the actual
`started_at`, since the platform does not guarantee execution to the minute.

#### 2. Close the risk-register row

**File**: `context/foundation/infrastructure.md`

**Intent**: The risk register names this exact mitigation; record that it is now
in place.

**Contract**: Update the "Daily ingestion cron skips runs silently" row's
mitigation to reference the shipped `ImportRun` record and the admin surface,
rather than describing them as something to build. Touch only that row.

### Success Criteria:

#### Automated Verification:

- `manage.py registry_status` against production exits zero within 48 h of the scheduled run

#### Manual Verification:

- A scheduled execution the operator did not trigger appears in `/admin/registry/importrun/` with `trigger=scheduled`
- Its counters are consistent with the F-01 production baseline
- `production-verification.md` records the run and the schedule-vs-actual drift
- `infrastructure.md`'s risk-register row reflects the shipped mitigation

---

## Testing Strategy

### Unit Tests:

- `ImportRun` written on the success path with counters matching `LoadStats`
- `ImportRun` written on the failure path **and surviving** the import
  transaction's rollback — the highest-value test in the change
- `--trigger` recorded correctly
- `STALE_AFTER` boundary: at, just under, just over
- No successful run at all reads as stale
- A `failed` run does not satisfy the verdict
- A successful run holding an old `source_as_of` still reads fresh — pinning the
  collapse-to-one-number decision so a later reader does not silently reverse it
- A recent `trigger=manual` run reads fresh — pinning the verdict as
  trigger-agnostic, so nobody quietly narrows it to scheduled runs only

### Integration Tests:

- `registry_status` exit code agrees with the admin verdict for the same data
- The whole import path end to end via the offline `--file` fixture, unchanged
  from F-01's existing coverage

### Manual Testing Steps:

1. Run the import locally against the fixture; confirm one `success` row.
2. Run it with a bad `--url`; confirm one `failed` row with a readable error and
   no change to `Product` counts.
3. Load `/admin/registry/importrun/`; confirm the verdict banner and the absence
   of any edit affordance.
4. Run `registry_status`; confirm exit 0 and a readable summary.
5. After Phase 3, trigger the cron service once by hand; confirm a
   `trigger=scheduled` row.
6. After the schedule fires unattended, repeat step 5's check without touching
   anything.

Network retry behaviour is deliberately **not** tested — mocking `requests`
would couple the tests to `_download`'s call shape without testing behaviour.
The retry is bounded by constants and a wall-clock deadline instead.

## Performance Considerations

The import measured ~6 s in production for download, parse and write, against a
24 h schedule interval — four orders of magnitude of headroom. That gap, not
`RUN_DEADLINE_SECONDS`, is the real reason a lock is unnecessary: the deadline
bounds retry attempts, while a single stalled transfer is bounded by
`DOWNLOAD_TIMEOUT`'s per-chunk read timeout. Both are far below the interval.
The `ImportRun`
table grows by one row per day; every read is a single indexed lookup on
`started_at`.

The one real cost is that each run re-downloads ~74 MB, because the publisher
serves no `ETag` and no `Last-Modified` (settled in F-01). Nothing in this plan
can avoid that.

## Migration Notes

`registry/migrations/0002_importrun.py` is purely additive — a new table, no
alterations to `Product`, `Substance` or `ProductSubstance` — so it applies
cleanly to the live database and needs no backfill. There is no historical run
data to import: the single production load F-01 performed is recorded in
`production-baseline.md`, not in the database, and deliberately stays there.

Rollback is a table drop; nothing else in the app reads `ImportRun`.

## References

- Roadmap item F-02: `context/foundation/roadmap.md:98-110`
- Platform cron behaviour: `context/foundation/infrastructure.md` § Unknown Unknowns, § Risk Register
- F-01's deferral of this work: `context/archive/2026-08-07-registry-substance-data/plan.md:104-106`
- F-01 ingestion research (cadence, no conditional GET): `context/archive/2026-08-07-registry-substance-data/options.md` §§ 2, 14
- Production numbers to compare against: `context/archive/2026-08-07-registry-substance-data/production-baseline.md`
- The transaction the run record must avoid: `registry/management/commands/import_registry.py:147-162`
- Read-only admin pattern to follow: `registry/admin.py`
- Deploy pipeline: `.github/workflows/deploy.yml`, `context/deployment/deploy-plan.md`

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles. See `references/progress-format.md`.

### Phase 1: `ImportRun` record and failure-safe recording

#### Automated

- [x] 1.1 Migration applies cleanly: `uv run python manage.py migrate` — 679264a
- [x] 1.2 Migration state is complete: `uv run python manage.py makemigrations --check --dry-run` — 679264a
- [x] 1.3 The failure-path test proves a `failed` row survives the guard's rollback — 679264a
- [x] 1.4 Full suite passes: `uv run python manage.py test` — 679264a
- [x] 1.5 Type checking passes: `uv run mypy` — 679264a
- [x] 1.6 Django system checks pass: `uv run python manage.py check` — 679264a

#### Manual

- [x] 1.7 A local `import_registry --file <fixture> --min-products 1` run creates one `success` row with counters matching the printed summary — 679264a
- [x] 1.8 A deliberately bad `--url` produces a `failed` row carrying a readable error message — 679264a

### Phase 2: Freshness verdict and its two surfaces

#### Automated

- [x] 2.1 Boundary tests pass at, just under, and just over `STALE_AFTER` — 3bc60ac, hardened at e568d69 (the exact-boundary test was flaky as first landed — ~60% failure rate on repeated local runs — fixed at 3f4b3f8; RUNNING-doesn't-count-as-fresh case added at e568d69)
- [x] 2.2 `registry_status` exits non-zero when stale and zero when fresh — 3bc60ac
- [x] 2.3 Full suite passes: `uv run python manage.py test` — verified green (103 tests) as of e568d69, run 3x with no flakes after the fixes above
- [x] 2.4 Type checking passes: `uv run mypy` — 3bc60ac
- [x] 2.5 Django system checks pass: `uv run python manage.py check` — 3bc60ac

#### Manual

- [x] 2.6 `/admin/registry/importrun/` renders the run list with the verdict visible above it — 3bc60ac
- [x] 2.7 The admin page offers no add, change or delete affordance — 3bc60ac
- [x] 2.8 `uv run python manage.py registry_status` prints a readable summary locally — 3bc60ac

### Phase 3: Railway cron service, configured in-repo

#### Automated

- [x] 3.1 `railway.cron.json` validates against the live schema via `jsonschema` — 164e91c
- [x] 3.2 CI `check` job stays green on the PR: `uv sync --locked`, `manage.py check`, `mypy`, `manage.py test` — 164e91c. **Caveat:** verified as the identical local commands, not an actual PR run (no PR was opened this session); the branch was never pushed. Push + open a PR to close this against the letter of the criterion.

#### Manual

- [x] 3.3 The cron service exists and its config file mechanism is confirmed and written down — service provisioned 2026-08-16 with explicit go-ahead; `railwayConfigFile` confirmed live against the deployment's own resolved manifest (not just set), see deploy-plan.md
- [x] 3.4 A manually triggered execution of the cron service completes and writes an `ImportRun` row with `trigger=scheduled` — closed 2026-08-16 after merge (`c506ae5`) redeployed `web` (ran the migration) and `registry-import-cron`. Re-triggered via the dashboard's "Cron Runs → Run now": **succeeded** in 15s, real production numbers (20,242 products, 0 new, 3 newly inactive, 25,879 links, 97.2% resolved). Confirmed by construction, not direct DB read (no production admin credentials on hand): `handle()` calls `run.save()` for the success path *before* `_report()` prints the summary (`import_registry.py`), so the printed summary in the deployment logs is proof the row landed. First attempt (pre-merge) crashed — see deploy-plan.md's "Registry import cron" section for that finding.
- [x] 3.5 Reading the `deploy.yml` diff confirms the cron `railway up` step is sequenced after the `web` one — 164e91c
- [x] 3.6 `deploy-plan.md` reflects the new service, its variables, and the schedule — 164e91c

### Phase 4: Production verification

#### Automated

- [ ] 4.1 `manage.py registry_status` against production exits zero within 48 h of the scheduled run

#### Manual

- [ ] 4.2 A scheduled execution the operator did not trigger appears in `/admin/registry/importrun/` with `trigger=scheduled`
- [ ] 4.3 Its counters are consistent with the F-01 production baseline
- [ ] 4.4 `production-verification.md` records the run and the schedule-vs-actual drift
- [ ] 4.5 `infrastructure.md`'s risk-register row reflects the shipped mitigation
