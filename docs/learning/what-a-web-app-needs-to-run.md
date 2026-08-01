---
title: "What does a web app actually need to run? (and what settings.py, urls.py, wsgi.py, asgi.py each do)"
slug: what-a-web-app-needs-to-run
date: 2026-08-01
tags: [web-fundamentals, django, deployment]
classification: mixed
prerequisites: [django-project-vs-app]
---

# What does a web app actually need to run? (and what settings.py, urls.py, wsgi.py, asgi.py each do)

## Why this came up

[django-project-vs-app.md](django-project-vs-app.md) used `settings.py`, `urls.py`,
`wsgi.py`, and `asgi.py` by name without explaining what each one actually does — fair
question, since those are exactly the files `django-admin startproject` generated inside
`domowa_apteka/` and they're not going away. This doc explains what a web app needs to
run *at all*, generically, then shows which of these four files covers which need.

## Builds on

See [django-project-vs-app.md](django-project-vs-app.md) for the project-vs-app split —
this doc is about what lives *inside* the project container, specifically the four
top-level files that aren't an app.

## The concept, from the ground up

Strip away Django entirely for a second. Any web app, in any language or framework, is a
long-running process that a server keeps alive, and that process needs exactly four
ingredients to do anything useful:

1. **An entry point** — one specific object or function the server process actually calls
   for every incoming request. Something has to exist for the server to "plug into." No
   entry point, no way for a request to ever reach your code.
2. **Configuration** — settings that apply everywhere: which database to talk to, which
   features are switched on, secret keys, debug mode. This needs to live somewhere central
   that all the code can read, and (this is the AGENTS.md hard rule already in this repo)
   secrets in it need to come from environment variables, not be hardcoded. See
   [config-in-dev-vs-prod.md](config-in-dev-vs-prod.md) for how that env-var mechanism
   actually works and what `DEBUG`, `SECRET_KEY`, and `ALLOWED_HOSTS` each control.
3. **Routing** — a lookup table mapping "a request came in for this URL path" to "run this
   specific piece of handler code." Without it, the entry point would have no idea what to
   actually do with an incoming request.
4. **The handler code itself** — what actually runs once routing has picked it. This is
   what apps hold (see the prerequisite doc) — models, views, business logic.

Every real framework has all four. They just don't always give them their own dedicated
file with an obvious name — Django does, which is exactly why these four files exist and
why `django-admin startproject` created them on day one, before any app or feature code.

## The fifth ingredient: an actual running process

The four ingredients above are all *static* — files sitting on disk (unrelated to "static
files" in the CSS/JS sense; see
[static-files-collectstatic-and-whitenoise.md](static-files-collectstatic-and-whitenoise.md)
for that meaning). None of them do
anything by themselves. A web app also needs one more thing that isn't a file at all: an
**OS process that is actually running and listening on a network port**, ready to accept
incoming connections and, for each one, invoke the entry point.

