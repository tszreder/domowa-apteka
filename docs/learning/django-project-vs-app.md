---
title: "What's the difference between a Django project and a Django app?"
slug: django-project-vs-app
date: 2026-07-31
tags: [django, web-fundamentals, scaffolding]
classification: mixed
prerequisites: []
---

# What's the difference between a Django project and a Django app?

## Why this came up

Right now `domowa-apteka` only has the `domowa_apteka/` package — `settings.py`,
`urls.py`, `wsgi.py`, `asgi.py` — created by `django-admin startproject`. Per
`AGENTS.md`, no feature app has been created yet, and the very next real step is running
`manage.py startapp <name>` to start building the actual pharmaceutical-tracking feature.
Before that command runs, it's worth knowing what it's about to create and why Django
makes you create it at all.

## The concept, from the ground up

Django splits "the thing you deploy" from "a feature module" into two different concepts,
with two different names:

- A **project** is the whole deployable thing. It's the top-level Python package —
  `domowa_apteka/` here — holding the settings that apply globally (database connection,
  installed features, secret key), the URL routing table that decides what handles each
  incoming request, and the entry points (`wsgi.py`/`asgi.py`) a server actually starts.
  There is exactly one project per deployed site.
- An **app** is a self-contained module for one feature domain — user accounts, or (soon,
  here) pharmaceutical tracking. It holds its own models (data shape), views (request
  handling logic), and templates for that one feature. A project is built by wiring
  together one or more apps; the same app could in principle be lifted out and reused in
  a different project with little change.

`manage.py startapp inventory` (or whatever name is chosen) generates a new folder next to
`domowa_apteka/`, with its own `models.py`, `views.py`, `admin.py`, and migration folder —
but it does nothing on its own until it's added to `INSTALLED_APPS` in `settings.py` and
wired into `urls.py`. That registration step is what turns "a folder with some Python
files" into "a part of the running site."

## In terms you already know

| This project's concept | What it's like in your world |
| --- | --- |
| Django **project** (`domowa_apteka/`) | An **ADF Data Factory instance** — the container holding global config (linked services ≈ database connection, integration runtime ≈ deployment target) and the thing that actually gets deployed and run as one unit. |
| Django **app** (e.g. a future `inventory` app) | An **ADF pipeline** inside that factory — self-contained, holds its own internal logic, and only does something once it's registered/triggered inside the factory. Could be copied into a different factory largely as-is. |
| `INSTALLED_APPS` in `settings.py` | The list of pipelines a factory actually knows about — an app that exists as a folder but isn't listed here is like a pipeline that was authored but never published/attached to the factory. |

## What's universal vs. specific to this project's choices

**True for any web app, not just Django:**
- Every non-trivial web app separates global/shared configuration (database connection,
  secrets, which features are turned on) from the code for one specific feature — the
  names differ, but the split itself is close to universal.
- A "feature module" that can be unplugged and reused across projects is a common design
  goal, not a Django invention.

**Specific because this project picked Django:**
- Django is unusually explicit about it: it gives you a CLI command (`startapp`) that
  generates the folder structure, and *requires* you to list every app by name in
  `INSTALLED_APPS` before it does anything. A framework like Flask doesn't force this
  structure at all — you could put an entire small site in one file if you wanted to.
- Railway (this project's deployment platform) doesn't know or care about this Django-level
  split — it just runs whatever start command you give it (e.g. a `gunicorn` process
  pointing at `domowa_apteka.wsgi`). The project/app distinction is purely a Django-code
  organization concept, invisible at the deployment layer.

## Go deeper

- [Difference Between App And Project In Django — PythonGuides](https://pythonguides.com/django-app-vs-project/) —
  beginner-friendly walkthrough with concrete examples, doesn't assume prior web-dev background.
- [Django official tutorial, Part 1 — "Creating an app"](https://docs.djangoproject.com/en/5.2/intro/tutorial01/#creating-an-app) —
  the authoritative reference, matches the Django version this project uses (5.2).

## Quick recap

**Q: If I delete a Django app folder, does the project still run?**
A: It'll run, but anything the deleted app provided (its models, views, admin pages) is
gone, and if it's still listed in `INSTALLED_APPS` Django will error on startup — you'd
need to remove that entry too.

**Q: Can one project have zero apps?**
A: Yes — a fresh `django-admin startproject` (which is `domowa-apteka`'s current state)
is exactly that: a working project with no feature apps yet. It won't do anything useful
until at least one app is added.

**Q: When would I actually create a second app instead of adding to an existing one?**
A: When you have a genuinely separate feature domain — e.g. "pharmaceutical inventory"
vs. "household accounts/invites" are different enough concerns that most Django projects
would give them separate apps, similar to how you'd give two unrelated data domains
separate pipelines rather than one giant pipeline that does everything.

**Q: Does `startapp` register the app automatically?**
A: No — it only generates the folder and files. You still have to add the app's name to
`INSTALLED_APPS` in `settings.py` yourself before Django treats it as part of the project.
