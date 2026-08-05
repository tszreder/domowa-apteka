---
title: "What does a Django model class actually become in the database?"
slug: orm-models-and-sql-ddl
date: 2026-08-05
tags: [django, orm, database, web-fundamentals]
classification: mixed
prerequisites: [database-migrations-and-dev-prod-parity]
---

# What does a Django model class actually become in the database?

## Why this came up

Phase 2 of `context/changes/household-accounts-and-invites/plan.md` writes two Python classes
in `households/models.py` — `Household` and `Membership` — and `manage.py makemigrations`
turns them into `households/migrations/0001_initial.py`, which `manage.py migrate` then
applies as real tables. [database-migrations-and-dev-prod-parity.md](database-migrations-and-dev-prod-parity.md)
already covered *that* a migration is a generated, ordered schema-change file. This doc goes
one level deeper: field by field, what does a Python class attribute actually turn into as a
column, and why did `Membership.user` deliberately use `OneToOneField` instead of the more
common `ForeignKey`.

## Builds on

See [database-migrations-and-dev-prod-parity.md](database-migrations-and-dev-prod-parity.md) —
it explains what a migration file is, how `django_migrations` tracks what already ran, and how
the ORM lets the same model code target both SQLite and Postgres. This doc assumes that and
zooms into one specific translation: model class → table.

## The concept, from the ground up

### The model class *is* the schema, not a description of it

In an ADF/SSDT workflow, the schema (the dacpac, the CREATE TABLE script) and the code that
reads/writes the data are two separate artifacts you keep in sync by hand or via a diff tool.
Django collapses that into one artifact: the Python class. `households/models.py` defines:

```python
class Household(models.Model):
    name = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    invite_token = models.CharField(max_length=64, unique=True, db_index=True, blank=True)
```

`manage.py makemigrations` reads this class via Python's own introspection (no separate schema
file exists anywhere) and writes the DDL-equivalent operation into
`households/migrations/0001_initial.py`:

```python
migrations.CreateModel(
    name='Household',
    fields=[
        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
        ('name', models.CharField(max_length=255)),
        ('created_at', models.DateTimeField(auto_now_add=True)),
        ('invite_token', models.CharField(blank=True, db_index=True, max_length=64, unique=True)),
    ],
),
```

When `manage.py migrate` runs, Django's schema editor turns *that* into actual DDL for whichever
engine is configured — on SQLite roughly `CREATE TABLE households_household (id INTEGER PRIMARY
KEY AUTOINCREMENT, name VARCHAR(255) NOT NULL, created_at DATETIME NOT NULL, invite_token
VARCHAR(64) NOT NULL); CREATE UNIQUE INDEX ... ON households_household(invite_token);` — on
Postgres the equivalent `BIGSERIAL` / `VARCHAR(255)` / `TIMESTAMP WITH TIME ZONE` DDL. Same
Python attribute, different generated SQL, which is exactly the abstraction the prerequisite
doc described — this doc is just naming what each attribute becomes:

| Python (model field) | Becomes (roughly) | Notes |
| --- | --- | --- |
| `models.CharField(max_length=255)` | `VARCHAR(255) NOT NULL` | Django fields default to `NOT NULL` unless you pass `null=True` — a different default from many hand-written schemas. |
| `models.DateTimeField(auto_now_add=True)` | `TIMESTAMP NOT NULL` | Set once, at creation, by Django itself — never sent by application code. |
| `unique=True, db_index=True` | `UNIQUE` constraint + an index | Two separate things bundled by one field: the constraint enforces no duplicates, the index makes lookups by that column fast. |
| (implicit) `id` | `BIGINT PRIMARY KEY` (auto-increment) | Every model gets one for free unless you define your own primary key — this project doesn't, so it's on every table. |

### `ForeignKey` vs. `OneToOneField` — the same column, a different constraint

`Membership` links a user to a household:

```python
class Membership(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='membership',
    )
    household = models.ForeignKey(
        Household, on_delete=models.CASCADE, related_name='memberships',
    )
```

Both `ForeignKey` and `OneToOneField` generate the *same underlying thing* — a column holding
another table's primary key, with a `REFERENCES` constraint the database enforces on every
write. `on_delete=CASCADE` is a separate piece, and it's worth being precise about where it
runs: Django does **not** ask the database for a native `ON DELETE CASCADE` clause. Instead,
when you call `.delete()` on a `Household`, Django's ORM walks every relation pointing at it (a
`Collector`, in `django.db.models.deletion`) and issues explicit `DELETE` statements for the
related `Membership` rows itself, in Python, before removing the `Household` row — all inside
one transaction. The `REFERENCES` constraint at the database layer is real DDL; the cascading
*behavior* is the ORM's, which is also why deleting a `Household` correctly fires Django's
`pre_delete`/`post_delete` signals for every cascaded `Membership` — a database-native cascade
wouldn't know those signals exist. The migration confirms the constraint side — look at the
two fields side by side:

```python
('household', models.ForeignKey(on_delete=..., related_name='memberships', to='households.household')),
('user', models.OneToOneField(on_delete=..., related_name='membership', to=settings.AUTH_USER_MODEL)),
```