That's what "starting the server" means. Before you ran anything, `settings.py`,
`urls.py`, and the rest were just inert configuration — nothing was listening on
`127.0.0.1:8000`, so a browser request there would fail to connect (not "get an error
page" — there'd be nothing on the other end to even respond). Running
`uv run manage.py runserver` started exactly that process: we confirmed it afterwards two
ways — `Get-NetTCPConnection -LocalPort 8000` showed a real OS process (PID, `python.exe`)
bound to port 8000, and `curl http://127.0.0.1:8000/` got back an actual HTTP 200 response
because something was now there to answer it.

Two different programs can fill this "running process" role, and which one you use depends
on context:

- **`manage.py runserver`** — Django's own lightweight development server. Single process,
  auto-reloads when you edit code, deliberately not hardened or optimized — it exists
  purely for local development convenience and is not meant to face real traffic.
- **A production server** (e.g. `gunicorn`, invoked as `gunicorn domowa_apteka.wsgi`) —
  what actually runs in production (this project deploys to Railway per
  `context/foundation/infrastructure.md`). It's a separate program that *uses* `wsgi.py`
  (or `asgi.py`) as its entry point rather than having Django's dev server logic built in,
  typically runs multiple worker processes for concurrency, and has none of `runserver`'s
  "for convenience only" warnings baked in.

Same underlying need — a running, port-bound process — met by a throwaway tool locally and
a production-grade one when deployed.

## In terms you already know

| This project's concept | What it's like in your world |
| --- | --- |
| Entry point (`wsgi.py` / `asgi.py`) | The **Integration Runtime** in ADF — the actual compute engine a hosting process starts up to execute things. You don't author pipeline logic here; it's the thing that gets *invoked* to run what you authored elsewhere. |
| Configuration (`settings.py`) | The factory's **Linked Services + Global Parameters** — shared config (connection strings, feature switches) every pipeline can draw on, authored once, centrally. |
| Routing (`urls.py`) | The factory's **Triggers** — the mapping of "when this happens, run that pipeline." Here it's "when a request hits this path, run that view" instead of "when this schedule/event fires, run that pipeline," but it's the same shape: an external signal looked up against a table to decide what runs. |
| A running server process (`runserver` locally, `gunicorn` in prod) | A **Databricks cluster or SQL Warehouse in "Running" state** — the pipeline/query definitions exist regardless, but nothing executes until compute is actually up. A stopped cluster doesn't give you an error *from your pipeline* — the connection just can't be made at all, same as a browser hitting a port nothing is listening on. |

## What's universal vs. specific to this project's choices

**True for any web app, not just Django:**
- Every framework needs an entry point, central config, and a routing mechanism — that's
  not negotiable, it's what "a web app" structurally means.
- Keeping secrets out of source control and in environment variables instead is universal
  good practice, not a Django rule (it's just enforced more explicitly here because
  `AGENTS.md` already calls it out for this repo's `SECRET_KEY`).

**Specific because this project picked Django:**
- Django gives each of the three non-handler ingredients its **own dedicated file** with a
  fixed conventional name (`settings.py`, `urls.py`) or, for the entry point specifically,
  **two files** (`wsgi.py` and `asgi.py`) rather than one. That split exists because Django
  supports two different server protocols:
  - **WSGI** (`wsgi.py`) — the traditional, synchronous protocol: one request handled at a
    time per worker. This is what a plain Django app running behind something like
    `gunicorn` uses, and it's almost certainly what `domowa-apteka` will deploy with on
    Railway for the MVP.
  - **ASGI** (`asgi.py`) — a newer, async-capable protocol needed only if you want
    WebSockets, long-lived connections, or async views. Django ships this file by default
    even though this project doesn't need it yet, in case a future feature does.
  - A framework like Flask doesn't hand you separate named files for this at all — you'd
    wire up the equivalent yourself, less explicitly.
  - Railway itself doesn't care which of the two you use — it just runs whatever start
    command you configure (e.g. `gunicorn domowa_apteka.wsgi`), pointed at whichever entry
    point file you chose.

**Can you create or rename these files yourself?**
Yes — nothing about the filenames `settings.py`, `urls.py`, `wsgi.py`, `asgi.py` is magic.
`startproject` just generates them with these conventional names *and* wires two settings
to point at them by dotted Python path: `ROOT_URLCONF` (in `settings.py`, pointing at
`urls.py`) and `WSGI_APPLICATION` (pointing at `wsgi.py`). If you renamed `wsgi.py` to
`entrypoint.py`, Django wouldn't care as long as `WSGI_APPLICATION` and your server start
command were updated to match — the names are convention plus a couple of cross-references
that need to stay in sync, not something the framework enforces structurally.

## Go deeper

- [Difference Between ASGI and WSGI in Django — GeeksforGeeks](https://www.geeksforgeeks.org/python/difference-between-asgi-and-wsgi-in-django/) —
  clear, beginner-friendly comparison with concrete examples.
- [How to deploy with WSGI — Django official docs](https://docs.djangoproject.com/en/5.2/howto/deployment/wsgi/)
  and [How to deploy with ASGI — Django official docs](https://docs.djangoproject.com/en/5.2/howto/deployment/asgi/) —
  the authoritative reference for both entry-point files, matching this project's Django version.

## Quick recap

**Q: Why does a brand-new Django project already have these four files before any feature
code exists?**
A: Because a project needs an entry point, config, and routing to be a working, runnable
thing at all — `startproject` gives you a minimal but complete skeleton on day one, even
with zero apps.

**Q: If domowa-apteka never needs WebSockets, can `asgi.py` just be deleted?**
A: You could, but there's no benefit to it — it costs nothing sitting unused, and deleting
it forecloses using async features later without regenerating it. Leave it.

**Q: I ran `manage.py runserver` locally — does that use wsgi.py or asgi.py?**
A: Neither, directly — Django's development server (`runserver`) has its own internal
lightweight server for local use. `wsgi.py`/`asgi.py` matter for whatever server process
production deployment (Railway) actually starts.

**Q: Where would I add a new URL path once the first app exists?**
A: In `urls.py` — that's the routing table from the ground-up explanation above. A common
pattern is each app getting its own small `urls.py` that the project's root `urls.py`
pulls in with `include()`, so routing for one feature stays with that feature's app.

**Q: Why do I need to "start" the app at all — isn't the code already there?**
A: The code being on disk isn't enough; nothing is listening for requests until an actual
process is running and bound to a port. `uv run manage.py runserver` is what creates that
process locally — see [python-dependency-management-pip-uv-venv.md](python-dependency-management-pip-uv-venv.md)
for how `uv run` locates the right Python environment to run it in.

**Q: How do I confirm the server is actually running, beyond just opening the browser?**
A: Two independent checks: `Get-NetTCPConnection -LocalPort 8000 -State Listen` shows the
real OS process (PID, `python.exe`) bound to that port, and `curl` (or a browser) getting
an HTTP response back — no response/connection-refused means nothing's listening there.
