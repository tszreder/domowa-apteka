<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: Registry Freshness Refresh (F-02)

- **Plan**: `context/changes/registry-freshness-refresh/plan.md`
- **Scope**: Full plan — Phases 1–4 of 4 (all Progress items `[x]`)
- **Date**: 2026-08-20
- **Verdict**: APPROVED — all 5 findings triaged and resolved 2026-08-20
- **Findings**: 0 critical, 2 warnings, 3 observations

## Method note

The skill body prescribes two `general-purpose` sub-agents. This session's harness
rule ("do not call the Agent tool unless the user requested it") takes precedence,
so the drift scan, safety/quality scan and pattern comparison were run inline.
Same coverage, no delegation.

## Evidence gathered

Automated criteria re-run live at review time (not trusted from the Progress notes):

| Command | Result |
|---|---|
| `uv run python manage.py makemigrations --check --dry-run` | `No changes detected` — exit 0 |
| `uv run python manage.py check` | `no issues (0 silenced)` — exit 0 |
| `uv run mypy` | `Success: no issues found in 57 source files` |
| `uv run python manage.py test` | `Ran 150 tests … OK` |
| `test_freshness` + `test_import_run` ×3 | `Ran 19 tests … OK` ×3 — the documented flake (3f4b3f8, e568d69) is genuinely fixed |
| `curl` live schema + `jsonschema.validate(railway.cron.json)` | VALID against `https://railway.com/railway.schema.json` |
| `gh pr checks 21` / `gh pr checks 23` | `check` = **pass** on both real PR runs |

Git scope: `a0c4e70..5dedf28`, filtered to the F-02 commits (`13c027c` is
unrelated). Code surface: `registry/models.py`, `registry/migrations/0002_importrun.py`,
`registry/management/commands/import_registry.py`, `registry/management/commands/registry_status.py`,
`registry/freshness.py`, `registry/admin.py`,
`registry/templates/admin/registry/importrun/change_list.html`,
`registry/tests/{test_import_run,test_freshness,test_loader}.py`,
`.github/workflows/deploy.yml`, `railway.cron.json`, `pyproject.toml`, `uv.lock`,
plus `context/deployment/deploy-plan.md`, `context/foundation/infrastructure.md`,
`context/changes/registry-freshness-refresh/production-verification.md`.

**The transaction trap — the plan's self-named "single most likely defect" — is
correctly handled and non-vacuously tested.** `ImportRun.objects.create()` sits at
`import_registry.py:110`, before `_run_import()`; both the failure `save()`
(`:122`) and the success `save()` (`:135`) execute after the `try` block unwinds,
in autocommit. `test_failure_leaves_a_failed_row_and_no_data`
(`registry/tests/test_import_run.py:61`) is discriminating rather than vacuous: it
asserts `Product.objects.count() == 0` **and** the `failed` row's survival in the
same test, so it proves the rollback genuinely fired and the run record outlived it.

**Criterion 4.5 verified directly.** `infrastructure.md`'s "Daily ingestion cron
skips runs silently" row was rewritten in `cabd20c` to cite the shipped
`ImportRun` / `get_verdict()` / `registry_status` mitigation and the three
production fires. Only that row changed. Not a rubber-stamp.

**Criterion 3.4 / 4.1 chain holds.** `railway.cron.json`'s `startCommand` literally
carries `--trigger scheduled`, and `import_registry.py`'s `--trigger` default is
`manual`, so the "confirmed by construction" argument for `trigger=scheduled` is
sound. It is independently corroborated by the live `registry_status` run in
production (exit 0, timestamp matching Run 3 to the second).

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| Plan Adherence | WARNING |
| Scope Discipline | WARNING |
| Safety & Quality | PASS |
| Architecture | PASS |
| Pattern Consistency | PASS |
| Success Criteria | PASS |

► **Overall: APPROVED** — no critical findings; two minor warnings, both about
configuration hygiene rather than shipped behaviour.

## Findings

