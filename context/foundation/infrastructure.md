---
project: domowa-apteka
researched_at: 2026-08-03
recommended_platform: Railway
runner_up: Azure (Container Apps)
context_type: mvp
tech_stack:
  language: python
  framework: django
  runtime: uv
---

> **Confirmatory re-run (2026-08-03).** Railway was chosen on 2026-07-31 and has
> been live since 2026-08-01, so the platform decision was not reopened — the
> runner-up and third place are recorded history, not live candidates. What this
> run did was re-verify every Railway claim against the deployed system and CLI
> `5.30.3`, and rewrite the cross-check and risk register with evidence instead
> of speculation. **Five claims from the 2026-07-31 version were empirically
> false and are corrected below**; each correction is marked ⚠︎ with what was
> actually observed. Rows for Azure, Render, Fly.io, Vercel, Cloudflare and
> Netlify were **not** re-researched this run and still carry 2026-07-31 dates.

## Recommendation

**Deploy on Railway.** — confirmed in production, not just on paper.

Railway was selected because it was the only researched platform matching every
hard constraint at once: automatic `uv.lock` detection with no Dockerfile,
genuinely co-located managed Postgres, GA native cron for the daily registry
ingestion, and a fully scriptable deploy/log loop. The live deployment has now
validated the load-bearing parts of that claim: the build detected `uv.lock` and
ran `uv sync --locked --no-dev` with no Dockerfile, `DATABASE_URL` resolves over
private networking to the co-located Postgres, and the whole operational loop
(deploy, logs, variables, scale, rollback) has been driven from the CLI and
public API without opening the dashboard once.

Two of the original reservations turned out to be **wrong in the project's
favour** — in-place region migration is trivial, and the MCP server shipped —
and one previously invisible risk turned out to be **worse than anything on the
original register**: the Postgres volume has no backups.

## Platform Comparison

| Platform | CLI-first | Managed/Serverless | Agent-readable docs | Stable deploy API | MCP/Integration | Total |
|---|---|---|---|---|---|---|
| **Railway** (verified 2026-08-03) | Pass | Pass | Pass | Pass | Pass ⚠︎ was Partial | **5/5** |
| Azure (Container Apps) | Pass | Pass | Pass | Pass | Pass | 5/5 |
| Render | Partial | Pass | Fail | Partial | Pass | 3/5 |
| Fly.io | Pass | Partial | Pass | Partial | Partial | 3/5 |
| Vercel | Pass | Partial | Fail | Partial | Pass | 3/5 |
| Cloudflare | Pass | Fail (Django needs Paid-plan Containers) | Pass | Pass | Pass | dropped — hard constraint |
| Netlify | Pass | Fail (no Python function runtime at all) | Pass | Pass | Pass | dropped — hard constraint |

Only the Railway row was re-scored on 2026-08-03. All other rows are carried
forward unchanged from 2026-07-31 and should be treated as that date's research.

### What changed in Railway's score

**MCP/Integration: Partial → Pass.** The 2026-07-31 note read "MCP server is
explicitly *work in progress* — no first-class structured tool access yet,
CLI-only for agent-driven ops." Railway now ships **two** MCP variants:
`railway mcp install` writes the server config into Claude Code / Cursor /
OpenCode / Codex, and `railway mcp proxy` fronts the hosted remote server at
`mcp.railway.com` using the CLI login. `railway setup agent -y` installs Railway
skills alongside it. Destructive operations are excluded from the default
toolset; `redeploy` and `accept-deploy` are flagged destructive and require
confirmation — which matches this project's human-on-irreversibles posture.

**Status caveat (checked 2026-08-03):** Railway's own docs still say "The
Railway MCP Server is a work in progress. We are actively adding more tools and
features." The capability has shipped and is installable; the vendor has not
declared it GA. Scored Pass on capability, tracked as non-GA in the risk register.

### Corrections to the 2026-07-31 research

