---
project: domowa-apteka
deployed_at: 2026-08-01
platform: Railway
environment: production
status: live
---

# Deployed State — domowa-apteka

Post-deploy record of what is **actually running**. The upfront plan and its
full execution log live at `context/changes/deployment/deployment-plan.md`;
this file is the short answer to "what is deployed and how do I touch it".

## Live URL

**https://web-production-f61ed.up.railway.app**

- `/health/` → `200 ok` (liveness probe; deliberately does not touch the DB,
  so a database outage does not also trigger a rollback loop)
- `/admin/` → Django admin, login verified end-to-end over HTTPS

## Railway resources

| Resource | Name | ID |
| --- | --- | --- |
| Project | `domowa-apteka` | `d65038dc-2df8-4a08-91bc-be7255c9154e` |
| Environment | `production` | `3704dc3d-20dc-4744-97c9-fd94624a7d42` |
| Web service | `web` | `4adb8513-d6dc-4441-94bd-a375ef368a0d` |
| Database | `Postgres` | `534de5e9-ce4e-4cde-b1ce-532f6d5988a8` |
| Cron service | `registry-import-cron` | `d87f619c-4a72-4976-be68-a9ad9bf33f9d` |

Workspace `tszreder's Projects` (`9780cb91-a4f2-4498-904c-b75fa84ee62f`),
workspace `preferredRegion` = `europe-west4-drams3a`.

**Region: EU West / Amsterdam (`ams`, `europe-west4-drams3a`)** for both `web`
and `Postgres`. Originally deployed to `sfo` (US West) and migrated in place on
2026-08-02 — see "Region migration" below.

## Wired secrets and variables (service `web`)

| Variable | Source | Note |
| --- | --- | --- |
| `SECRET_KEY` | set manually via `--stdin` | 50 chars, generated fresh; never committed, never on a command line |
| `DEBUG` | set manually | `False` |
| `ALLOWED_HOSTS` | set manually | `web-production-f61ed.up.railway.app,healthcheck.railway.app,.railway.internal` |
| `CSRF_TRUSTED_ORIGINS` | set manually | `https://web-production-f61ed.up.railway.app` |
| `DATABASE_URL` | reference `${{Postgres.DATABASE_URL}}` | resolves to `postgres.railway.internal:5432/railway` — internal network, not the public proxy |

`RAILWAY_*` variables are injected by the platform. No other secrets are wired.

**Not present, by design:** `DJANGO_SUPERUSER_*` were set temporarily to seed the
admin account and **deleted afterwards** — see "How the superuser was created".

## Deploy configuration

Config-as-code in `railway.json` (git-tracked, so the deploy is reproducible
from source rather than dashboard state):

- `startCommand`: `migrate --noinput` → `collectstatic --noinput` → `gunicorn domowa_apteka.wsgi --bind 0.0.0.0:$PORT`
- `healthcheckPath`: `/health/`, `healthcheckTimeout`: 300
- `restartPolicyType`: `ON_FAILURE`, max 3 retries
- `numReplicas`: **1 — do not raise.** `migrate` runs inside `startCommand`, so
  concurrent replicas race on migrations. Move `migrate` to a separate release
  step before scaling horizontally. **This also constrains `railway scale`** —
  region assignments *are* replica counts, so `eu-west=1 us-west=1` means two
  replicas running `migrate` concurrently.
- `region`: `europe-west4-drams3a`. Pinned in `railway.json` so a later
  `railway up` cannot reassert the workspace default and silently move the
  service. Config-as-code and the live `railway scale` state must agree.

**This pin covers `web` only.** `Postgres` is template-provisioned and never
reads this repo's `railway.json` — its EU West placement is **live platform
state with nothing reproducing it**. If Postgres is ever deleted and
reprovisioned, it will land in the workspace default region and must be moved
by hand again with `railway scale --service Postgres eu-west=1 <old-region>=0`.

Build: Railpack auto-detects the Python project and runs `uv sync --locked --no-dev`.
`.python-version` pins 3.11. Because the build installs from `uv.lock`, a lockfile
out of sync with `pyproject.toml` **fails the build** — always use `uv add`/`uv lock`,
never pip.

