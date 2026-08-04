---
title: "Why can't you just deploy the scaffold as-is? (What Phase 0 of the deployment plan is doing)"
slug: from-dev-scaffold-to-production-ready
date: 2026-08-01
tags: [deployment, django, web-fundamentals, production]
classification: mixed
prerequisites: [what-a-web-app-needs-to-run, database-migrations-and-dev-prod-parity]
---

# Why can't you just deploy the scaffold as-is? (What Phase 0 of the deployment plan is doing)

## Why this came up

`context/changes/deployment/deployment-plan.md` has six phases. Phases 1–5 are all Railway
commands — install a CLI, create a project, set variables, deploy. Phase 0 is different:
it's nine checkboxes of **changes to your own code**, before Railway is even mentioned.
The obvious question is why that's needed at all: the app runs fine locally today, so what
exactly is missing? This doc is the map of Phase 0 — what each item is protecting against,
and which of the three deeper docs covers it.

## Builds on

- [what-a-web-app-needs-to-run.md](what-a-web-app-needs-to-run.md) — the five ingredients
  (entry point, config, routing, handler code, a running process). Phase 0 is mostly about
  ingredient #2, **configuration**, and one new ingredient production adds.
- [database-migrations-and-dev-prod-parity.md](database-migrations-and-dev-prod-parity.md) —
  why the same model code can target SQLite locally and Postgres in production.

## The concept, from the ground up

`django-admin startproject` optimizes for one thing: that you can type one command and see
a working app in your browser thirty seconds later. Every default it wrote into
`domowa_apteka/settings.py` serves that goal, and **every one of them is actively wrong in
production**:

| Scaffold default | Great locally because… | Dangerous in production because… |
| --- | --- | --- |
| `SECRET_KEY = 'django-insecure-…'` (hardcoded, line 23) | Zero setup — it just works | It's committed to git. Anyone who reads the repo can forge login sessions |
| `DEBUG = True` (line 26) | Errors show a full stack trace in the browser | That stack trace shows your source code, settings, and query values **to whoever triggered the error** |
| `ALLOWED_HOSTS = []` (line 28) | Django quietly permits `localhost` when `DEBUG=True` | With `DEBUG=False` this list being empty rejects *every* request — including the platform's health check |
| `DATABASES` → SQLite file (line 75) | No database server to install | The file lives on the container's disk, which is wiped on every redeploy |
| No static-file serving config | `DEBUG=True` makes Django serve CSS/JS itself | That helper switches **off** at `DEBUG=False`, so the admin site loads with no styling |

Notice the pattern: three of these five are not "you forgot to configure production," they
are **behaviour that silently changes the moment `DEBUG` flips to `False`**. That's the
single most surprising thing about Phase 0 and the reason it can't be skipped and fixed
later — flipping one flag changes four unrelated subsystems at once.

### The sixth ingredient production adds: something is watching you

Locally, you are the supervisor. You start `runserver`, you look at the terminal, you
notice if it crashed. In production the platform plays that role, and it judges your app
by a criterion local dev never applies: it makes an HTTP request to a **health check path**
every few seconds and expects a `200 OK` back. No 200 → it assumes the app is broken →
it kills the container and rolls back to the previous deploy.

Your app currently has exactly one route, `/admin/`. A health check aimed anywhere else
gets a 404, which is not a 200, so the platform kills a perfectly healthy app — and the
failure surfaces as a deploy that never goes live, which reads like a *build* failure. That
is why Phase 0 adds a two-line `/health/` view that returns the string `ok`. It's not
ceremony; it's the only channel your app has to tell the platform "I'm alive."

Even better: the same request is subject to `ALLOWED_HOSTS`. If the platform's probe
arrives with an internal hostname you didn't allow, Django answers **400 Bad Request** —
still not a 200, still a rollback loop, but now with a completely different cause. The plan
calls this out (Phase 4, "check `railway logs` for a 400 on `/health/` first") precisely
because the two failures look identical from outside.

