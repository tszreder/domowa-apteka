---
project: domowa-apteka
researched_at: 2026-07-31
recommended_platform: Railway
runner_up: Azure (Container Apps)
context_type: mvp
tech_stack:
  language: python
  framework: django
  runtime: uv
---

## Recommendation

**Deploy on Railway.**

Railway is the only researched platform that cleanly matches every hard constraint at once: native `uv.lock` auto-detection via Nixpacks, a genuinely co-located managed Postgres (same project, same billing), GA native cron for the daily registry-ingestion job, and a fully CLI-scriptable deploy/log loop — all at a predictable ~$5-15/mo floor. Given the project's 1-week, after-hours-only, solo-developer timeline (hard deadline 2026-09-14 per `prd.md`), Railway's single-project simplicity outweighs Azure's technically comparable scores: Azure ties Railway on the five agent-friendly criteria, and the developer's prior hands-on Azure experience was seriously weighed as a tie-break, but the cross-check concluded the extra resource surface (Container Apps environment, the app, Postgres Flexible Server, VNet integration, KEDA Jobs config) risks eating into a deadline that has no slack.

## Platform Comparison

| Platform | CLI-first | Managed/Serverless | Agent-readable docs | Stable deploy API | MCP/Integration | Total |
|---|---|---|---|---|---|---|
| Railway | Pass | Pass | Pass | Pass | Partial | 4.5/5 |
| Azure (Container Apps) | Pass | Pass | Pass | Pass | Pass | 5/5 |
| Render | Partial | Pass | Fail | Partial | Pass | 3/5 |
| Fly.io | Pass | Partial | Pass | Partial | Partial | 3/5 |
| Vercel | Pass | Partial | Fail | Partial | Pass | 3/5 |
| Cloudflare | Pass | Fail (Django needs Paid-plan Containers) | Pass | Pass | Pass | dropped — hard constraint |
| Netlify | Pass | Fail (no Python function runtime at all) | Pass | Pass | Pass | dropped — hard constraint |

**Cloudflare** and **Netlify** were dropped before scoring: Netlify's Functions runtime supports JS/TS/Go only — Python isn't a supported language, full stop. Cloudflare's Python support is Pyodide-based (Python Workers, open beta) and doesn't run standard WSGI/Django; the only way to run a real Django app is Cloudflare Containers, which requires the Workers Paid plan. Both fail the tech-stack hard constraint regardless of how they score on the other four criteria.

**Render** has a native, GA Python/Django runtime and the strongest MCP server of the group (official, GA, can create services/DBs/cron and tail logs), but its docs are web-only (no GitHub markdown source), its CLI has no rollback subcommand, and its free-tier Postgres expires 30 days after creation — a real trap for a project meant to persist household data past a one-month trial.