### F1 — `REGISTRY_OVERALL_URL` drift guarded only by a doc note pointing the wrong way

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Plan Adherence
- **Location**: `context/deployment/deploy-plan.md:403-405,487`; `domowa_apteka/settings.py:79`
- **Detail**: Plan Phase 3 §4 contracts five service variables on the cron service,
  including `REGISTRY_OVERALL_URL`. Two (`ALLOWED_HOSTS`, `REGISTRY_OVERALL_URL`)
  were deliberately left unset, with reasoning recorded — legitimate as a
  documented deviation, and both services currently resolve to the same in-code
  default, so nothing is broken today. The residual problem is the mitigation's
  direction: `deploy-plan.md:487` says "**if this is ever set on `web`**, set it
  identically on the cron service". But `web` never runs `import_registry` — the
  cron service is the variable's only consumer. Someone bumping the export version
  the obvious way (change it on `web`, where all the other app config lives) would
  see the URL change take **no effect at all**, while the cron keeps importing the
  old version. The `settings.py` comment promising "a variable change, not a code
  deploy" is what makes that the natural move.
- **Fix A ⭐ Recommended**: Set `REGISTRY_OVERALL_URL` explicitly on the cron
  service now (to the current 6.0.0 URL), and rewrite `deploy-plan.md:487` to say
  the cron service is the authoritative place to set it.
  - Strength: Turns a "remember to do two things in the right order" note into a
    single obvious location; the variable becomes visible in the dashboard on the
    service that actually reads it.
  - Tradeoff: One more explicitly-pinned variable to update on an export-version
    bump; the in-code default and the set value can themselves diverge.
  - Confidence: HIGH — mechanism already used for the cron's other three
    variables (`deploy-plan.md:394-396`); no code change.
  - Blind spot: Setting a variable triggers a redeploy unless `--skip-deploys` is
    passed; not verified whether that matters for a cron-scheduled service.
- **Fix B**: Leave both unset and only fix the note's direction in `deploy-plan.md`.
  - Strength: Zero production touch; keeps the single source of truth in code.
  - Tradeoff: Still relies on a human reading the right doc line at the right
    moment — the same failure mode, only better worded.
  - Confidence: MEDIUM — correct as far as it goes, but doc-only.
  - Blind spot: None significant.
- **Decision**: FIXED via Fix A, in two parts. Doc half applied by this review:
  `deploy-plan.md`'s variable row now names `registry-import-cron` as the only
  service the variable has any effect on, and spells out the set-then-redeploy
  command. Production half run **by the user**, 2026-08-20 — this session's
  permission classifier blocked every `railway variable` invocation (read-only
  `list` included), so `railway variable set 'REGISTRY_OVERALL_URL=<6.0.0 URL>'
  --service registry-import-cron --skip-deploys` was executed by hand and
  returned without error. The value pinned is identical to `settings.py`'s
  in-code default, so no behaviour changed; the variable is now visible and
  editable on the service that reads it.

### F2 — `deploy.yml` overclaims what step ordering guarantees about migrations

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Adherence
- **Location**: `.github/workflows/deploy.yml:87-93`
- **Detail**: The comment says deploying `web` first "guarantees the cron service
  can never execute against a schema the database has not migrated to yet". Step
  ordering does not deliver that guarantee: `railway up --ci` streams the *build*
  log and exits, while `migrate --noinput` runs later, at container start. The
  actual safety margin comes from two facts recorded in `deploy-plan.md` but not
  in the workflow — a `railway up` against a cron-scheduled service is
  `buildOnly: true` and never executes `startCommand`, and the next execution is
  hours away at the 23:05 UTC tick. The 2026-08-16 `relation "registry_importrun"
  does not exist` crash is the empirical proof that this hazard is real. A future
  reader who trusts the word "guarantees" could reorder the steps or add a
  post-deploy trigger and reintroduce the failure.
- **Fix**: Reword the comment to state the real mechanism — cron `railway up` is
  build-only and the next execution is a schedule tick away, so `web`'s
  start-command migration lands first in practice — and cross-reference
  `deploy-plan.md`'s "Registry import cron" section.
