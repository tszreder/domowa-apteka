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

## Known gaps

- `SECURE_SSL_REDIRECT` and `SECURE_HSTS_SECONDS` are **off**. `check --deploy`
  flags both. `SECURE_SSL_REDIRECT` was deferred because a redirect can turn the
  healthcheck's 200 into a 301 and fail deploys; HSTS is browser-cached and
  semi-irreversible. Both are safe to revisit now that the deploy is green.
- No application code yet beyond the scaffold — no Django app, no models. The
  daily ingestion cron (Phase 6 of the plan) is blocked on that feature work.
- **CI's `check` job is a thin gate.** `manage.py test` finds 0 tests, so today
  the only real signals are lockfile sync and Django's system checks. It gets
  meaningful the moment the first app exists — it is wired now so there is
  somewhere for those tests to land.
- `ALLOWED_HOSTS` cannot be black-box tested from the internet: Railway's edge
  router returns 404 for an unknown Host before the request reaches Django.
  Verify by reading the stored variable, not by probing.