## Deploy trigger

**Auto-deploy on merge to `main`**, via GitHub Actions — not via Railway's own
GitHub integration. Railway's GitHub App is not installed on the account
(`railway api 'query { githubRepos { fullName } }'` returns `Not Authorized`),
and connecting a repo to a service would put the deploy trigger in dashboard
state, which is the thing `railway.json` exists to avoid.

| | |
| --- | --- |
| Repo | `tszreder/domowa-apteka` (private) |
| Workflow | `.github/workflows/deploy.yml` |
| Secret | `RAILWAY_TOKEN` — a Railway **project token** scoped to the `production` environment, stored as a GitHub Actions repository secret |
| Trigger | `push` to `main` (i.e. a PR merge), excluding `context/**`, `docs/**`, `**.md` |
| Gate | job `check` must pass first: `uv sync --locked`, `manage.py check`, `manage.py test` |

Three things about that workflow that are load-bearing, not stylistic:

- **`paths-ignore` is on `push` only, never on `pull_request`.** A workflow
  skipped by a path filter never reports its checks, so a required check would
  sit pending forever and no docs-only PR could ever merge.
- **The ignore list is `context/**`, `docs/**`, `**.md` — nothing else.** So a
  commit touching only `railway.json`, or only `deploy.yml` itself, *does*
  deploy. That is correct (both change how the app runs) but surprising the
  first time a workflow-only edit ships a container.
- **`concurrency` sits on the `deploy` job, not the workflow.** At workflow
  level it would queue PR `check` runs behind an in-flight deploy. The group
  exists to stop two merges from running `migrate` concurrently — see
  `numReplicas: 1` above.
- **`check --deploy` is `continue-on-error`.** It reports three findings in CI:
  `W004` (HSTS) and `W008` (SSL redirect) are the real, accepted gaps below.
  **`W009` (weak `SECRET_KEY`) is a CI artefact, not a production problem** —
  the runner has no `.env`, so settings.py falls back to the scaffold key.
  Production has a fresh 50-char key as a Railway variable. Do not "fix" W009
  by putting a secret in the workflow.

**The manual path still works and is the escape hatch**: `railway up --service
web --ci`. `--ci` streams build logs then exits instead of holding a TTY, which
is what makes it usable from both a runner and an agent.

### Verified end-to-end, 2026-08-04

First CI deploy was the merge of PR #1 (`597a036`), run `30954319213`:

- `check` 20s → `deploy` 44s. Total merge-to-live under two minutes.
- New deployment `2b6fb397-2385-43c7-90b8-796a46d5d198` SUCCESS; the previous
  `8ac6ddde` moved to REMOVED.
- `/health/` **200 in 102ms**, `/admin/login/` **200**, service `● Online`,
  region still **EU West** — the `railway.json` region pin holds for a
  CI-originated upload, not just a laptop one.
- **`RAILWAY_TOKEN` alone carried project and environment context.** No
  `railway link`, no `.railway/` state, nothing else in the runner's env. This
  was the main unverified assumption going in; it holds.
- Runner cost ~1 minute of the 2,000/month GitHub Free allows for private
  repos. `railway up` returns as soon as the image is pushed, so the runner is
  not billed for the container restart.

Two things the first runs corrected, worth not rediscovering:

- `astral-sh/setup-uv` publishes **no floating major tag** — `@v9` fails to
  resolve, only `@v9.0.0` works. Both actions are pinned to exact releases.
- `actions/checkout@v4` and `setup-uv@v6` target the deprecated Node 20 and
  get force-migrated to Node 24 with a warning. Current majors avoid it.

### Branch protection is unavailable — measured, not assumed

Attempted 2026-08-04, both APIs, on this private repo under the free plan:

```
gh api -X POST repos/tszreder/domowa-apteka/rulesets            -> 403
gh api -X PUT  repos/tszreder/domowa-apteka/branches/main/protection -> 403
```

Both return the identical body:

> `Upgrade to GitHub Pro or make this repository public to enable this feature.`