- **Decision**: FIXED — comment reworded to name the real mechanism
  (`railway up` returns at build completion, cron deploys are `buildOnly: true`,
  the next execution is a schedule tick away) and to cross-reference
  `deploy-plan.md` § "Registry import cron". Behaviour unchanged; `web` stays
  first.

### F3 — Cron schedule moved off the plan's stated window on a different rationale

- **Severity**: 💬 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Adherence
- **Location**: `railway.cron.json:5`; `b0046a5`
- **Detail**: Plan Phase 3 §2 specifies a schedule that "should sit in the early
  morning UTC, after the publisher's daily refresh, and must not be `@daily`-style
  midnight". The implementation landed at `17 3 * * *` (compliant), then `b0046a5`
  moved it to `5 23 * * *` (23:05 UTC) with a rationale about reading as 00:05 CET
  — a local-time preference, not the publisher-refresh constraint the plan named.
  The constraint does hold empirically: all three production runs at 23:05 UTC
  fetched a same-day `stanNaDzien` (`production-verification.md:38,54,67`), and
  23:05 UTC is off the midnight-contention mark. So this is a rationale gap in the
  record, not a live defect.
- **Fix**: Add one line to `deploy-plan.md`'s cron section noting that the 23:05 UTC
  slot was confirmed to land after the publisher's daily refresh (same-day
  `stanNaDzien` on three consecutive fires), so the plan's original constraint is
  met and not merely abandoned.
- **Decision**: FIXED differently — the user chose to restore the plan's window
  rather than document the deviation. `railway.cron.json`'s `cronSchedule` is
  back to `17 3 * * *` (03:17 UTC), re-validated against the live schema.
  `deploy-plan.md` now carries a full schedule history (landed 03:17 → moved to
  23:05 on 2026-08-17 for a local-time reason → reverted 2026-08-20), the
  `deploy.yml` comment's tick reference was updated, and the stale "Known gaps"
  entry (still describing Phase 4 as outstanding) was corrected.
  **New open item raised by this change**: the three production fires only prove
  the day's snapshot is up by *23:05* UTC. Whether it is up by 03:17 UTC is
  untested, and a run that lands too early loads the previous day's snapshot
  without failing (`_reject_older_snapshot` compares `<`) and without reading
  stale (the verdict keys on run time, not snapshot date). Recorded in
  `deploy-plan.md`; verify the first fire's `stanNaDzien` against its run date.
  This is a live production config change and needs a deploy to take effect.

### F4 — The change's own records lag the work that actually shipped

- **Severity**: 💬 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Adherence
- **Location**: `context/changes/registry-freshness-refresh/plan.md:646`;
  `context/changes/registry-freshness-refresh/change.md:4-6`