| # | 2026-07-31 claim | Verified reality (2026-08-03) |
|---|---|---|
| 1 | "no easy in-place region migration later"; moving "meant re-provisioning the database and re-pointing DNS during a maintenance window" | ⚠︎ **False.** Two `railway scale` commands moved both services `sfo` → `ams` in place. No re-provisioning, no DNS change, domain and private networking unchanged. Railway's docs: "The region of a service can be changed at any time, without any changes to your domain, private networking, etc." |
| 2 | "Nixpacks auto-detects `uv.lock`" | ⚠︎ **Wrong builder.** The live service manifest reports `"builder": "RAILPACK"`, and Railway's build docs now state "Railway uses Railpack to build your code." The `uv.lock` auto-detection claim holds — the builder name did not. |
| 3 | "MCP server is WIP — no structured agent tool access" | ⚠︎ **Stale.** Local + remote MCP both ship (see above). Vendor still labels it WIP. |
| 4 | "No free tier — Hobby's $5/mo is real spend from day one" | ⚠︎ **Partly stale.** A Free plan now exists at $0/mo with $1 monthly credit. It does not change the recommendation: $1 will not cover an always-on Django process plus a Postgres volume, so Hobby at $5/mo remains the realistic floor. |
| 5 | Rollback = "`railway deployment list` … then `railway redeploy <deployment-id>`" | ⚠︎ **That command does not exist.** `railway redeploy` accepts no deployment-ID argument — it only redeploys *latest* (`--from-source` re-pulls the source instead). Real rollback is the public API mutation `deploymentRollback(id: String!)`, with `Deployment.canRollback` as a pre-check. See the operational story. |

### Shortlisted Platforms

#### 1. Railway (Recommended — deployed and verified)

Railpack auto-detects `uv.lock` and runs `uv sync --locked --no-dev` with no
Dockerfile — confirmed in the live build. Native Cron Jobs fit the once-daily
ingestion job. Postgres is first-party and co-located on the same project and
bill — genuine co-location, confirmed by `DATABASE_URL` resolving to
`postgres.railway.internal` over private networking. The CLI plus the public
GraphQL API (`railway api`) covers the entire operational loop including
region moves, rollback, and volume backup scheduling. Docs are markdown on
GitHub. Remaining weak point: the only EU region is Amsterdam — confirmed
against the live region list, which returns exactly one EU location (`ams` /
`europe-west4-drams3a`). Measured impact is small: `/health/` responds in
~90 ms from Poland, down from ~292 ms in `sfo`.

#### 2. Azure Container Apps (Runner-up — recorded, not re-researched)

Scored identically well on the five criteria as of 2026-07-31: GA Container
Apps Jobs (KEDA cron), managed Postgres Flexible Server (GA in Poland Central
since Sept 2023 — the only shortlisted option with a Poland-local region),
open-source markdown docs, scriptable `az` CLI, and a broad MCP Server. What
tipped it to runner-up: `uv` support in Azure's Oryx build system is newer and
less battle-tested than pip, and setup requires wiring 3–4 distinct resources
versus Railway's single project — a real risk against a 1-week deadline with no
slack. That deadline reasoning is now moot (the deploy is done), but the
resource-surface argument would still apply to a migration.

#### 3. Render (recorded, not re-researched)

Strong native Django support and a mature MCP server, plus GA Cron Jobs.
Passed over because its docs aren't agent-readable (web-only, no GitHub
markdown source) and its free-tier Postgres expires 30 days after creation — a
poor fit for a household app meant to keep data long-term.

## Anti-Bias Cross-Check: Railway (post-deployment)

The three lenses were re-run against the deployed system rather than against a
proposal. Items the deployment **disproved** are struck through and explained;
items it **confirmed or newly surfaced** are stated with evidence.

### Devil's Advocate — Weaknesses

