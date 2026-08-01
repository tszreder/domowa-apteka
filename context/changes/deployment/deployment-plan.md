# Railway Deployment Plan — domowa-apteka

## Context

`context/foundation/infrastructure.md` recommends Railway (co-located Postgres, Railpack/Nixpacks auto-detects `uv.lock`, native cron, scriptable CLI). The repo is currently a bare `django-admin startproject` scaffold: default insecure `SECRET_KEY`, `DEBUG=True`, empty `ALLOWED_HOSTS`, SQLite, no apps, no ingestion command, no GitHub remote. The goal of this change is to get that scaffold running in production on Railway with a co-located Postgres database, so subsequent feature work (households, pharmaceuticals, duplicate matching) ships onto a working deploy pipeline instead of bolting deployment on at the end.

Two things discovered during research **update infrastructure.md's assumptions** (not edited — that file is skill-owned per `AGENTS.md`; noted here and left for a future `/10x-infra-research` re-run if it matters):
- Railway replaced **Nixpacks with Railpack** as its build system (beta since March 2026). Behavior is equivalent for this project: Railpack still auto-detects `uv.lock`/`pyproject.toml`, installs `uv`, and — notably — auto-detects Django and generates `python manage.py migrate && gunicorn {app}:application` as the start command. We override this explicitly anyway (see Phase 3) rather than rely on auto-detection.
- `railway variables set` (infrastructure.md's syntax) vs `railway variable set` (singular, per current docs) — CLI syntax drifts between doc snapshots. Every phase below that shells out to `railway` starts with `--help` to confirm current syntax rather than trusting either source blindly.

**Deploy trigger decision (user confirmed): CLI-only (`railway up`) for the MVP week.** No GitHub remote exists yet; wiring GitHub-linked auto-deploy is deferred to a future change once the repo is pushed. This also means the "deploys trigger automatically on push" assumption in infrastructure.md's Operational Story doesn't apply yet — deploys are manual (`railway up`) until that's revisited.

**Plan artifact location (user directed):** this plan is persisted to `context/changes/deployment/deployment-plan.md`, following the repo's existing `context/changes/<change-id>/` convention (see `context/changes/README.md`, and the sibling `context/changes/bootstrap-verification/`) rather than the `context/deployment/deploy-plan.md` path that `CLAUDE.md`'s Module 1 Lesson 5 notes describe for Plan Mode's output. The two serve different purposes and both get written: `deployment-plan.md` (this document, the upfront plan) written here directly, and `context/deployment/deploy-plan.md` (a short post-deploy record of what actually got deployed — domain, wired secrets, confirmed working state) written in Phase 5 once verification passes, matching what CLAUDE.md says downstream milestone-planning skills expect to find there.

**Status: approved for execution; Phase 0 complete (2026-08-01).** Phase 0's local code changes are done and verified — see the Execution Log at the bottom of this file for what was done and where it deviated from the plan as drafted. Phases 1–5 not started; Phase 6 remains blocked on feature work.

---

## Phase 0 — Make the scaffold deployable (local code changes)

The current `settings.py` is 100% local-dev defaults. Nothing here is Railway-specific yet — it's the prerequisite any Postgres+env-var host would need. This phase has several first-deploy landmines identified during research; each gets its own checkbox and its "if you see X, it's Y" line.

- [x] **Add production dependencies** to `pyproject.toml`: `gunicorn`, `psycopg[binary]`, `dj-database-url`, `whitenoise`. Run `uv lock` to update `uv.lock` (already git-tracked, per `.gitignore` comment — do not gitignore it).
- [x] **Env-driven settings** in `domowa_apteka/settings.py`:
  - `SECRET_KEY = os.environ["SECRET_KEY"]` (no default — fail loudly if unset in prod; keep a local-only fallback pattern only if you also add a `.env` + `python-dotenv`/`django-environ` loader for local dev — simplest is `os.environ.get("SECRET_KEY", "django-insecure-...-local-only")`).
  - `DEBUG = os.environ.get("DEBUG", "False") == "True"`. **Do not use `bool(os.environ.get("DEBUG"))`** — `bool("False")` is `True` in Python; this is the classic silent-prod-debug-leak bug.
  - `ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "").split(",")` if set, else sensible local default (`["localhost", "127.0.0.1"]`).
- [x] **Database**: replace the hardcoded `sqlite3` `DATABASES` block with `dj_database_url.config(default="sqlite:///db.sqlite3", conn_max_age=600)`, reading `DATABASE_URL` from env. Keeps local dev on SQLite with zero config while prod picks up Railway's injected Postgres URL automatically.
- [x] **Static files (WhiteNoise)**: add `'whitenoise.middleware.WhiteNoiseMiddleware'` to `MIDDLEWARE` directly below `SecurityMiddleware`; set `STATIC_ROOT = BASE_DIR / "staticfiles"`. **Storage backend decision**: use `STORAGES = {"staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"}}` (non-manifest) rather than `CompressedManifestStaticFilesStorage` — the manifest variant crashes at runtime (`ValueError: Missing staticfiles manifest entry`) if `collectstatic` wasn't run at build time for every referenced file. Non-manifest is more forgiving for a 1-week MVP; revisit once static assets stabilize.
- [x] **Healthcheck endpoint**: add a trivial view + urlpattern, e.g. `path("health/", lambda r: HttpResponse("ok"))` in `domowa_apteka/urls.py`. Required because Railway's `healthcheckPath` needs a real 200-returning route — `/` is currently a 404 (only `/admin/` exists) and pointing the healthcheck at a 404 path fails every deploy in an infinite rollback loop that looks like a build failure, not a healthcheck failure.
- [ ] **ALLOWED_HOSTS for the healthcheck request specifically**: Railway's internal healthcheck may hit the service on an internal hostname, not your public domain. Verify at deploy time what Host header the failed healthcheck log shows (`railway logs`); if it's not covered by your `ALLOWED_HOSTS` env var, either add it explicitly or set `ALLOWED_HOSTS=*` for the first deploy and tighten afterward once the actual host is confirmed.
- [x] **CSRF + proxy headers for admin login** *(settings applied; the `CSRF_TRUSTED_ORIGINS` env var itself is still deliberately unset — Phase 4)* (needed because end-to-end verification in Phase 4 is "log into `/admin/`" over HTTPS behind Railway's TLS terminator):
  - `SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")`
  - `CSRF_TRUSTED_ORIGINS = os.environ.get("CSRF_TRUSTED_ORIGINS", "").split(",")` if set, else `[]`.
  - **Ordering constraint**: the actual Railway domain isn't known until *after* the first deploy generates one (Phase 4). Set `CSRF_TRUSTED_ORIGINS` as an env var *after* the domain exists, then redeploy — don't hardcode a guessed domain now.
- [x] **Pin the Python version**: add a `.python-version` file (`3.11` or whatever exact version is targeted) at repo root. This is both a build-determinism fix and the documented workaround for a known Railway community issue where the build fails with `uv: command not found` when the Python version isn't pinned explicitly.
- [x] Run `uv run manage.py check --deploy` locally against `DEBUG=False` env vars to catch other production-readiness warnings Django flags out of the box before deploying. *(Run: W009/W012/W016 cleared; W004 + W008 deliberately deferred — see Execution Log.)*

## Phase 1 — Prerequisites: one-time CLI & account setup

Everything in this phase is done **once**, before any project-specific work. This machine (Windows 11, PowerShell primary, Bash tool also available) already has npm (`npm --version` → `10.8.1`) but not Scoop — that decides which install path is the path of least resistance here.

- [ ] **Install the Railway CLI.** On this machine, npm is already present, so:
  ```powershell
  npm i -g @railway/cli
  ```
  Alternative if you'd rather not add a global npm package: install [Scoop](https://scoop.sh/) first, then `scoop install railway`. Either produces the same `railway` binary — pick one, don't do both.
  **Edge case — corporate/locked-down npm registry or proxy**: if `npm i -g` fails with a registry/network error, fall back to the pre-built binary from the [railwayapp/cli GitHub releases](https://github.com/railwayapp/cli/releases) and add it to `PATH` manually.
- [ ] **Verify the install**: `railway --version`. If PowerShell reports `railway` as an unrecognized command right after an npm install, open a new terminal — npm's global bin path is usually only picked up by newly-spawned shells, not the current session.
- [ ] **Create a Railway account** (if one doesn't already exist) at railway.com — GitHub OAuth or email signup. This is a one-time, human-only step; no CLI equivalent.
- [ ] **Authenticate the CLI**: `railway login` — opens a browser to complete auth and stores a token locally. **Edge case — headless/remote/SSH environment** (not this machine, but relevant if you ever run this from a remote dev box): use `railway login --browserless`, which prints a one-time code to paste into railway.com/cli-login from any browser instead.
- [ ] **Verify authentication**: `railway whoami` — should print the logged-in account's email/username. If it errors, `railway login` didn't complete; re-run it.
- [ ] **Decide the CLI-vs-CI auth story now, to avoid re-deriving it later**: interactive `railway login` is fine for this MVP week (CLI-only deploys, confirmed above). If GitHub-linked auto-deploy is wired up later, that flow uses Railway's GitHub App integration, not a CLI token — but if a future CI pipeline needs `railway up` from a non-interactive runner, that's `RAILWAY_TOKEN` (project-scoped) as a secret env var on the runner, not another `railway login`. Not needed now; noted so Phase 5's cron-service work doesn't rediscover this from scratch.
- [ ] **One-time local dev parity check**: confirm `uv sync` and `uv run manage.py runserver` still work against SQLite before touching Railway at all — Phase 0's settings changes must not break local dev. This is the fallback to diff against if a later Railway-specific step misbehaves and it's unclear whether the bug is local-code or platform-specific.

## Phase 2 — Railway project setup (per-project, done once for this repo)

- [ ] From the repo root: `railway init` to create a new Railway project (none is linked yet — confirmed via empty `git remote -v` and no existing Railway link). Name it `domowa-apteka` for consistency with `tech-stack.md`.
- [ ] Add Postgres: `railway add --database postgres` (confirm exact flag via `railway add --help` first — CLI syntax drift noted above). This auto-provisions a co-located Postgres and exposes reference variables (`${{Postgres.DATABASE_URL}}`, etc.) to other services in the same project.
- [ ] **Edge case — no service exists yet to attach the database reference to**: if `railway add --database postgres` requires an existing service context, create the web service first via a no-op `railway up` (it will fail on missing env vars — expected, matches the documented Railway/Django guide behavior) or via `railway service create` if that subcommand exists, then add Postgres.

## Phase 3 — Environment variables & start command (config-as-code)

- [ ] Generate a fresh production `SECRET_KEY` locally (`uv run python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"`) — never reuse the scaffold's committed insecure key.
- [ ] Run `railway variable --help` (or `railway variables --help`) to confirm current syntax, then set on the web service:
  - `SECRET_KEY=<generated>`
  - `DEBUG=False`
  - `ALLOWED_HOSTS=*` (tighten after Phase 4 confirms the real domain/host)
  - `DATABASE_URL=${{Postgres.DATABASE_URL}}` — use the **internal** reference variable, not the public proxy URL (the proxy adds egress cost/latency for services already co-located in the same project).
- [ ] Create `railway.json` at repo root (config-as-code, git-tracked — keeps the deploy config reviewable and scriptable rather than dashboard-only state):
  ```json
  {
    "$schema": "https://railway.com/railway.schema.json",
    "deploy": {
      "startCommand": "python manage.py migrate --noinput && python manage.py collectstatic --noinput && gunicorn domowa_apteka.wsgi --bind 0.0.0.0:$PORT",
      "healthcheckPath": "/health/",
      "healthcheckTimeout": 300,
      "restartPolicyType": "ON_FAILURE",
      "restartPolicyMaxRetries": 3
    }
  }
  ```
  Explicit `startCommand` is used instead of relying on Railpack's Django auto-detection — deterministic, includes `collectstatic`, and controls the `$PORT` bind explicitly.
- [ ] **Guardrail, not a build-now item**: do not raise `numReplicas` above 1 while `migrate` runs inside `startCommand` — concurrent migrate runs across replicas race. If horizontal scaling is ever needed, move `migrate` to a separate one-off release step first.

## Phase 4 — First deploy & verification

- [ ] `railway up` from repo root.
- [ ] **If build fails with `uv: command not found`**: confirm `.python-version` (Phase 0) is committed and matches a version Railpack supports; alternatively set `RAILPACK_PYTHON_VERSION` as a build-time env var.
- [ ] **If deploy fails healthcheck repeatedly (looks like a crash loop)**: check `railway logs` for a 400 response on `/health/` first — that's `ALLOWED_HOSTS` rejecting the healthcheck's Host header, not an app crash. Fix per Phase 0's `ALLOWED_HOSTS` step before assuming the app is broken.
- [ ] Generate a public domain (Railway dashboard → service → Networking → Generate Domain, or `railway domain` if the CLI supports it — confirm via `--help`).
- [ ] Set `CSRF_TRUSTED_ORIGINS=https://<the-generated-domain>` and re-run `railway variable set` + redeploy (`railway up` again, or `railway redeploy`) now that the domain is known.
- [ ] Verify: visit `https://<domain>/health/` → expect `ok`. Create a superuser (`railway run python manage.py createsuperuser` — runs the command against the deployed environment) and log into `https://<domain>/admin/` to confirm DB connectivity, static CSS loads (WhiteNoise), and CSRF/proxy headers are correct end-to-end.

## Phase 5 — Operational hardening

- [ ] Document the rollback runbook as a two-step script (no single rollback verb exists): `railway deployment list` → copy a prior deployment ID → `railway redeploy <deployment-id>`. Confirm exact subcommand names via `--help` at execution time.
- [ ] Set a personal calendar/monthly reminder to check the Railway usage dashboard — no built-in budget alert is confirmed, and the pre-mortem in `infrastructure.md` specifically flags silent cost creep as a risk.
- [ ] Create `context/deployment/` (does not exist yet) and write `context/deployment/deploy-plan.md` — a short post-deploy record (not a duplicate of `deployment-plan.md`): actual domain, which env vars/secrets are wired, confirmed-working verification date. This is the artifact `CLAUDE.md`'s Module 1 Lesson 5 notes say downstream milestone-planning skills expect to find; write it once Phase 4 verification passes.

## Phase 6 — Daily ingestion cron job — BLOCKED, not just deferred

- [ ] **Cannot start yet.** No Django app, no models, no `manage.py <ingestion-command>` exists in the repo (confirmed: `INSTALLED_APPS` is stock Django only, `urls.py` has only `/admin/`). This phase is blocked on the feature work that builds the registry-ingestion management command, not on Railway configuration.
- [ ] Once that command exists, wire it as a **second Railway service** from the same repo (not a replica of the web service), with its own config-as-code file (e.g. `railway.cron.json`, since `cronSchedule` is a per-service `deploy` field and the two services need independent start commands) setting `"startCommand": "python manage.py <ingestion-command>"` and `"cronSchedule": "0 3 * * *"` (adjust hour — Railway cron runs in UTC; convert from the intended Warsaw local time and account for DST drift twice a year).
- [ ] Reuse the same `DATABASE_URL` reference variable on the cron service.
- [ ] Per the risk register in `infrastructure.md`: Railway logs a cron run as "completed" even on early exit — add an app-side last-successful-run timestamp (e.g. visible in Django admin) so a silent early-exit is distinguishable from an actually-fresh registry, rather than trusting Railway's cron status alone.

---

## Verification Summary

- Local: `uv run manage.py check --deploy` passes with prod-like env vars before first `railway up`.
- Deployed: `/health/` returns 200, `/admin/` login succeeds over HTTPS (proves DB, static, CSRF/proxy config all correct simultaneously), `railway logs` shows no repeated healthcheck failures.
- Config is git-tracked (`railway.json`) so the deploy is reproducible from source, not hand-configured dashboard state.
- `context/changes/deployment/deployment-plan.md` (this file) is the upfront plan; `context/deployment/deploy-plan.md` gets written after Phase 4 and reflects the actual deployed state.

## Out of Scope (per infrastructure.md)

- Docker image configuration
- CI/CD pipeline setup (GitHub Actions auto-deploy is a future change, once a GitHub remote exists)
- Production-scale architecture (multi-region, HA, DR)

---

## Execution Log

### Phase 0 — done 2026-08-01

**Files changed:** `pyproject.toml`, `uv.lock` (both via `uv add`), `domowa_apteka/settings.py`, `domowa_apteka/urls.py`, `.python-version` (new).

**Versions installed:** `gunicorn 26.0.0`, `psycopg 3.3.4` (+`psycopg-binary`), `dj-database-url 3.1.2`, `whitenoise 6.12.0`.

**Verified:**
- Local dev unchanged with no env vars set: `check` clean, `DEBUG` resolves via env, SQLite at `BASE_DIR/db.sqlite3`, `ALLOWED_HOSTS=['localhost','127.0.0.1']`, `CSRF_TRUSTED_ORIGINS=[]`.
- Prod-like env vars: `DATABASE_URL` parses to `django.db.backends.postgresql` @ `postgres.railway.internal`, `CONN_MAX_AGE=600`; WhiteNoise is `MIDDLEWARE[1]`, directly under `SecurityMiddleware`; `SECURE_PROXY_SSL_HEADER` set.
- `collectstatic --dry-run`: 127 files resolve into `staticfiles/`.
- **`/health/` actually requested** via Django's test client (not just settings resolution): returns `200` / body `ok`. Requires `ALLOWED_HOSTS=testserver` for the test, since the test client sends `Host: testserver`.
- **WSGI callable imports**: `from domowa_apteka.wsgi import application` → `WSGIHandler`. This is the closest available check that `gunicorn domowa_apteka.wsgi` will start, since gunicorn cannot run on Windows (no `fcntl`) and so is untestable locally.

**Deviations from the plan as drafted:**

1. **`uv` was not on the agent's PATH** (blocker, resolved). It was installed via `pip install --user` to `C:\Users\tszre\AppData\Roaming\Python\Python311\Scripts\uv.exe` and was on the *persisted* PATH, but the running Claude Code process held a pre-change environment. Fixed by restarting Claude Code from a fresh terminal, not by editing PATH. Note for future sessions: a PATH change requires restarting the agent host, not just the shell. `uv 0.12.0`.
2. **Added a `_csv_env()` helper** in `settings.py` instead of the plan's literal `os.environ.get(X, "").split(",")`. The plan's form returns `['']` (a list holding one empty string), not `[]`. For `CSRF_TRUSTED_ORIGINS` — deliberately unset until Phase 4 — Django raises at startup because every origin must carry a scheme, so the plan as drafted would have crash-looped the first `railway up` with an error pointing nowhere near its cause. Helper filters empties for both `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS`.
3. **`SECRET_KEY` — resolved the plan's internal contradiction** (line 25 offered both strict `os.environ[...]` and a `.get()` fallback). Took the `.get()` fallback with the scaffold's insecure key as the local-only default; strict indexing would break the Phase 1 local-parity check, and no dotenv loader is in scope. Production safety comes from Phase 3 setting a real `SECRET_KEY`; `check --deploy` flags W009 if the insecure default ever reaches prod.
4. **`STORAGES` declares both `default` and `staticfiles` backends**, not just `staticfiles` as the plan snippet shows — an explicit full declaration avoids depending on Django-version-specific merge behaviour for partially-specified `STORAGES`.
5. **`DEBUG` default confirmed as `'False'`** per the plan. Consequence not called out in the plan: local `runserver` now needs `DEBUG=True` set explicitly, or it serves no admin CSS and returns bare 500s.
6. **Added `SESSION_COOKIE_SECURE` and `CSRF_COOKIE_SECURE`, both gated on `not DEBUG`** — beyond the plan's Phase 0 list, but load-bearing for Phase 4's "log into `/admin/` over HTTPS" verification, and with zero effect on what the healthcheck receives. This clears `check --deploy`'s `W012` and `W016`. Both gate on `DEBUG`, which compounds deviation 5's ergonomics note rather than adding a new constraint.

**Deliberately deferred (not oversights):** `check --deploy` still reports 2 warnings, both left off on purpose until the first deploy is green:
- `W008` `SECURE_SSL_REDIRECT` — if Railway's healthcheck reaches the container without an `X-Forwarded-Proto` header, the redirect turns `/health/`'s 200 into a 301 and fails the deploy. That is precisely the opaque rollback loop Phase 4 budgets a debugging bullet for; enabling it pre-deploy trades a real risk for a lint clean.
- `W004` `SECURE_HSTS_SECONDS` — HSTS is cached by browsers and semi-irreversible; not worth enabling before the domain even exists.

Revisit both once Phase 4 verification passes.
