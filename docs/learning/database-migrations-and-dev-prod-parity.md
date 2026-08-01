---
title: "Database migrations, and is SQLite-dev / Postgres-prod actually safe?"
slug: database-migrations-and-dev-prod-parity
date: 2026-07-31
tags: [django, web-fundamentals, deployment, database]
classification: mixed
prerequisites: [what-a-web-app-needs-to-run]
---

# Database migrations, and is SQLite-dev / Postgres-prod actually safe?

## Why this came up

`context/changes/deployment/deployment-plan.md` (Phase 0) switches this project's database
config from a hardcoded SQLite block to `dj_database_url.config(default="sqlite:///db.sqlite3")`
— local dev keeps using SQLite with zero setup, while Railway injects a `DATABASE_URL`
pointing at a real Postgres in production. That raised two questions worth actually
understanding rather than taking on faith: is running two *different* database engines in
dev vs. prod safe, and what is this "migration" thing the plan's `startCommand` runs
(`python manage.py migrate --noinput`) before the app is allowed to serve a single request.

## Builds on

See [what-a-web-app-needs-to-run.md](what-a-web-app-needs-to-run.md) — it introduced
`settings.py` as the place holding "which database to talk to" but didn't go into what
happens once that database's *shape* (tables, columns) needs to change over time. That's
what this doc covers.

## The concept, from the ground up

**1. What a migration actually is.**
Once an app has been running for a while, its database schema needs to change — you add a
model, add a field, change a column's type. A migration is a small, ordered file that
describes exactly one such change and how to apply it. Django generates these files for you:
`manage.py makemigrations` diffs your current models against the last-known schema state and
writes a new numbered file (`0001_initial.py`, `0002_add_field.py`, ...) describing the delta.
`manage.py migrate` then *applies* whichever of those files haven't run yet, against
whichever database `DATABASE_URL` currently points at, in order.

Django knows which ones "haven't run yet" because it keeps a bookkeeping table —
`django_migrations` — inside the target database itself, recording every migration that has
already been successfully applied *there*. Run `migrate` twice in a row and the second run
does nothing; it's not re-running history, it's advancing whatever database it's pointed at
to the latest known schema state.

**2. Why the same migration files can target two different database engines at all.**
You don't write migrations in raw SQL — you write Django models in Python, and Django's ORM
(object-relational mapper) is the translation layer that turns "add a field to this model"
into the actual `ALTER TABLE ...` statement, in whichever SQL dialect the configured backend
speaks. That's the whole reason the same codebase can point at SQLite locally and Postgres in
production without you hand-writing two versions of every schema change: you're coding
against Django's abstraction, not against SQLite or Postgres directly.

**3. Where the abstraction leaks — the actual parity risk.**
The abstraction is good, not perfect. Concretely, for this project:
- **Concurrency**: SQLite locks the whole file per write; Postgres handles real concurrent
  writes. Code that's never exercised two simultaneous writes locally won't have surfaced a
  locking/race bug that Postgres would happily allow to occur in prod.
- **Raw SQL**: if a migration ever uses Django's `RunSQL` escape hatch instead of the ORM,
  that SQL is whatever you typed — untranslated, and only ever tested against whichever
  backend you ran it against locally.
- **Postgres-only field types** (e.g. `JSONField`'s native querying, array fields, full-text
  search) don't have a real SQLite equivalent — Django emulates enough to make `migrate` and
  basic tests pass, but production behavior can differ subtly.
- **First real run risk, specific to this project's plan**: Phase 4's `startCommand` runs
  `migrate --noinput` as part of the production deploy itself. That means the *first time*
  this project's migrations ever execute against a real Postgres is during the actual
  production deploy — not something tested ahead of time. A cheap mitigation not currently in
  the plan: spin up a throwaway local Postgres once (`docker run postgres`, or `railway run`
  against the provisioned one) and run `migrate` against it before trusting the first `railway up`.