So **neither rulesets nor classic branch protection** work here — it is the
plan tier, not the API choice. The intended rule was: require a PR into `main`,
require the `check` status check, block force-push and deletion.

Consequences to hold in mind, since nothing enforces them:

- **A direct `git push` to `main` deploys.** "Work on a branch, open a PR" is a
  convention here, not a guardrail. `git push origin main` with app code in it
  ships to production with no gate.
- The `check` job still runs on every PR and still blocks `deploy` via
  `needs:` — that part does not depend on branch protection. What is missing is
  only the *inability to bypass the PR*.

Three ways to close it if that becomes uncomfortable: GitHub Pro (~$4/month),
make the repo public (the code is not sensitive; the secret lives in GitHub,
not the repo), or a local `pre-push` hook rejecting pushes to `main` — weakest,
since it is per-clone and trivially skipped with `--no-verify`.

## Runbooks

**Deploy** — normally: merge a PR into `main` and let the workflow run.
To deploy without a merge (hotfix, or CI is down):
```powershell
railway up --service web --ci
```

**Watch a CI deploy**
```powershell
gh run list --limit 5
gh run watch <run-id>
gh run view <run-id> --log-failed
```

**Redeploy the current commit without pushing anything**
```powershell
railway redeploy --service web --yes
```

**Rotate `RAILWAY_TOKEN`**
1. Railway dashboard → project `domowa-apteka` → Settings → Tokens → create a
   new project token scoped to `production`; delete the old one.
2. GitHub → repo Settings → Secrets and variables → Actions → update
   `RAILWAY_TOKEN`.

Do not mint the token with `railway api projectTokenCreate` and do not pass it
to `gh secret set --body`. Both print or accept the value on a command line,
which puts a credential with full project access into shell history and, if an
agent is driving, into its transcript. Dashboard → web UI, by hand.

**Check status / logs**
```powershell
railway deployment list --service web --json
railway logs --service web --deployment
```

**Roll back** (no single rollback verb exists — two steps)
```powershell
railway deployment list --service web --json   # copy a prior SUCCESS id
railway redeploy --service web --yes           # redeploys latest
```

**Set a variable without triggering a deploy**
```powershell
railway variable set KEY=value --service web --skip-deploys --json
```
For secrets, pipe from **Bash `printf`**, never a PowerShell pipe:
```bash
printf '%s' "$VALUE" | railway variable set KEY --stdin --service web --skip-deploys
```
A PowerShell pipeline appends a newline that Railway stores as part of the value.

## Cost monitoring — currently manual

`railway usage limit set --target workspace --soft 5 --hard 15` was attempted on
2026-08-01 and **rejected**: `Usage limits require an active subscription`. The
account is on the free tier, so enforced limits are unavailable.

Until a subscription exists, cost monitoring is a manual check:
```powershell
railway usage --json
railway usage projects --json
```
Baseline at first deploy: **$0.0023** for the current period, no limit set.

**When a subscription is added, set the limits** — the intended values are
soft **$5**, hard **$15**. Note the two differ in kind: **soft** only notifies;
**hard** actually shuts resources down, i.e. a deliberate outage as a
runaway-cost breaker.

## How the superuser was created (and why it matters for next time)

`railway ssh` is the only way to run a one-off `manage.py` command against the
deployed database — `railway run` executes **locally** with variables injected,
and `DATABASE_URL` points at `postgres.railway.internal`, unreachable from a
laptop. But `railway ssh` holds a TTY and **hangs in any non-interactive shell**,
so it cannot be driven by an agent.

The workaround used, which needs no shell at all:

1. Set `DJANGO_SUPERUSER_USERNAME` / `_EMAIL` / `_PASSWORD` as service variables.
2. Temporarily add `(python manage.py createsuperuser --noinput || true)` to
   `startCommand` in `railway.json`. The `|| true` keeps it idempotent — without
   it, a redeploy where the user already exists returns non-zero and breaks the
   `&&` chain, crashing the container.
3. Deploy, confirm "Superuser created successfully" in the logs.
4. Revert `railway.json`, **delete all three variables**, redeploy.