### Phase 0, item by item

| Phase 0 item | What it's really solving | Covered in depth by |
| --- | --- | --- |
| Add `gunicorn`, `psycopg`, `dj-database-url`, `whitenoise` | Production needs a real server process, a Postgres driver, a way to read the DB URL from the environment, and a way to serve static files | [what-a-web-app-needs-to-run.md](what-a-web-app-needs-to-run.md) (gunicorn), this doc |
| `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS` from `os.environ` | Same code, different behaviour per environment, with no secrets in git | [config-in-dev-vs-prod.md](config-in-dev-vs-prod.md) |
| `dj_database_url.config(...)` replacing the SQLite block | SQLite locally, Postgres in prod, chosen by an env var rather than an edit | [config-in-dev-vs-prod.md](config-in-dev-vs-prod.md) + [database-migrations-and-dev-prod-parity.md](database-migrations-and-dev-prod-parity.md) |
| WhiteNoise middleware + `STATIC_ROOT` + `STORAGES` | Serving CSS/JS/images once Django's dev-only helper switches off | [static-files-collectstatic-and-whitenoise.md](static-files-collectstatic-and-whitenoise.md) |
| `/health/` endpoint | Giving the platform's supervisor a 200 to find | this doc, above |
| `ALLOWED_HOSTS` covering the health-check host | Not answering 400 to the probe | [config-in-dev-vs-prod.md](config-in-dev-vs-prod.md) |
| `CSRF_TRUSTED_ORIGINS` + `SECURE_PROXY_SSL_HEADER` | Being able to log into `/admin/` over HTTPS through the platform's TLS front door | [csrf-and-https-behind-a-proxy.md](csrf-and-https-behind-a-proxy.md) |
| `.python-version` file | The build machine picking the same Python you develop against | this doc, below |
| `manage.py check --deploy` | Django's own audit of everything above, run *before* you deploy | this doc, below |

### The two items that don't need their own doc

**`.python-version`** — a one-line file at the repo root containing e.g. `3.11`. Locally
`uv` reads it to pick an interpreter; the build platform reads the same file to decide
which Python to install. Without it the platform guesses, and a guess that doesn't match
`uv.lock`'s assumptions produces build failures that have nothing to do with your code.
It is the same instinct as pinning a Databricks Runtime version on a job cluster instead of
letting it float.

**`manage.py check --deploy`** — Django ships a production-readiness linter. Run it with
production-ish environment variables and it reports every setting that's unsafe
(`DEBUG` on, weak `SECRET_KEY`, missing HTTPS hardening) without deploying anything. This
is the cheapest possible feedback loop in the whole plan: run it before `railway up`, not
after the first failed deploy.

## In terms you already know

| This project's concept | What it's like in your world |
| --- | --- |
| The scaffold's dev defaults (insecure key, `DEBUG=True`, SQLite) | An ADF pipeline authored in **Debug mode against a dev linked service** — genuinely useful, genuinely not the thing you publish. Nobody would point the debug configuration at prod and call it a release. |
| A platform health check probing `/health/` | An **Azure App Service / Load Balancer health probe** — it pings a path on a fixed interval and pulls the instance out of rotation if it doesn't get a 200, regardless of whether the app is actually fine. |
| `.python-version` pinning the build's interpreter | Pinning the **Databricks Runtime version** on a job cluster instead of letting it float to "latest" and discovering a behaviour change at 3 a.m. |
| `manage.py check --deploy` | The **Best Practices Analyzer / Tabular Editor BPA rules** you run over a model before publishing — a static audit against known production pitfalls, not a test run. |

## What's universal vs. specific to this project's choices

**True for any web app on any platform:**
- Development defaults are deliberately insecure and deliberately convenient; promoting
  them to production unchanged is the single most common first-deploy mistake, in every
  framework and language.
