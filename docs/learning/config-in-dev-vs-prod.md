---
title: "How does the same code run differently in dev and production? (environment variables, DEBUG, SECRET_KEY, ALLOWED_HOSTS)"
slug: config-in-dev-vs-prod
date: 2026-08-01
tags: [deployment, configuration, django, web-fundamentals, security]
classification: mixed
prerequisites: [what-a-web-app-needs-to-run, from-dev-scaffold-to-production-ready]
---

# How does the same code run differently in dev and production?

## Why this came up

Phase 0 of `context/changes/deployment/deployment-plan.md` rewrites four lines of
`domowa_apteka/settings.py` to read from `os.environ` instead of holding literal values, and
Phase 3 then sets those same names via `railway variable set`. That's the whole mechanism
by which one git repository behaves like a safe local sandbox on your laptop and a locked-down
service in production. This doc explains where those values come from, what each of the four
settings actually controls, and the one Python wart that makes this pattern bite people.

## Builds on

- [what-a-web-app-needs-to-run.md](what-a-web-app-needs-to-run.md) established `settings.py`
  as ingredient #2, central configuration, and noted that secrets belong in environment
  variables. This doc is the *how* and *why* behind that one line.
- [from-dev-scaffold-to-production-ready.md](from-dev-scaffold-to-production-ready.md) for
  where these changes sit among the rest of Phase 0.

## The concept, from the ground up

### The problem: one codebase, several environments

Your laptop and the production server run the *same files*. But they must not behave the
same: locally you want a throwaway database and verbose errors; in production you want the
real database and no leaked internals. There are only three places that difference can live:

1. **In the code, edited before each deploy.** Rejected everywhere, for the obvious reason
   — it's a manual step, and the one time someone forgets is the time secrets ship.
2. **In separate config files per environment** (`settings_dev.py`, `settings_prod.py`).
   Works, still used, but now the production file either contains secrets (so it can't be
   committed) or points at something else that does.
3. **Outside the codebase entirely, in the environment the process starts in.** This is the
   modern default, usually called *12-factor config*, and it's what the plan uses.

An **environment variable** is just a key/value pair that the operating system hands to a
process when it starts. `os.environ` is Python reading that dictionary. Nothing more
magical than that — but the consequence is significant: the value is supplied by *whoever
starts the process*, so the same code can be started five different ways with five different
configurations, and none of those values ever touch git.

### Who actually sets them

| Environment | Where the value comes from |
| --- | --- |
| Your laptop, ad-hoc | You export it in the shell before running, or rely on the code's local fallback default |
| Your laptop, repeatable | A `.env` file (already gitignored in this repo) read by a loader library like `python-dotenv` |
| Railway | The platform injects them into the container at start; you set them with `railway variable set` or in the dashboard |
| Railway, for the database | A **reference variable** — `DATABASE_URL=${{Postgres.DATABASE_URL}}` — so the value is resolved from the Postgres service at deploy time rather than copy-pasted |

That last row is why the plan can say "keeps local dev on SQLite with zero config while prod
picks up Railway's injected Postgres URL automatically": `dj_database_url.config(default="sqlite:///db.sqlite3")`
reads `DATABASE_URL` if it exists and falls back to SQLite if it doesn't. Locally it doesn't
exist, so you get SQLite; on Railway it does, so you get Postgres. Same line of code.

### The wart: everything in the environment is a string

There is no boolean, integer, or list type in an operating system's environment. Every value
is text. So this innocent-looking line is a genuine production incident waiting to happen:

```python
DEBUG = bool(os.environ.get("DEBUG"))   # WRONG
```

`bool("False")` is `True` in Python — any non-empty string is truthy. Setting `DEBUG=False`
in Railway would produce `DEBUG = True` in the running app, and you would be serving stack
traces to the public while believing debug was off. The plan flags this explicitly; the
correct form is an explicit string comparison:

```python
DEBUG = os.environ.get("DEBUG", "False") == "True"
```

The same wart in list form: `"".split(",")` returns `[""]` — a list containing one empty
string, not an empty list. The plan's `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS` lines both
have this shape and both need the empties filtered out, e.g.
`[h for h in os.environ.get("ALLOWED_HOSTS", "").split(",") if h]`.

This is not a Django problem or a Python problem. Every config-from-environment system in
every language has it, because the environment is stringly-typed all the way down.

### What the four settings actually do

**`SECRET_KEY`** — not "a password for the app." It's the key Django uses to *sign* things
it hands to browsers: session cookies, password-reset tokens, CSRF tokens (see
[csrf-and-https-behind-a-proxy.md](csrf-and-https-behind-a-proxy.md)). A signature proves
"this cookie was issued by me and hasn't been edited." Anyone holding the key can mint a
cookie that says *I am user #1, the admin*, and Django will believe it. The scaffold's key
is committed to this repo in plain text (`settings.py:23`), which is why Phase 3 generates a
fresh one for production and Phase 0 makes the setting read from the environment. Rotating
it invalidates every existing session — an acceptable one-time cost now, a logout-everyone
event later.

**`DEBUG`** — the single highest-leverage flag in the file, because in Django it changes at
least four behaviours at once:

| `DEBUG=True` | `DEBUG=False` |
| --- | --- |
| Errors render a full interactive traceback: source lines, local variable values, settings | Errors render a plain 500 page; details go to logs only |
| `ALLOWED_HOSTS` empty is tolerated (localhost implied) | `ALLOWED_HOSTS` is enforced; empty means **every** request is rejected with 400 |
| `django.contrib.staticfiles` serves CSS/JS automatically | It does not — you need WhiteNoise or equivalent (see [static-files-collectstatic-and-whitenoise.md](static-files-collectstatic-and-whitenoise.md)) |
| Every SQL query is retained in memory for the debug toolbar | Not retained (retaining them in a long-running process is a slow memory leak) |