For an MVP built on plain Django ORM code (no `RunSQL`, no Postgres-only field types yet),
this split is a well-worn, generally-safe pattern — it's exactly why Django ships a database
abstraction layer in the first place. The gap above is the one concrete thing worth closing.

## In terms you already know

| This project's concept | What it's like in your world |
| --- | --- |
| A migration file (one schema change, numbered, ordered) | A single incremental step in a schema change log — the same idea as an SSDT/dacpac schema-diff-and-publish step, just one file per change instead of one big diff-and-apply. |
| `django_migrations` (the table tracking what's already applied, per database) | A **control/watermark table** from an ADF incremental-load pattern — except instead of tracking "last successfully loaded date," it tracks "which schema-version scripts have already run against this specific database," so re-running `migrate` is a no-op for anything already applied. |
| The ORM translating the same model code into SQLite or Postgres SQL | ADF's **Linked Service abstraction** — the same Copy Activity/pipeline logic runs against different underlying stores because it's written against ADF's abstraction layer, not the engine's raw API. Swap the Linked Service connection, not the pipeline. Here, swap `DATABASE_URL`, not the model code. |

## What's universal vs. what's specific to this project's choices

**True for any app with a database, not just Django:**
- Schema changes need to be applied consistently, in the right order, across every
  environment the app runs in — "migrations" as a general practice exist to solve exactly
  that, regardless of language or framework.
- Testing against a database engine that differs from production is a real, well-known risk
  category (**dev/prod parity**) — not a Django-specific concern.

**Specific because this project picked Django + the `dj_database_url` split:**
- Django autogenerates migration files from model diffs (`makemigrations`) and tracks a full
  historical migration graph per app; other ecosystems (e.g. raw Flyway/Liquibase setups)
  instead require you to hand-write every migration's SQL yourself.
- The SQLite-dev / Postgres-prod split itself is this project's choice, made in
  `deployment-plan.md` Phase 0 — trading a small parity risk for zero local Postgres setup. A
  different project might run Postgres locally via Docker from day one (higher setup cost,
  no parity gap), which becomes the better trade once the app starts leaning on
  Postgres-specific features.
- The "first Postgres run happens at deploy time" gap is specific to this plan's current
  `startCommand` design (Phase 3) — a different rollout could add a one-time migration
  smoke-test against Postgres as its own step before Phase 4's `railway up`.

## Go deeper

- [Django Migrations: A Primer — RealPython](https://realpython.com/django-migrations-a-primer/) —
  builds intuition for `makemigrations`/`migrate` with concrete before/after examples, no
  prior web-dev background assumed.
- [Django official docs: Migrations](https://docs.djangoproject.com/en/5.2/topics/migrations/) —
  authoritative reference, matching this project's Django 5.2.

## Quick recap

**Q: What is a Django migration, concretely?**
A: A generated Python file describing one schema change (e.g. "add this column"), produced
by diffing your models against the last known schema state, and applied in order by `migrate`.

**Q: How does Django avoid re-applying a migration that already ran?**
A: It keeps a `django_migrations` bookkeeping table *inside* the target database — the same
role a watermark/control table plays in an ADF incremental load, just tracking schema
versions instead of data batches.

**Q: Why can the same model code run against both SQLite and Postgres?**
A: Because you write against Django's ORM, an abstraction layer, not raw SQL — the ORM
compiles your model code into whichever dialect the currently-configured backend needs.

**Q: Is this project's SQLite-dev / Postgres-prod split actually safe?**
A: Yes, as long as the code stays plain ORM (no raw SQL migrations, no Postgres-only field
types) — but right now the plan's first real Postgres migration run happens *during* the
production deploy itself, which is the one gap worth closing with a local Postgres test run
first.

**Q: When would you stop using this split and run Postgres locally too?**
A: Once the app starts depending on Postgres-specific behavior (heavy `JSONField` querying,
full-text search, concurrency-sensitive code paths) — at that point the parity risk outweighs
the convenience of zero local setup.
