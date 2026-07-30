---
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
---

## Why this stack

A solo builder shipping a small household-medicine tracker as a 1-week after-hours MVP picked Python, making Django the recommended default for `(web, python)`. Django's batteries-included model is a direct fit: built-in auth carries the login-based household accounts and invites; the ORM plus migrations model the pharmaceutical→active-substance sets that drive the full/partial duplicate matching; the admin gives a zero-cost surface for inspecting ingested registry data; and a scheduled management command run by cron satisfies the daily ingestion the PRD's data-freshness requirement forces. Bootstrapper confidence is verified, so scaffolding stays smooth under a tight deadline. Deployment defaults to Fly (the card's first target, with scheduled machines for the ingestion cron); CI runs on GitHub Actions with auto-deploy-on-merge — the standard solo shape. Auth and background-jobs flags are set; payments and realtime are out of scope per PRD non-goals. One caveat: Django is untyped by default, so plan a type-hints-everywhere plus mypy convention in CLAUDE.md. A candidate non-user-facing LLM for normalizing messy registry fields is possible but uncommitted, so no AI flag is set.