Reuse this shape for any future one-off management command.

## Orphaned credential — safe to remove

An SSH key was created while trying to reach the container, then made redundant by
the `startCommand` workaround. **Nothing uses it.**

- Local files: `~/.ssh/id_ed25519_railway` and `.pub` (no passphrase)
- Registered with Railway as `domowa-apteka-agent`,
  fingerprint `SHA256:hlm4FS6ZPTUUEpGIzc86p/KpYPWROz+0NFLnBRQfr90`

Keep it only if a human intends to use `railway ssh` interactively. Otherwise remove:

```powershell
railway ssh keys remove domowa-apteka-agent
Remove-Item "$env:USERPROFILE\.ssh\id_ed25519_railway*"
```

## Region migration (2026-08-02, sfo → ams)

Moved both services from US West to EU West in place. `infrastructure.md` had
recorded "no easy in-place region migration" as a risk — **that turned out to be
wrong**; `railway scale` does it without re-provisioning or DNS changes.

```bash
railway scale --service web      eu-west=1 sfo=0
railway scale --service Postgres eu-west=1 sfo=0
```

Three things that bit, worth knowing before repeating this:

1. **`us-west=0` does not zero `sfo`.** The CLI alias `us-west` maps to a
   *different* US West region (`pdx`/`us-west1`) than the one the services were
   actually in (`sfo`/`us-west2`). Passing `eu-west=1 us-west=0` left the service
   at **2 replicas** (EU West + sfo) instead of moving it. Zero the region by its
   **airport-code ID** (`sfo=0`), which `railway scale` accepts alongside aliases.
   Confirm the ID first: `railway api 'query { regions(projectId: "...") { id name location } }'`.
2. **Move `web` and `Postgres` in the same window, then redeploy `web` last.**
   Railway private networking is a WireGuard mesh scoped to project+environment,
   not to region — so a split placement *works* but pays a transatlantic RTT on
   every one of Django's 5–15 queries per request. Worse, while Postgres was
   being rebuilt in `ams` its `postgres.railway.internal` record disappeared, and
   the concurrent `web` boot died on
   `OperationalError: failed to resolve host 'postgres.railway.internal'`.
   Two `web` deployments failed this way. Harmless (the old `sfo` deployment kept
   serving) but avoidable: scale Postgres first, wait for it to go green, then
   `railway up --service web --ci`.
3. **Volume migration was a non-event.** 103MB moved with the service; the volume
   came back `Ready` and the boot logged `No migrations to apply`, confirming the
   `django_migrations` table came across rather than a blank volume being
   re-migrated from scratch. Row-level contents were **not** independently
   verified — `DATABASE_PUBLIC_URL` is set but no TCP proxy exists, so the DB is
   unreachable from outside the private network by design.

Measured effect: `/health/` went from ~292ms to ~88ms from Poland.

## Registry import cron (`registry-freshness-refresh` F-02, Phase 3)

**Config-path mechanism — settled empirically, 2026-08-16, without touching
production.** `railway up`/`railway service` expose no config-path flag (per
the plan's own note), but the GraphQL API does: `ServiceInstance.railwayConfigFile`
is a plain `String` field, and it is also on `ServiceInstanceUpdateInput` —
confirmed by introspecting the live schema:

```
railway api 'query { __type(name: "ServiceInstance") { fields { name } } }'
railway api 'query { __type(name: "ServiceInstanceUpdateInput") { inputFields { name type { name } } } }'
railway api 'query { __schema { mutationType { fields { name } } } }'   # → serviceInstanceUpdate
```

So a second service is pointed at `railway.cron.json` instead of the
repo-root `railway.json` by setting `railwayConfigFile: "railway.cron.json"`
on that service's instance via `serviceInstanceUpdate` — a one-time
API/dashboard step, not a CLI flag and not something `deploy.yml` can express.
No dashboard fallback was needed; the documented fallback in `plan.md` is
moot.

**What is code-complete:**
- `railway.cron.json` — `deploy.startCommand` runs `python manage.py
  import_registry --trigger scheduled`, `deploy.cronSchedule` is `17 3 * * *`
  (03:17 UTC — after the publisher's daily refresh, deliberately off the
  `@daily`/midnight mark where platform contention is worst), and
  `deploy.restartPolicyType` is `NEVER`. `deploy.region` is pinned to
  `europe-west4-drams3a`, same as `web`'s pin and for the same reason (see
  "Deploy configuration" above) — unpinned, a later `railway up` could
  reassert the workspace default, and a split-region cron would pay
  transatlantic RTT downloading ~74 MB and writing to
  `postgres.railway.internal` on every run. No `healthcheckPath`, no
  `numReplicas` — both are `web`-only concerns. Validated against the live
  `https://railway.com/railway.schema.json` with `jsonschema` (`uv add --dev
  jsonschema`).
