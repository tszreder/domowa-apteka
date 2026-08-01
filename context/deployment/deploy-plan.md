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

Workspace `tszreder's Projects` (`9780cb91-a4f2-4498-904c-b75fa84ee62f`).

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
  step before scaling horizontally.

Build: Railpack auto-detects the Python project and runs `uv sync --locked --no-dev`.
`.python-version` pins 3.11. Because the build installs from `uv.lock`, a lockfile
out of sync with `pyproject.toml` **fails the build** — always use `uv add`/`uv lock`,
never pip.

## Deploy trigger

**Manual CLI only** — `railway up --service web --ci`. There is no GitHub remote
and no auto-deploy on push. `--ci` streams build logs then exits, which is what
makes it usable from a script or an agent.

## Runbooks

**Deploy**
```powershell
railway up --service web --ci
```

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

## Known gaps

- `SECURE_SSL_REDIRECT` and `SECURE_HSTS_SECONDS` are **off**. `check --deploy`
  flags both. `SECURE_SSL_REDIRECT` was deferred because a redirect can turn the
  healthcheck's 200 into a 301 and fail deploys; HSTS is browser-cached and
  semi-irreversible. Both are safe to revisit now that the deploy is green.
- No CI/CD, no GitHub remote, no auto-deploy.
- No application code yet beyond the scaffold — no Django app, no models. The
  daily ingestion cron (Phase 6 of the plan) is blocked on that feature work.
- `ALLOWED_HOSTS` cannot be black-box tested from the internet: Railway's edge
  router returns 404 for an unknown Host before the request reaches Django.
  Verify by reading the stored variable, not by probing.