The difference is one extra constraint `OneToOneField` adds on top: it also makes that foreign-
key column `UNIQUE`. A `ForeignKey` lets a household have many memberships (that's the point —
many users per household). A `OneToOneField` on `user` means the database *physically cannot
store* a second row with the same `user_id` — inserting one raises `IntegrityError` at the
database layer, before any Django validation code runs.

That's the load-bearing design decision in `context/changes/household-accounts-and-invites/plan.md`'s
"Implementation Approach": *"The one-household-per-user rule is enforced by the database, not
by application code."* A view-level check ("does this user already have a household? if so,
reject") is something every future contributor has to remember to write and could forget in a
new code path. A `UNIQUE` constraint can't be forgotten — the database refuses the second row
unconditionally, from any code path, including a stray shell script or a future admin action
that never goes through a Django view at all.

## In terms you already know

| This project's concept | What it's like in your world |
| --- | --- |
| A Django model class doubling as the schema definition | Closer to **schema-as-code in a dbt model / Delta Live Tables table definition** than to SSDT — the object you write in the language you already work in *is* the deployable schema artifact, not a separate script kept in sync with it by hand. |
| `CharField`, `DateTimeField`, etc. mapping to column types per-engine | A Power BI/Fabric **data type** (`Whole Number`, `Date/Time`) that renders to a different native column type depending on the underlying store (Import model vs. Direct Lake vs. Postgres source) — one declared type, engine-specific storage underneath. |
| `unique=True` compiling to a `UNIQUE` constraint | A **primary/alternate key constraint enforced by the engine** (Azure SQL `UNIQUE INDEX`), not a Power Query dedup step that only cleans data you already loaded — the database itself refuses the second row. |
| `OneToOneField` (FK + UNIQUE, enforced at insert time) | A **1:1 relationship in an Azure SQL schema**, enforced with a unique constraint on the foreign-key column — the same pattern you'd use to guarantee "at most one profile row per employee," just expressed as a Python field instead of a `CREATE UNIQUE INDEX` statement. |

## What's universal vs. what's specific to this project's choices

**True for any relational database, not just Django's:**
- A foreign key is a column holding another table's primary key, with a constraint the
  database enforces on every write — regardless of ORM or hand-written SQL.
- A one-to-one relationship is a foreign key plus a uniqueness constraint on that column —
  there's no separate "1:1" construct at the SQL level, it's this composition.
- Enforcing an invariant at the database layer (a constraint) is strictly stronger than
  enforcing it in application code, because it holds regardless of which code path writes the
  row.

**Specific because this project picked Django's ORM:**
- The model-class-is-the-schema pattern, and generating migration files by diffing model state,
  is Django's own convention — a framework using raw SQL migrations (Flyway, Liquibase) has you
  write the DDL directly, with no Python class standing in for it.
- Django's default of `NOT NULL` unless `null=True` is stated, and its automatic unmanaged `id`
  primary key, are Django defaults — other ORMs (and hand-written DDL) don't always default the
  same way.
- `related_name` (`'membership'`, `'memberships'`) is a Django-only concept: it names the
  reverse lookup (`user.membership`, `household.memberships`) and has no SQL equivalent — it
  exists purely so Python code can walk the relationship in both directions.

## Go deeper

- [Django Models — RealPython](https://realpython.com/django-models/) — walks through field
  types and relationships with runnable examples, aimed at readers without prior ORM exposure.
- [Django official docs: Models](https://docs.djangoproject.com/en/5.2/topics/db/models/) and
  [Model field reference](https://docs.djangoproject.com/en/5.2/ref/models/fields/) — the
  authoritative list of field types and what each compiles to.

## Quick recap

**Q: Where does this project's actual database schema "live" — is there a separate schema file?**
A: No — `households/models.py` is the schema. `makemigrations` reads the Python classes directly
and generates the migration file from them; there is no separate DDL script to keep in sync.

**Q: What's the practical difference between `ForeignKey` and `OneToOneField`?**
A: Identical underlying column and constraint, except `OneToOneField` also adds `UNIQUE` — so
the database itself rejects a second row referencing the same target, instead of merely
allowing many.

**Q: Why is `Membership.user` a `OneToOneField` and not a `ForeignKey`?**
A: To enforce "one household per user" as a database constraint rather than a rule application
code has to remember to check — any attempt to insert a second membership for the same user
raises `IntegrityError` unconditionally, from any code path.

**Q: When would you reach for `ForeignKey` instead of `OneToOneField`?**
A: Whenever more than one row is a legitimate target — `Membership.household` is a plain
`ForeignKey` because a household is meant to have many members.

**Q: Does `on_delete=CASCADE` run in Python, or in the database?**
A: In Python. Django's ORM collects every related row (via a `Collector`) and issues explicit
`DELETE` statements for them itself, inside one transaction — it deliberately doesn't rely on a
native `ON DELETE CASCADE` SQL clause, so that Django's own per-object signals still fire for
each cascaded row.