- `.github/workflows/deploy.yml` gained a second `railway up --service
  registry-import-cron --ci` step, sequenced **after** `web`'s, so a cron
  execution can never hit an unmigrated schema.

**Provisioned 2026-08-16**, with explicit go-ahead (creating billed
production infrastructure and wiring production credentials was held for a
human decision — see git history on this section for the earlier
not-yet-provisioned state):

```
railway add --service registry-import-cron --json
railway api 'mutation($serviceId: String!, $environmentId: String!) {
  serviceInstanceUpdate(serviceId: $serviceId, environmentId: $environmentId,
    input: { railwayConfigFile: "railway.cron.json" })
}' --variables '{"serviceId":"d87f619c-4a72-4976-be68-a9ad9bf33f9d","environmentId":"3704dc3d-20dc-4744-97c9-fd94624a7d42"}'
railway variable set 'DATABASE_URL=${{Postgres.DATABASE_URL}}' --service registry-import-cron --skip-deploys
railway variable set 'SECRET_KEY=${{web.SECRET_KEY}}'          --service registry-import-cron --skip-deploys
railway variable set 'DEBUG=False'                              --service registry-import-cron --skip-deploys
railway up --service registry-import-cron --ci
```

`SECRET_KEY` and `DATABASE_URL` were set as **references** (`${{web.SECRET_KEY}}`,
`${{Postgres.DATABASE_URL}}`), not raw values — the actual secret was never
seen, typed, or logged by the agent driving this. `ALLOWED_HOSTS` and
`REGISTRY_OVERALL_URL` were deliberately left unset: a management command
never serves an HTTP request, so `ALLOWED_HOSTS`'s fallback
(`['localhost', '127.0.0.1']`) is inert, and `REGISTRY_OVERALL_URL`'s in-code
default is correct until it's ever changed (see the drift-risk note below).

**Confirmed against the running service** (`railway api` querying
`service(id).serviceInstances.edges.node.latestDeployment.meta`): the deploy's
`fileServiceManifest.deploy` shows `cronSchedule: "17 3 * * *"`,
`region: "europe-west4-drams3a"`, `restartPolicyType: "NEVER"`, and the
expected `startCommand` — `railway.cron.json` is genuinely driving this
service, not just pointed at. The dashboard's **Cron Runs** tab independently
agrees: "Runs at 03:17 am (UTC)".

**A `railway up` or `railway redeploy` against a cron-scheduled service is
build-only** — confirmed by inspecting `deployment.meta.buildOnly: true` on
both the initial deploy and a subsequent `railway redeploy`. Neither actually
executes `startCommand`; the container only runs at the next cron tick, or via
the dashboard's **Cron Runs → Run now** button (no CLI/GraphQL equivalent
found — `serviceInstanceDeploy(V2)` and `serviceInstanceRedeploy` take no
"run now" argument). This is new information beyond what the plan anticipated
(it only marked the config-*path* mechanism unverified, not manual
triggerability) — worth knowing before assuming any CLI-only workflow can
kick off an out-of-schedule run.

**First manual trigger (via "Run now"), 2026-08-16 23:36 UTC: crashed, not a
clean `failed` row.**

```
django.db.utils.ProgrammingError: relation "registry_importrun" does not exist
```

