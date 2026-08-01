# Repository Guidelines

domowa-apteka is a household pharmaceutical tracker (resolves products to active substances to catch brand-name duplicates). Stack: Django 5.2 on Python 3.11+, managed with `uv`, SQLite in dev. The project is a fresh scaffold — no Django app has been created yet beyond the `domowa_apteka` project package.

## Hard Rules

- `domowa_apteka/settings.py` still ships the `django-admin startproject` defaults: hardcoded `SECRET_KEY`, `DEBUG = True`, empty `ALLOWED_HOSTS`. Do not deploy or commit real secrets into this file — move `SECRET_KEY` and any credentials to environment variables (`.env`, already gitignored) before any non-local use.
- `context/**` is the source of truth for planning docs (PRD, tech-stack decision, shaping notes). Do not hand-edit `context/foundation/*.md`; those are written by the `/10x-*` skill chain.

## Project Structure

- `domowa_apteka/` — Django project package: `settings.py`, `urls.py`, `wsgi.py`, `asgi.py`. No app modules exist yet; the first feature app has not been started with `manage.py startapp`.
- `pyproject.toml` / `uv.lock` — dependency manifest, managed by `uv` (do not hand-edit `uv.lock`).
- `context/foundation/prd.md` — product requirements (@context/foundation/prd.md).
- `context/foundation/tech-stack.md` — stack decision and rationale (@context/foundation/tech-stack.md).

## Build, Test, and Development Commands

- `uv sync` — install/update dependencies from `uv.lock`.
- `uv run manage.py runserver` — start the dev server.
- `uv run manage.py migrate` — apply database migrations.
- `uv run manage.py makemigrations <app>` — generate migrations after model changes.
- `uv run manage.py test` — run Django's built-in test runner (no pytest config present).
- `uv run manage.py startapp <name>` — scaffold a new app under the repo root.

## Coding Style & Naming Conventions

- No linter, formatter, or type-checker config (ruff/black/mypy) is present yet — none is enforced in CI or pre-commit today. The tech-stack decision (@context/foundation/tech-stack.md) calls for a type-hints-everywhere + mypy convention once apps exist; wire it up before relying on it.
- No local per-app layout convention established yet since none of the project's own apps exist.

## Testing Guidelines

- No coverage threshold is configured.

## Commit & Pull Request Guidelines

- History is a single "Initial commit: Django scaffold" — no message convention is established yet. No CI workflow exists in `.github/workflows/`.