**Fly.io** matches the `deployment_target: fly` hint already in `tech-stack.md` and gives real VM flexibility (genuine Docker/Firecracker, not a serverless shim), but `uv` isn't auto-detected by `fly launch` (needs a hand-written Dockerfile), there's no native rollback command, and Managed Postgres is either expensive (~$38+/mo) or unsupported/self-managed (~$2/mo, "not able to provide support" per Fly's own docs).

**Vercel** is technically workable and effectively free on Hobby, but its serverless-function model fights Django's process assumptions (SQLite is unusable — ephemeral filesystem; the whole app compiles into one function bundle; the daily ingestion job would have to become an HTTP-triggered view bound by a 5-minute default duration cap), and there's no first-party co-located Postgres — only marketplace resellers (Neon, Supabase), directly against the stated co-location preference.

### Shortlisted Platforms

#### 1. Railway (Recommended)

Nixpacks auto-detects `uv.lock` and runs `uv sync --no-dev --frozen` out of the box — no custom Dockerfile needed. Native Cron Jobs (GA) fit the once-daily ingestion job directly. Postgres is first-party, one-click, and billed on the same project — genuine co-location. CLI (`railway up`, `railway logs`, `railway deployment list` + `railway redeploy`) covers the full operational loop without a dashboard. Public docs source is markdown on GitHub. Weakest point: the MCP server is explicitly "work in progress," and the only EU region is Amsterdam (no Poland-local presence).

#### 2. Azure Container Apps (Runner-up)

Scored identically well on the five criteria — GA Container Apps Jobs (KEDA-based cron), genuinely managed Postgres Flexible Server (GA in Poland Central since Sept 2023), open-source markdown docs, fully scriptable `az` CLI, and a GA-ish MCP Server spanning 40+ services. Cost is more competitive than it first appears: Container Apps Consumption's free grant likely covers compute at ~$0, leaving Postgres Flexible Server (~$12-15/mo) as the real floor — comparable to Railway. The developer's prior hands-on Azure experience was a genuine factor. What tips it to runner-up: `uv` support in Azure's Oryx build system is newer and less battle-tested than pip (a March 2026 build incident briefly broke 3.11+ builds), and the setup requires wiring together 3-4 distinct resources (Container Apps environment, the app, Postgres Flexible Server, VNet integration for private DB access, KEDA Jobs config) versus Railway's single project — a real risk against a 1-week hard deadline with no slack.

#### 3. Render

Strong native Django support and the best-in-class MCP server (official, GA, can provision services/DBs/cron jobs and tail logs directly), plus GA Cron Jobs that fit the ingestion job well. Passed over because its docs aren't agent-readable (web-only, no GitHub markdown source) and its free-tier Postgres expiring after 30 days is a poor fit for a household app meant to keep data long-term — the sustainable paid floor (~$14/mo: Starter web service + Postgres Basic) is comparable to Railway's but without Railway's cron/CLI/docs advantages.

## Anti-Bias Cross-Check: Railway (Recommended)

### Devil's Advocate — Weaknesses

1. No Poland-local region — nearest is Amsterdam (EU West Metal), adding latency to both users and the daily calls to the Polish government registry, with no easy in-place region migration later.
2. No free tier — Hobby's $5/mo is real spend from day one, and usage-based billing on top of the flat fee (RAM/vCPU-seconds, even for an always-on process at zero traffic) can creep past the included credit without much warning.
3. MCP server is explicitly "work in progress" — no first-class structured tool access yet, CLI-only for agent-driven ops.
4. Smaller, newer platform than Render/Fly — thinner community/support trail if something platform-specific breaks (build caching, cron edge cases).
5. No native CLI rollback command — "redeploy a prior deployment" works but needs a deployment-ID lookup first, one indirection short of a single rollback command.

### Pre-Mortem — How This Could Fail

Six months in, with ~50 daily users, three small issues compounded. The daily registry-ingestion cron silently started failing for two weeks after the government API changed its pagination — Railway's cron logs "completed" even on an early exit, and without an app-side freshness check nobody noticed until a user reported garbage duplicate flags. Separately, the flat $5/mo Hobby credit undercovered growing Postgres storage (registry data plus per-household history), so the bill quietly crept to $18/mo — a surprise since minimizing cost was the explicit priority and nobody was watching the usage dashboard. Finally, a Polish user complained about slow page loads, and the team realized the nearest region was Amsterdam, not Warsaw — with no easy in-place migration, moving meant re-provisioning the database and re-pointing DNS during a maintenance window, disproportionate for a household-scale app.

### Unknown Unknowns

- Billing is continuous GB-seconds/vCPU-seconds for anything not explicitly serverless-enabled — an always-on Django process accrues cost at zero traffic, not obvious from the "$5/mo" headline.
- Cron has no execution-time guarantee (±minutes) and silently skips a run if the previous one is still in progress — "the cron fired" isn't proof the data is fresh without an explicit last-successful-run check in the app.
- Leaving Railway later means manually re-exporting Postgres and reconfiguring `DATABASE_URL`-style env vars — no one-command migration path, so today's co-location convenience is tomorrow's small lock-in cost.
- Nixpacks rebuilds dependency resolution from the lockfile on every deploy unless caching is explicitly tuned — cold-cache builds can add unexpected minutes to the deploy loop during the 1-week crunch.

## Anti-Bias Cross-Check: Azure Container Apps (runner-up, considered and passed over)

### Devil's Advocate — Weaknesses

1. `uv` support in Azure's build system (Oryx) is new and less battle-tested than pip — a March 2026 Oryx incident briefly broke Python 3.11+ builds.
2. Container Apps + Postgres Flexible Server + Container Apps Jobs (KEDA cron) is 3-4 distinct resources to wire together (VNet integration, connection strings, job trigger config) versus Railway's single project.
3. Poland Central still lacks some Azure services (Databricks, Synapse, ML) — a constraint if the uncommitted "LLM for normalizing registry fields" idea in `tech-stack.md` ever becomes real.
4. Azure's resource-group/subscription-level billing and IAM is enterprise-shaped — real risk of a half-configured resource for a solo side project.
5. The Container Apps free-grant math is a "should cover it" estimate, not guaranteed — cost can drift above the ~$12-15/mo floor without an obvious single-dashboard warning.

### Pre-Mortem — How This Could Fail

Six months in, looking back, Azure quietly cost more time than it saved. The Container Apps + Postgres Flexible Server setup took most of day one of the one-week build — VNet integration, resource-group naming, a KEDA Jobs cron config needing three iterations to trigger reliably. Halfway through, an Oryx build failure from a `uv.lock` edge case cost an evening of debugging with thin community documentation. The Postgres bill crept past the estimated $12-15/mo once backup retention and a forgotten non-zero minimum replica were factored in. Prior Azure familiarity saved some research time on IAM and CLI syntax, but not enough to offset the platform's larger resource surface for a project this small.

### Unknown Unknowns

- Container Apps Jobs is a separate resource from the Container App itself — job logs and app logs live in different places.
- Postgres Flexible Server's secure-by-default private access means a local dev machine can't connect directly without a VPN/bastion exception.
- Free-grant accounting is tracked per-subscription, not per-app — unrelated experiments under the same subscription silently eat into this project's budgeted grant.
- The Azure MCP Server's 40+-service surface is large — pointing an agent at it unscoped risks it touching unrelated resources in the same subscription.

## Operational Story

- **Preview deploys**: Railway auto-deploys on push to the linked branch; confirm PR-based ephemeral environments at setup time (not verified in research) rather than assuming parity with Vercel/Netlify-style preview URLs.
- **Secrets**: environment variables live in the Railway project (`railway variables set KEY=value` or dashboard); `DATABASE_URL` for the co-located Postgres is auto-injected into the web service. Move `SECRET_KEY` and any credentials here per the existing `AGENTS.md` hard rule — never commit them to `settings.py`.
- **Rollback**: `railway deployment list` to find a prior deployment, then `railway redeploy <deployment-id>`. No single-command rollback verb — script this as a two-step sequence if automating it.
- **Approval**: deploys trigger automatically on push unless disabled — for this project, keep automatic deploy for `main` but treat destructive actions (dropping the Postgres instance, rotating `SECRET_KEY`, deleting the project) as human-only, consistent with the "human-on-irreversibles" posture in the project's `/10x-infra-research` lesson notes.
- **Logs**: `railway logs` (with `--build`, `-n`, `--dns` variants) for both the web service and the cron job — check the job's own log stream separately from the app's when verifying the daily ingestion ran.

## Risk Register

| Risk | Source | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| Daily ingestion cron fails silently (exits early, Railway still logs "completed") | Pre-mortem | M | H | Add an app-side freshness check (e.g. last-successful-run timestamp visible in admin) rather than trusting cron-run status alone |
| Monthly cost drifts above the $5 Hobby credit as Postgres storage/usage grows | Pre-mortem, Devil's advocate | M | L | Check the Railway usage dashboard monthly during the build; set a mental/calendar reminder since there's no built-in budget alert confirmed |
| No Poland-local region adds latency for users and registry calls | Devil's advocate | H (certain) | L | Accept for MVP at household scale; revisit only if latency becomes a user complaint |
| No native CLI rollback command | Devil's advocate | H (certain) | L | Script `deployment list` + `redeploy` as a two-step rollback procedure ahead of time, not improvised during an incident |
| Nixpacks cold-cache build adds unplanned minutes to a deploy during the 1-week crunch | Unknown unknowns | M | L | Deploy early and often during the build week to keep the build cache warm rather than batching deploys |
| Leaving Railway later requires manual Postgres export + env var reconfiguration | Unknown unknowns | L | M | Not a near-term concern; note as a known lock-in cost if a future migration is ever considered |
| MCP server is WIP — no structured agent tool access to Railway operations yet | Devil's advocate | H (certain) | L | Use the CLI directly for agent-driven ops in the meantime; revisit if Railway's MCP reaches GA |

## Getting Started

1. Install the Railway CLI and authenticate: `railway login`.
2. From the repo root, link or create the project: `railway init` (or `railway link` if a Railway project already exists for `domowa-apteka`).
3. Add a co-located Postgres instance: `railway add` (or via the dashboard: New → Database → PostgreSQL) — this auto-injects `DATABASE_URL` into the web service.
4. Confirm `uv.lock` and `pyproject.toml` are committed (they already are) — Nixpacks auto-detects `uv.lock` and runs `uv sync --no-dev --frozen` during build; no Dockerfile needed.
5. Set required environment variables via `railway variables set SECRET_KEY=... DEBUG=False ALLOWED_HOSTS=...` before the first deploy, per the existing `AGENTS.md` hard rule against shipping the `startproject` defaults.
6. Verify or set the start command so Railway runs migrations before serving: `python manage.py migrate && gunicorn domowa_apteka.wsgi` (adjust the module path if it differs from the scaffolded `domowa_apteka` project package).
7. Deploy: `railway up`, or push to the linked branch for auto-deploy.
8. Configure the daily ingestion job as a second Railway service (or a Cron Job on the same service) running `python manage.py <ingestion-command>` on a daily UTC schedule via Railway's native Cron field.
9. Tail logs to confirm both the web service and the cron job are healthy: `railway logs`.

## Out of Scope

The following were not evaluated in this research:
- Docker image configuration
- CI/CD pipeline setup
- Production-scale architecture (multi-region, HA, DR)
