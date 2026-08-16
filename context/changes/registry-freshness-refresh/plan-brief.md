# Registry Freshness Refresh (F-02) — Plan Brief

> Full plan: `context/changes/registry-freshness-refresh/plan.md`

## What & Why

Put the daily registry import on a schedule, and give the app its own record of
every import attempt. The platform's cron **silently drops** a run when the
previous execution is still active and fires ±minutes late — documented in
`context/foundation/infrastructure.md`. So neither "the cron is scheduled" nor
"the cron fired" is evidence the substance data a user is reading is current.
Only an app-side last-successful-run record is.

## Starting Point

F-01 shipped `manage.py import_registry` — idempotent, ~6 s in production,
verified twice against the same snapshot. It deliberately stopped short: its
plan states *"No `ImportRun` / snapshot model… F-02 owns the run record and the
scheduler"*. Today nothing records that an import ran, nothing schedules one,
and the only production load was a hand-run one-off via a temporary
`startCommand` since reverted.

## Desired End State

A Railway cron service runs the import once a day. Every attempt writes an
`ImportRun` row — including failures, which survive the import's own transaction
rollback. One freshness verdict, derived from the last *successful* run against
a single 48-hour constant, is readable in the Django admin and from
`manage.py registry_status`, which exits non-zero when stale.

## Key Decisions Made

| Decision | Choice | Why (1 sentence) |
| --- | --- | --- |
| Trigger | Railway cron service (2nd service, same repo) | Native GA cron was an explicit platform-selection criterion, and it keeps a 74 MB download and a mutating job off the web dyno users browse. |
| Schedule config | In-repo `railway.cron.json`, with a documented unverified caveat | `deploy.cronSchedule` is confirmed in the official schema; how a 2nd service *selects* a non-root config file is not, so Phase 3 settles it empirically with a dashboard fallback. |
| Run record shape | `ImportRun` log table, one row per attempt | Only a history distinguishes "never ran" from "ran and failed" from "ran fine, publisher had nothing new" — and a skipped cron shows up as a gap between rows. |
| Failure handling | Record the failure, retry the download within the run, exit non-zero | A transient blip on 74 MB shouldn't cost a day of freshness; the non-zero exit keeps the platform's own execution log honest. |
| Headline freshness | Last-successful-run only; `source_as_of` recorded but not in the verdict | User chose to collapse freshness to one number — see Open Risks for what that accepts. |
| Staleness threshold | 48 h, one named constant | Must tolerate the one dropped run and ±minutes drift the platform is documented to produce, or the signal gets ignored as noise. |
| Overlap protection | Hard wall-clock ceiling, no lock | ~6 s against a 24 h interval means a lock guards a scenario that can't occur, and a stale lock would reintroduce the exact silent-skip failure being eliminated. |
| Alerting | Seam only — verdict function + non-zero-exit command | Real alerting becomes a config change (point a 2nd cron at the command) rather than a code change, without pulling SMTP credentials into this change. |
| Surfacing | Django admin (+ the status command) | `infrastructure.md`'s own mitigation names admin; S-02 isn't built, so there is no user-facing screen to warn on yet. |
| Test depth | Run record + verdict boundaries, no network mocks | Covers the transaction trap and off-by-one thresholds via F-01's existing offline fixture path. |

## Scope

**In scope:** `ImportRun` model + migration; failure-safe run recording in
`import_registry`; bounded download retry; a freshness verdict module; read-only
`ImportRun` admin with a verdict banner; `manage.py registry_status`; a Railway
cron service configured in-repo and deployed from CI; production verification.

**Out of scope:** alerting (email/webhook); a user-facing staleness banner
(S-02/S-03); locks or mutexes; conditional GET or delta ingestion (settled
impossible in F-01); any change to parsing, normalization or the substance
model; `ImportRun` retention policy.

## Architecture / Approach

```
Railway cron service ──daily──> manage.py import_registry --trigger scheduled
                                        │
              ImportRun.create()  ───────┤  (autocommit, BEFORE the transaction)
                                        │
                              transaction.atomic()  ← existing F-01 import
                                        │              guards raise in here
              ImportRun.save(ok|failed) ┘  (autocommit, AFTER it unwinds)
                                        │
                          registry/freshness.py  ── STALE_AFTER = 48h
                                   │        │
                        admin changelist    manage.py registry_status
                          (verdict banner)   (exit != 0 when stale)
                                                      │
                                            future: 2nd cron → alert
```

The load-bearing detail: `import_registry.py:147` and `loader.py:89` both open
transactions and the min-products guard raises *inside* them, so a naively
placed failure record would roll itself back — destroying exactly the evidence
this change exists to capture.

## Phases at a Glance

| Phase | What it delivers | Key risk |
| --- | --- | --- |
| 1. Run record | `ImportRun` model, failure-safe recording, bounded retry | The transaction trap — a failure record written in the wrong scope silently vanishes |
| 2. Verdict + surfaces | `freshness.py`, read-only admin, `registry_status` | Threshold logic duplicated between the two surfaces and drifting apart |
| 3. Cron service | `railway.cron.json`, CI deploy step, service variables | How a 2nd service selects a non-root config file is **unverified**; deploy order matters (web migrates first) |
| 4. Production verification | First unattended run recorded and compared to F-01's baseline | Can only be checked after the schedule actually fires |

**Prerequisites:** F-01 shipped and archived (done); Railway project access for a
second service; `RAILWAY_TOKEN` already in GitHub Actions secrets.
**Estimated effort:** ~2–3 sessions across Phases 1–3, plus a wait of at least
one schedule interval before Phase 4 can close.

## Open Risks & Assumptions

- **Accepted blind spot from collapsing to one number.** With last-successful-run
  as the sole headline, a publisher that quietly stops updating for a week reads
  as perfectly healthy. `source_as_of` is recorded on every run so the cause is
  diagnosable, but it will not raise the verdict. Deliberate; revisit if the
  publisher ever proves unreliable.
- **Unverified:** how a second Railway service is pointed at a config file other
  than the repo-root `railway.json`. `deploy.cronSchedule` and
  `restartPolicyType: NEVER` *are* confirmed against the official schema
  (fetched 2026-08-14). Phase 3 step 1 resolves the rest empirically, with a
  documented dashboard fallback so it cannot deadlock. Flagged rather than
  omitted, per `lessons.md` § "Verify a platform limitation before registering
  it as a risk".
- **Deploy ordering is a real hazard.** Only the web service's `startCommand`
  runs `migrate`; deploying the cron service first would let an execution meet
  an unmigrated schema.
- **48 h is looser than the PRD's literal "about a day".** Chosen so one dropped
  run does not cry wolf; a two-day-old snapshot will read healthy.
- **Every run re-downloads ~74 MB.** No `ETag`, no `Last-Modified` — settled in
  F-01, unavoidable.

## Success Criteria (Summary)

- An operator can answer "when did the registry data last refresh successfully?"
  from the admin, without inspecting the scheduler.
- A failed or skipped import is visible after the fact rather than leaving
  silence — including a failure the import's own rollback would otherwise erase.
- The import runs unattended on a schedule, and the first run nobody triggered
  is recorded and matches F-01's production numbers.