1. **No automatic volume backups, and the project has none configured.**
   `volumeInstanceBackupScheduleList` returns `[]` for the live
   `postgres-volume`. Railway's backup schedules are opt-in (Daily/6 days,
   Weekly/1 month, Monthly/3 months); nothing is enabled by default. Every row
   of household medicine data currently exists in exactly one place. This is the
   single highest-impact finding of this re-run and did not appear on the
   original register, which predates the volume existing.
2. **Restore is documented as a dashboard-only flow.** The docs describe
   locating a backup in the Backups tab and clicking restore — no CLI path is
   documented. The public API *does* expose `volumeInstanceBackupRestore`, so it
   is scriptable, but the undocumented path is the one an agent would have to
   discover under incident pressure.
3. **No rollback verb in the CLI.** Rollback exists only as a raw API mutation.
   An operator reaching for `railway rollback` finds nothing, and the obvious
   substitute (`railway redeploy`) silently redeploys *latest* — i.e. re-applies
   the broken deployment rather than reverting it. This is a foot-gun during an
   incident, not merely an inconvenience.
4. **Only one EU region.** Amsterdam is the sole EU option; there is no Poland
   region. Confirmed against the live region list.
5. **Usage-based billing accrues at zero traffic.** RAM at $10/GB/month and CPU
   at $20/vCPU/month are billed continuously for an always-on process, plus
   $0.15/GB/month for volume storage. The "$5/mo" headline is a credit, not a cap.
6. ~~"No free tier."~~ **Disproved** — a $0/mo Free plan with $1 monthly credit
   now exists. Immaterial here: $1 will not run this workload.

### Pre-Mortem — How This Could Fail

Six months in, the failure that actually lands is data loss, not latency. The
Postgres volume ran without a backup schedule because nothing on the platform
required one and the deploy checklist never asked. A bad migration — or a
`railway volume delete` typed against the wrong linked service, since the CLI
links a service globally and `railway status` is the only thing showing which —
takes the household's entire medicine history with it, and there is nothing to
restore from. The recovery attempt then compounds it: the operator reaches for
`railway redeploy`, which redeploys the *latest* deployment rather than rolling
back, re-applying the very migration that caused the damage. Meanwhile the daily
ingestion cron has been skipping runs whenever the previous execution is still
active, so the registry data was already weeks stale and nobody noticed, because
"the cron fired" was treated as proof of freshness. None of these are exotic
platform failures. Each is a default that had to be opted out of, and wasn't.

### Unknown Unknowns

- **Cron silently skips, it does not queue.** If a previous execution still has
  status `Active`, the next scheduled run is dropped entirely. Railway also does
  not guarantee execution to the minute — runs "can vary by a few minutes." So
  neither "the cron is scheduled" nor "the cron fired" is evidence the data is
  fresh; only an app-side last-successful-run timestamp is.
- **Region aliases in `railway scale` don't map to where you actually are.**
  `us-west` resolves to `pdx`/`us-west1`, but a service can sit in
  `sfo`/`us-west2`. Passing `us-west=0` to drain a service in `sfo` silently
  creates a second replica instead of moving one. Zero regions by their
  airport-code ID, confirmed via the `regions` API query.
- **Region assignments are replica counts.** On a service whose `startCommand`
  runs `migrate`, a two-region state means two containers running `migrate`
  concurrently — so `numReplicas: 1` implicitly also means "never span regions,
  even transitionally."
- **A database's internal DNS disappears while it moves.** `railway scale` on a
  volume-backed service tears down and rebuilds the container; during that
  window `*.railway.internal` does not resolve, and any app container booting
  into it dies on DNS resolution. Sequence the DB first, wait for green, then
  redeploy the app.
- **PR environments require a GitHub remote.** They are GA and automatic once
  enabled in Project Settings → Environments, but they hang off the GitHub
  integration. This project deploys via `railway up` from a local branch with no
  GitHub remote, so PR previews are **not available today** without first
  publishing the repo.