Cause: `registry-import-cron` was built from the **`feature/registry-freshness-refresh`
branch**, which carries the `0002_importrun` migration — but `web` was still
serving `main`, which predates F-02 entirely, so production Postgres never
ran that migration. The cron container's own code creates an `ImportRun` row
as the very first thing `handle()` does (see `import_registry.py`), and that
`INSERT` hit a table that doesn't exist — so the crash happened **below**
the run-record safety net Phase 1 built, not despite it. No `ImportRun` row
was written at all; there was no row to write to.

This is empirical, sharper confirmation of the exact hazard
"Timing & lifecycle — deploy order matters" in `plan.md` describes: not just
"a cron execution could race an unmigrated schema", but "a cron service
built from code `web` hasn't deployed yet has **no** schema for that code at
all". The fix already exists (`deploy.yml`'s `web`-then-cron ordering) — this
failure predates that ordering ever applying, because the branch itself
hadn't reached `main` yet.

**Resolved, 2026-08-16 23:48 UTC, after merge.** PR #21 merged as `c506ae5`;
`deploy.yml`'s `deploy` job redeployed `web` (running the migration) then
`registry-import-cron`, in that order, exactly as designed. Re-triggered via
"Run now": **succeeded in 15s** against the real registry —

```
Registry snapshot 2026-08-16
  products in file:   22884 (all kinds)
  products loaded:    20242 (0 new)
  products inactive:  3
  substances:         0 new
  links:              25879
    substance_row: 25465
    common_name: 414
  resolved:           19681 of 20242 (97.2%)
  elapsed:            9.8 s
```

Not independently confirmed by reading the `ImportRun` row itself — no
production admin credentials on hand, and the deployment has no live
instance to attach a console to once the run exits (cron containers don't
stay up). Confirmed by construction instead: `handle()`'s success path calls
`run.save()` *before* `_report()` prints the summary above
(`import_registry.py`), so seeing that summary in the deployment logs is
proof the row landed with `status=success`, `trigger=scheduled` (the only
value `railway.cron.json`'s `startCommand` ever passes).

**Service variables — final state:**

| Variable | Source |
| --- | --- |
| `DATABASE_URL` | reference `${{Postgres.DATABASE_URL}}` |
| `SECRET_KEY` | reference `${{web.SECRET_KEY}}` |
| `DEBUG` | `False` |
| `ALLOWED_HOSTS` | unset — inert for a non-HTTP management command |
| `REGISTRY_OVERALL_URL` | unset — falls back to the in-code default, same as `web`. **If this is ever set on `web`** (to bump the export version), **set it identically on the cron service in the same change.** `settings.py`'s own comment says the variable exists so a version bump is "a variable change, not a code deploy" — a cron service left behind would keep importing the old version while `web`'s config claims otherwise, silently reintroducing the drift the variable exists to prevent. |

No new setting is introduced by this change, so `.env.example` is unchanged.

## Known gaps

- `SECURE_SSL_REDIRECT` and `SECURE_HSTS_SECONDS` are **off**. `check --deploy`
  flags both. `SECURE_SSL_REDIRECT` was deferred because a redirect can turn the
  healthcheck's 200 into a 301 and fail deploys; HSTS is browser-cached and
  semi-irreversible. Both are safe to revisit now that the deploy is green.
- **Daily ingestion cron is live and confirmed working.** `registry-import-cron`
  runs `railway.cron.json`'s schedule (03:17 UTC daily) and a manually
  triggered run succeeded end-to-end on real production data 2026-08-16 —
  see "Registry import cron" above. What's left is Phase 4 of
  `registry-freshness-refresh`: confirming an actual *unattended* scheduled
  fire (not a manual "Run now") lands cleanly, which can't be checked until
  the schedule has genuinely come around.
- **CI's `check` job is a thin gate no longer** — `registry` and `households`
  both carry real tests now; `manage.py test` is a meaningful signal.
- `ALLOWED_HOSTS` cannot be black-box tested from the internet: Railway's edge
  router returns 404 for an unknown Host before the request reaches Django.
  Verify by reading the stored variable, not by probing.