That bundling is why "just flip DEBUG and see what breaks" in production is a bad plan, and
why `manage.py check --deploy` exists.

**`ALLOWED_HOSTS`** — a list of hostnames this app is willing to answer to, checked against
the incoming request's `Host` header. Its purpose is blocking *Host header poisoning*: an
attacker sends a request with `Host: evil.com`, your app generates a password-reset email
containing a link built from that header, and the victim clicks through to the attacker's
site. The list is the app asserting "I am `domowa-apteka.up.railway.app` and nothing else."
The plan starts with `*` (allow anything) for the first deploy precisely because the platform's
health-check probe may arrive with an internal hostname you can't predict, then tightens it
once `railway logs` reveals the real one.

**`DATABASE_URL`** — one string encoding driver, credentials, host, port, and database name:
`postgresql://user:pass@host:5432/dbname`. `dj-database-url` parses it into the `DATABASES`
dict Django expects. The value is a credential, which is exactly why it arrives as an
injected environment variable rather than living in `settings.py`.

## In terms you already know

| This project's concept | What it's like in your world |
| --- | --- |
| Environment variables supplying per-environment config | **ARM template parameter files** (`parameters.dev.json` / `parameters.prod.json`) against one published ADF definition — same artifact, values bound at deployment time, not authoring time. |
| Secrets specifically (`SECRET_KEY`, `DATABASE_URL`) | A **Databricks secret scope / Key Vault–backed reference** — the notebook says `dbutils.secrets.get(...)`, the value never appears in the notebook or in source control. |
| Railway reference variable `${{Postgres.DATABASE_URL}}` | A **Key Vault reference in an App Service setting** — the config holds a pointer, the platform resolves the actual value at start-up. |
| `DEBUG = True` | An **ADF Debug run / an interactive Databricks notebook** — rich, verbose, shows you everything, and precisely for that reason not what you expose to consumers. |
| `SECRET_KEY` as a signing key | The **signing key behind a Storage SAS token or a Power BI embed token** — possession of the key is the authority to mint valid tokens; leaking it is not "a password leak," it's "anyone can issue credentials." |
| `ALLOWED_HOSTS` | An **Azure SQL / Storage firewall allow-list**, but on the name the caller used rather than the IP it came from — "I only answer to these identities." |
| Everything in the environment being a string | **ADF pipeline parameters being stringly-typed** until you explicitly cast — `@bool('false')` has the same footgun energy as `bool("False")`. |

## What's universal vs. specific to this project's choices

**True for any web app on any platform:**
- Configuration that varies by environment comes from the environment; secrets never enter
  source control. This is 12-factor orthodoxy and applies to Node, .NET, Go, everything.
- Environment values are strings and must be parsed deliberately.
- Some notion of "which hostnames am I" and "how verbose are my errors" exists in every
  serious framework, under different names.

**Specific because this project picked Django + Railway:**
- The specific setting *names* (`DEBUG`, `SECRET_KEY`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`)
  and the fact that they live in one module-level Python file that Django imports are Django's
  design. Flask uses `app.config`; .NET uses `appsettings.{Environment}.json` layered with
  environment overrides.
- Django bundling four unrelated behaviours behind one `DEBUG` boolean is a Django-specific
  trait, and the main reason its deployment checklist exists.
- `dj-database-url` is a third-party library, not a framework feature. The `DATABASE_URL`
  convention itself, though, is near-universal across hosting platforms — Railway, Render,
  Fly.io, and Heroku before them all inject that exact variable name.
- Reference variables (`${{Postgres.DATABASE_URL}}`) are Railway syntax; other platforms have
  equivalents with different spellings.

## Go deeper

- [The Twelve-Factor App — III. Config](https://12factor.net/config) — three short paragraphs
  that are the origin of this whole pattern, and the source of the useful litmus test: "could
  this repo be open-sourced right now without leaking credentials?"
- [Settings — Django official docs](https://docs.djangoproject.com/en/5.2/topics/settings/)
  and the [settings reference](https://docs.djangoproject.com/en/5.2/ref/settings/) for the
  exact semantics of `DEBUG`, `ALLOWED_HOSTS`, and `SECRET_KEY`.

## Quick recap

**Q: What is an environment variable, in one sentence?**
A: A key/value pair the operating system hands to a process at start-up, readable in Python
via `os.environ` — configuration supplied from outside the code, by whoever launches it.

**Q: Why is `DEBUG = bool(os.environ.get("DEBUG"))` a bug?**
A: Environment values are always strings, and `bool("False")` is `True`. Setting `DEBUG=False`
would leave debug mode on in production and publicly expose stack traces. Compare to the
string `"True"` explicitly instead.

**Q: If `SECRET_KEY` leaks, what can an attacker actually do?**
A: Forge anything Django signs — most importantly session cookies, so they can impersonate any
user including admins, without ever knowing a password.

**Q: When would I reach for `ALLOWED_HOSTS = "*"` and when is that wrong?**
A: Acceptable as a deliberate, temporary first-deploy measure when you don't yet know what
hostname the platform's health check uses — which is exactly the plan's Phase 0/Phase 4
sequence. Wrong as a permanent state: tighten it to the real domain once `railway logs` shows
you what's actually arriving.

**Q: Why can the same `DATABASES` line give me SQLite locally and Postgres in production?**
A: Because `dj_database_url.config(default="sqlite:///db.sqlite3")` reads `DATABASE_URL` if
present and falls back if not. Locally it's absent; Railway injects it. See
[database-migrations-and-dev-prod-parity.md](database-migrations-and-dev-prod-parity.md) for
what still differs between the two engines despite the shared code.
