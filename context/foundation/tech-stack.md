---
starter_id: django
package_manager: uv
project_name: domowa-apteka
hints:
  language_family: python
  team_size: solo
  deployment_target: railway
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
---

## Why this stack

A solo builder shipping a small household-medicine tracker as a 1-week after-hours MVP picked Python, making Django the recommended default for `(web, python)`. Django's batteries-included model is a direct fit: built-in auth carries the login-based household accounts and invites; the ORM plus migrations model the pharmaceutical→active-substance sets that drive the full/partial duplicate matching; the admin gives a zero-cost surface for inspecting ingested registry data; and a scheduled management command satisfies the daily ingestion the PRD's data-freshness requirement forces. Scaffolding confidence is verified. **Deployment is Railway, not the card's first default (Fly)** — the project is already live at `web-production-f61ed.up.railway.app` with co-located Postgres in EU West and config-as-code in `railway.json`; see `context/deployment/deploy-plan.md`. **The two CI fields are now accurate**: the repo is private at `tszreder/domowa-apteka`, and `.github/workflows/deploy.yml` runs `railway up --service web --ci` on every merge to `main`, gated by a `check` job (`uv sync --locked`, `manage.py check`, `manage.py test`). Railway's own GitHub integration was rejected in favour of Actions so the deploy trigger stays in git rather than dashboard state; `railway up` remains the manual escape hatch. Auth and background-jobs flags are set; payments and realtime are out of scope per PRD non-goals. One caveat: Django is untyped by default, so plan a type-hints-everywhere plus mypy convention in CLAUDE.md. A candidate non-user-facing LLM for normalizing messy registry fields is possible but uncommitted, so no AI flag is set.