- **Detail**: Two places where the paperwork stopped short of the shipped state.
  (a) The Progress note on criterion 3.2 still reads "verified as the identical
  local commands, not an actual PR run (no PR was opened this session); the branch
  was never pushed. Push + open a PR to close this against the letter of the
  criterion." Honest when written, but PR #21 (carrying Phase 3's `164e91c`) and
  PR #23 both merged with `check` = **pass** — verified live via `gh pr checks`.
  The criterion is met against its letter; only the note is stale, and the next
  reader inherits an open item that is actually closed. (b) `change.md` sat at
  `status: planned` / `updated: 2026-08-14` while all four phases were
  implemented, merged (PRs #21–#24) and production-verified through 2026-08-19 —
  it never transitioned through `implementing` / `implemented`, so `/10x-status`
  and `/10x-archive` would have read this as un-started work. This review has
  already stamped it `impl_reviewed` / `2026-08-20`; recorded here so the stamp
  does not launder the gap.
- **Fix**: Replace the 3.2 caveat with the settled evidence — `check` passed on
  PR #21 (run 31974387952) and PR #23 (run 31975233535). The `change.md` half needs
  no further action beyond the stamp already applied; the carry-forward is to
  advance `change.md` at each phase close rather than only at review time.
- **Decision**: FIXED — `plan.md`'s 3.2 Progress note now cites the two passing
  PR runs (#21 / 31974387952, #23 / 31975233535) instead of the superseded
  caveat. `change.md` stamped `impl_reviewed` / `2026-08-20` by this review.

### F5 — Two changes outside the plan's "Changes Required" lists, both benign

- **Severity**: 💬 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Scope Discipline
- **Location**: `railway.cron.json:7`; `registry/tests/test_loader.py:355,369,380-392,409`
- **Detail**: (a) `deploy.region: "europe-west4-drams3a"` was added to
  `railway.cron.json` in `0ba2b83`. Plan §2's contract enumerates what to omit
  (`healthcheckPath`, `numReplicas`) but never mentions `region`; the pin matches
  `web`'s and the reasoning (transatlantic RTT on a 74 MB download plus writes to
  `postgres.railway.internal`) is recorded in `deploy-plan.md`. Sound addition.
  (b) `test_loader.py` was modified in Phase 1 (sleep patched out in three
  `DownloadPathTests`, one new retry-ceiling test) though the plan lists only
  `test_import_run.py` as new. This is the unavoidable consequence of §4's retry
  loop landing in a path those tests already exercised, and the added test pins
  `DOWNLOAD_MAX_ATTEMPTS` without coupling to `_download`'s call shape. Neither is
  scope creep in substance — flagged only so the plan-vs-diff record is honest.
- **Fix**: Add both to the plan as a short addendum under Phase 3 §2 and Phase 1 §5
  — the `region` pin with its transatlantic-RTT rationale, and `test_loader.py` as
  a file Phase 1's retry loop necessarily touches — so a future plan-vs-diff read
  finds no unexplained files.
- **Decision**: FIXED — three addenda added to `plan.md`: `test_loader.py` under
  Phase 1 §5, the `deploy.region` pin under Phase 3 §2, and (raised by F3's fix)
  the schedule's move-and-revert history under the same section.

## What was checked and found clean

- **Safety & Quality** — no injection surface (no raw SQL; all ORM), no hardcoded
  secrets (`SECRET_KEY` / `DATABASE_URL` wired as Railway *references*, never
  values), no new authn/authz boundary. `ImportRunAdmin` follows `ProductAdmin` /
  `SubstanceAdmin` exactly: add/change/delete denied, `has_view_permission`
  deliberately untouched. Every read is a single indexed lookup on `started_at`;
  no N+1 (the one inline that could have had one, `ProductSubstanceInline`, already
  carries `select_related`). Retry bounded by `DOWNLOAD_MAX_ATTEMPTS`,
  `DOWNLOAD_RETRY_BACKOFF` and `RUN_DEADLINE_SECONDS`, with the attempts-vs-
  wall-clock distinction stated in the code. `OSError` deliberately not retried.
- **Architecture** — `freshness.py` is the single verdict source; `admin.py` and
  `registry_status.py` both call `get_verdict()`, and the template comment says so.
  Policy stays out of `loader.py` (`_reject_older_snapshot` lives in the command,
  as F-01 established). `RunStatus.RUNNING` correctly excluded from the verdict,
  with `test_a_running_run_does_not_count_as_success` pinning it.
- **Pattern Consistency** — `TextChoices` follows the `SourceField` precedent;
  migration is additive and auto-generated; `CommandError` for non-zero exit is
  Django's own convention; app-level template dir matches `households`.
- **Success Criteria** — every automated criterion re-run green at review time; the
  documented ~60% flake in the exact-boundary test is fixed (frozen `now` patched
  into `registry.freshness.timezone.now`) and survived three consecutive runs.
  All twelve Phase 2 cases the plan names exist by name in `test_freshness.py`,
  including `test_a_failed_run_does_not_count_as_success`, both
  `registry_status` exit-code cases, and
  `test_agrees_with_the_admin_verdict_for_the_same_data`.
  Manual criteria carry real evidence: `production-verification.md` records three
  unattended fires via `deploymentInstanceExecutions` with counters within a few
  products of the F-01 baseline and 97.2% resolved throughout, plus a live
  `registry_status` read from production's console.