- **`DATABASE_PUBLIC_URL` is set even when no TCP proxy exists.** The variable
  is populated but points at nothing until a proxy is created, so a connection
  attempt hangs rather than failing fast. Don't read its presence as "the DB is
  reachable from outside."

## Operational Story

Verified against CLI `5.30.3` and the live project on 2026-08-03.

- **Preview deploys**: **Not available on this project.** PR environments are GA
  but require the GitHub integration plus enabling PR environments in Project
  Settings → Environments; this repo has no GitHub remote and deploys via
  `railway up --service web --ci` from a local branch. Ad-hoc isolated
  environments are still possible via `railway environment new <name>`.
- **Secrets**: environment variables live per-service in the Railway project.
  Read with `railway variables --service web --kv`; set with
  `railway variables set KEY=value`. Pipe secrets via Bash `printf '%s'` into
  `--stdin`, never a PowerShell pipeline (it appends a newline that is stored as
  part of the value). `DATABASE_URL` is a reference variable
  (`${{Postgres.DATABASE_URL}}`) resolving to the internal host, not the public
  proxy.
- **Rollback**: two steps, and the second is an API call, not a CLI verb:
  ```bash
  railway deployment list --service web --json          # find the target ID
  railway api 'mutation { deploymentRollback(id: "<deployment-id>") }'
  ```
  Pre-check eligibility with `Deployment.canRollback` — it reports `false` for
  FAILED deployments. **Do not reach for `railway redeploy`**: it takes no
  deployment ID and redeploys *latest*, which during an incident re-applies the
  broken release. Migrations do not roll back with the deployment.
- **Approval**: an agent may deploy, read logs and variables, scale, change
  region, and roll back. Human-only: deleting a service or volume, dropping the
  database, rotating `SECRET_KEY`, and `railway ssh` (which needs a TTY an agent
  cannot supply — the tell is a command that returns nothing and never exits).
- **Logs**: `railway logs` for the linked service; `railway logs --deployment <id>`
  for a specific deployment, including failed ones — this is how the region-move
  DNS failure was diagnosed. `--build` for build logs. The cron job's log stream
  is separate from the app's; check both when verifying the daily ingestion.
- **Which service am I talking to?** `railway service link <name>` sets the
  linked service globally, and several commands default to it silently.
  `railway status` is the only thing that shows the current link — check it
  before any destructive command.

## Risk Register

