---
bootstrapped_at: 2026-07-30T16:51:25Z
starter_id: django
starter_name: Django
project_name: domowa-apteka
language_family: python
package_manager: uv
cwd_strategy: native-cwd
bootstrapper_confidence: verified
phase_3_status: ok
audit_command: pip-audit
---

## Hand-off

Verbatim copy of `context/foundation/tech-stack.md`:

```yaml
starter_id: django
package_manager: uv
project_name: domowa-apteka
hints:
  language_family: python
  team_size: solo
  deployment_target: fly
  ci_provider: github-actions
  ci_default_flow: auto-deploy-on-merge
  bootstrapper_confidence: verified
  path_taken: standard
  quality_override: false
  self_check_answers: null
  has_auth: true
  has_payments: false
  has_realtime: false
  has_ai: false
  has_background_jobs: true
```

**Why this stack** (from hand-off body):

> A solo builder shipping a small household-medicine tracker as a 1-week after-hours MVP picked Python, making Django the recommended default for `(web, python)`. Django's batteries-included model is a direct fit: built-in auth carries the login-based household accounts and invites; the ORM plus migrations model the pharmaceutical→active-substance sets that drive the full/partial duplicate matching; the admin gives a zero-cost surface for inspecting ingested registry data; and a scheduled management command run by cron satisfies the daily ingestion the PRD's data-freshness requirement forces. Bootstrapper confidence is verified, so scaffolding stays smooth under a tight deadline. Deployment defaults to Fly (the card's first target, with scheduled machines for the ingestion cron); CI runs on GitHub Actions with auto-deploy-on-merge — the standard solo shape. Auth and background-jobs flags are set; payments and realtime are out of scope per PRD non-goals. One caveat: Django is untyped by default, so plan a type-hints-everywhere plus mypy convention in CLAUDE.md. A candidate non-user-facing LLM for normalizing messy registry fields is possible but uncommitted, so no AI flag is set.

## Pre-scaffold verification

| Signal      | Value                                    | Severity | Notes                                                        |
| ----------- | ---------------------------------------- | -------- | ------------------------------------------------------------ |
| npm package | not run                                  | n/a      | non-JS starter (language_family: python); no npm CLI to check |
| GitHub repo | not run                                  | n/a      | card.docs_url is docs.djangoproject.com, not a GitHub repo — no `pushed_at` signal available |

No recency signal available for this starter. Proceeded with no warning (WARN-AND-CONTINUE slot; never gating).

## Scaffold log

**Resolved invocation** (see deviation note below): `uv init --bare --vcs none && uv add django && uv run django-admin startproject domowa_apteka .`
**Strategy**: native-cwd
**Exit code**: 0 (all three stages exited 0: init 0, add 0, startproject 0)
**Pre-flight files-to-touch**: `pyproject.toml`, `uv.lock`, `.venv/`, `manage.py`, `domowa_apteka/` (settings.py, urls.py, wsgi.py, asgi.py, __init__.py)
**Files written by CLI**: 9 (pyproject.toml, uv.lock, manage.py, domowa_apteka/__init__.py, domowa_apteka/settings.py, domowa_apteka/urls.py, domowa_apteka/wsgi.py, domowa_apteka/asgi.py, plus the `.venv/` tree)
**Pre-existing files preserved**: `context/` (all 5 files: prd.md, project_ideas.md, README.md, shape-notes.md, tech-stack.md), `CLAUDE.md`, `.claude/` — none overwritten, no `.scaffold` siblings created
**.gitignore handling**: absent in scaffold (neither `uv init --bare` nor `django-admin startproject` created one) — see Next steps

### Deviations from the literal registry card (recorded per audit-trail honesty)

The documented card invocation (`pre: "pip install django"` + `cmd_template: "django-admin startproject {name} ."` with the native-cwd `{name}→.` substitution rule) was NOT run verbatim. Three deliberate patches were applied and confirmed with the user before writing:

1. **`pre` step is not executed by the v1 workflow** (scaffold-merge.md installs nothing beyond `cmd_template`), so `django-admin` would not exist → guaranteed HARD-STOP. Django was installed as the actual dependency step.
2. **The hand-off chose `uv`, but `uv` was not installed** on this machine (Python 3.11.9 + pip only). `uv 0.12.0` was installed via `pip install --user uv`, then the uv-native workflow (`uv init --bare` → `uv add django` → `uv run django-admin …`) was used in place of the card's `pip install django`. This honors the deliberate package-manager pick and yields `pyproject.toml` + `uv.lock` for reproducible Fly deploys.
3. **`{name}` substitution**: the literal native-cwd rule (`{name}→.`) yields `django-admin startproject . .`, which Django rejects. `{name}` was set to the project name sanitized to a valid Python identifier: `domowa-apteka` → `domowa_apteka`, keeping the trailing `.` for cwd-native scaffolding. This also deviates from scaffold-merge.md's "project_name is not a substitution input" rule.

These are patches around two bootstrapper v1 spec gaps (unhandled `pre` field; native-cwd substitution assuming a single name-or-directory positional) plus one environment gap (uv absent). The scaffold itself completed cleanly.

## Post-scaffold audit

**Tool**: pip-audit (run ephemerally as `uv run --with pip-audit pip-audit --format json` against the project venv, since pip-audit was not permanently installed)
**Summary**: 0 CRITICAL, 0 HIGH, 0 MODERATE, 0 LOW
**Direct vs transitive**: not distinguished by this tool

Clean tree. Project dependencies audited (django 5.2.16, asgiref 3.12.1, sqlparse 0.5.5, tzdata 2026.3) — all report zero vulnerabilities. The ephemeral pip-audit toolchain packages present in the audited environment (cachecontrol, requests, rich, etc.) also reported clean.

#### CRITICAL findings

None.

#### HIGH findings

None.

#### MODERATE findings

None.

#### LOW / INFO findings

None.

## Hints recorded but not acted on

| Hint                    | Value                    |
| ----------------------- | ------------------------ |
| bootstrapper_confidence | verified                 |
| quality_override        | false                    |
| path_taken              | standard                 |
| self_check_answers      | null                     |
| team_size               | solo                     |
| deployment_target       | fly                      |
| ci_provider             | github-actions           |
| ci_default_flow         | auto-deploy-on-merge     |
| has_auth                | true                     |
| has_payments            | false                    |
| has_realtime            | false                    |
| has_ai                  | false                    |
| has_background_jobs     | true                     |

v1 surfaces these but takes no automated action. CI/CD scaffolding (github-actions, auto-deploy-on-merge), deployment setup (fly), and feature wiring (auth, background-jobs) are deferred to a future skill.

## Next steps

Next: a future skill will set up agent context (CLAUDE.md, AGENTS.md). For now, your project is scaffolded and verified — happy hacking.

Useful manual steps in the meantime:
- `git init` (if you have not already) to start your own repo history.
- Add a `.gitignore` — neither the uv nor Django step created one. At minimum ignore `.venv/`, `__pycache__/`, `*.pyc`, `db.sqlite3`, and `.env`.
- The hand-off's `## Why this stack` flags that Django is untyped by default — plan a type-hints-everywhere + mypy convention in CLAUDE.md (that is the future M1L4 agent-context skill's territory).
- No `.scaffold` siblings were created (native-cwd wrote only new paths), so there is nothing to reconcile.
- Audit findings: none. Clean tree at bootstrap time.