- Configuration that varies per environment has to come from *outside* the code, or you end
  up with edit-before-deploy rituals that eventually get skipped.
- Ephemeral filesystems: on essentially every modern container platform, files written by
  the running app disappear on redeploy. Any state you care about belongs in a database or
  object storage, never on local disk.
- Something external decides whether your app is healthy, and it does so on evidence you
  must deliberately provide.

**Specific because this project picked Django + Railway:**
- The `DEBUG` flag bundling *four* behaviours (error page detail, `ALLOWED_HOSTS`
  enforcement, static-file serving, and some security-header defaults) is a Django trait.
  Flask, for example, has a `debug` flag too but doesn't hang static-file serving off it in
  the same way.
- `dj-database-url` and WhiteNoise are third-party conveniences, not framework features.
  A Node/Express app would use different libraries; a platform-as-a-service with a built-in
  CDN might not need WhiteNoise at all.
- Railway specifically infers a lot (it auto-detects `uv.lock` and can even guess a Django
  start command). The plan deliberately overrides that inference with an explicit
  `railway.json` — a reproducible-from-source choice, not a requirement.

## Two bugs in the plan's Phase 0 as written

Worth knowing before you approve it, because both are the kind that fail *at runtime*, not
at review:

1. **`STORAGES` replaces the whole dict, it doesn't merge.** Phase 0 shows
   `STORAGES = {"staticfiles": {...}}`. Django reads `settings.STORAGES` as-is (verified in
   `django/core/files/storage/handler.py`), so writing only the `staticfiles` key deletes
   the `default` key and any code touching regular file storage raises
   `Could not find config for 'default' in settings.STORAGES`. Both keys must be present.
2. **`"".split(",")` returns `[""]`, not `[]`.** The plan's pattern for `ALLOWED_HOSTS` and
   `CSRF_TRUSTED_ORIGINS` produces a list containing one empty string when the variable
   isn't set. For `CSRF_TRUSTED_ORIGINS` that trips Django's `4_0.E001` system check
   (entries must include a scheme); for `ALLOWED_HOSTS` it's a host entry that matches
   nothing and hides the fact that you configured nothing. Filter the empties.

## Go deeper

- [Django Deployment Checklist, explained](https://testdriven.io/blog/django-deployment-checklist/) —
  walks the same ground as Phase 0 in prose, aimed at people deploying their first Django app.
- [Deployment checklist — Django official docs](https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/) —
  the authoritative list `manage.py check --deploy` is checking against.

## Quick recap

**Q: Why is Phase 0 code changes rather than Railway configuration?**
A: Because the scaffold isn't deployable to *any* Postgres-and-env-vars platform yet, not
just not-to-Railway. Nothing in Phase 0 is Railway-specific; the same nine items would be
needed on Fly.io, Render, or a plain VM.

**Q: What actually breaks if I deploy with `DEBUG=True` and skip the rest?**
A: The app might well appear to work — which is the trap. You'd be publicly serving stack
traces containing your settings and source, with a signing key that's in a public repo, on
a database file that vanishes at the next deploy.

**Q: Why does a health check endpoint matter if I can just open the site myself?**
A: Because the platform is deciding, continuously and without you, whether to keep the
container alive. A missing or 400-returning `/health/` makes it roll back a working deploy,
and the symptom looks like a build failure rather than a routing problem.

**Q: When would I revisit these choices rather than keep them?**
A: When the MVP assumptions expire — `ALLOWED_HOSTS=*` should tighten to the real domain
once it exists, and the non-manifest static storage should become the manifest variant once
static assets stabilize (see
[static-files-collectstatic-and-whitenoise.md](static-files-collectstatic-and-whitenoise.md)).

**Q: What's the cheapest way to find out whether Phase 0 is complete?**
A: `uv run manage.py check --deploy` with production-like env vars set, locally, before
touching Railway at all.