| Risk | Source | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| **Postgres volume has no backup schedule — verified `[]`. Total data loss on a bad migration or an accidental volume delete.** | Devil's advocate (re-run) | H (certain, current state) | H | Enable a schedule now: `volumeInstanceBackupScheduleUpdate` via `railway api`, or Service → Backups in the dashboard. Daily/6-day retention is adequate at 103 MB. Verify with `volumeInstanceBackupScheduleList`. |
| `railway redeploy` re-applies the broken release when reached for as "rollback" | Devil's advocate (re-run) | M | H | Record the two-step `deployment list` + `deploymentRollback` sequence in the runbook *before* an incident. Never improvise rollback. |
| Daily ingestion cron skips runs silently when the prior execution is still `Active`, and fires ±minutes | Unknown unknowns (confirmed in docs) | M | H | **Shipped** (`registry-freshness-refresh`, F-02): `registry.ImportRun` records every attempt outside the import's own transaction, `registry/freshness.py::get_verdict()` is the single trigger-agnostic freshness check (48h `STALE_AFTER`), surfaced via a read-only `/admin/registry/importrun/` banner and `manage.py registry_status` (non-zero exit when stale). Verified against three consecutive unattended production fires, 2026-08-16 through 2026-08-18, drift +9s to +2m2s — see `context/changes/registry-freshness-refresh/production-verification.md`. Still true regardless: never treat "cron fired" as freshness — read the verdict, not the schedule. |
| Cost drifts above the $5 Hobby credit as volume storage and always-on compute accrue | Pre-mortem | M | L | `railway usage` and `railway usage limit` now exist — set a **soft** limit as the budget alert. Keep any hard limit well above realistic spend; a tight hard limit is a scheduled outage. |
| Region move creates a transient second replica running `migrate` concurrently | Unknown unknowns (observed) | M | M | Zero the old region by airport-code ID in the same command (`eu-west=1 sfo=0`), never by alias. `numReplicas: 1` means "one region at a time". |
| App/DB split across regions degrades silently instead of erroring | Unknown unknowns (observed) | L | M | Private networking is region-agnostic, so a split placement *works* and only shows up as latency. Move app and DB together; verify both with `railway status` per service and `VolumeInstance.region`. |
| Railway MCP server is shipped but vendor-labelled "work in progress" (checked 2026-08-03) | Research finding | H (certain) | L | CLI + `railway api` already cover the full loop. Adopt MCP where it reduces `--help` traversal; don't depend on tool stability yet. |
| Only one EU region (Amsterdam); no Poland-local presence | Devil's advocate | H (certain) | L | Accept. Measured at ~90 ms from Poland after the move — below the threshold where it's worth caring at household scale. |
| Restore path is documented dashboard-only | Devil's advocate (re-run) | H (certain) | L | `volumeInstanceBackupRestore` exists in the public API. Confirm the restore procedure once, on a throwaway backup, before needing it. |
| PR preview environments unavailable (no GitHub remote) | Research finding | H (certain) | L | Accept for MVP, or publish the repo and enable PR environments in Project Settings. `railway environment new` covers ad-hoc isolation meanwhile. |
| Leaving Railway later requires manual Postgres export + env var reconfiguration | Unknown unknowns | L | M | Known lock-in cost. Not a near-term concern. |

~~"No free tier"~~ and ~~"no easy in-place region migration"~~ have been removed
from the register — both were disproved on 2026-08-02/03. See the corrections table.

## Getting Started

The project is **already deployed**. This is the rebuild-from-scratch recipe,
accurate to CLI `5.30.3` — useful for recovery or for a second environment.

1. `railway login`, then `railway link` to attach the repo to the existing
   `domowa-apteka` project (or `railway init` for a new one).
2. `railway add` to provision co-located Postgres — auto-injects `DATABASE_URL`
   as a reference variable into the web service.
3. Commit `uv.lock` and `pyproject.toml`. Railpack detects `uv.lock` and runs
   `uv sync --locked --no-dev` — no Dockerfile. A lockfile out of sync with
   `pyproject.toml` **fails the build**, so always use `uv add` / `uv lock`.
4. Set variables before first deploy: `SECRET_KEY`, `DEBUG=False`,
   `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`. Pipe secrets with Bash
   `printf '%s' "$VALUE" | railway variables set KEY --stdin`.
5. Pin deploy config in `railway.json`, including `"region"` — otherwise
   `railway up` reasserts the workspace default. `numReplicas: 1` while
   `migrate` runs inside `startCommand`.
6. `railway up --service web --ci` to deploy; `--ci` streams build logs then
   exits, which is what makes it scriptable.
7. **Enable volume backups** — `railway api` with
   `volumeInstanceBackupScheduleUpdate`, or Service → Backups. This step was
   missed on the first deploy; do not miss it again.
8. Configure the daily ingestion as a Cron service running
   `python manage.py <ingestion-command>`, and add an app-side
   last-successful-run timestamp so freshness is observable.

## Out of Scope

The following were not evaluated in this research:
- Docker image configuration
- CI/CD pipeline setup
- Production-scale architecture (multi-region, HA, DR)
- Re-evaluation of Azure, Render, Fly.io, Vercel, Cloudflare, or Netlify — those
  rows carry 2026-07-31 research dates and were not revisited on 2026-08-03.
