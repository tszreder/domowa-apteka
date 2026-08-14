# Analogy Glossary

Accumulated mappings from this project's concepts to the learner's known Microsoft
data-stack world. Reuse these in every new doc rather than inventing a second, inconsistent
analogy for something already mapped here. If an analogy is ever revised, every doc that
used the old one needs a look.

| Concept here | Analogy in your world | First used in |
| --- | --- | --- |
| Django **project** (the top-level container: global settings, URL routing, one deployable unit) | An ADF **Data Factory instance** — the container that holds global config (linked services, integration runtime) and is what actually gets deployed/run. | django-project-vs-app.md |
| Django **app** (a self-contained feature module: its own models/views/logic, pluggable into a project) | An ADF **pipeline** inside that factory — a self-contained unit of work with its own internals, that gets registered into the factory and could in principle be copied into a different one. | django-project-vs-app.md |
| Entry point (`wsgi.py` / `asgi.py`) — the thing a server process actually invokes | ADF's **Integration Runtime** — the compute engine that gets started up to actually execute things, as opposed to something you author pipeline logic in. | what-a-web-app-needs-to-run.md |
| Configuration (`settings.py`) — shared config every part of the project can read | ADF's **Linked Services + Global Parameters** — shared, centrally-authored config every pipeline draws on. | what-a-web-app-needs-to-run.md |
| Routing (`urls.py`) — maps an incoming request path to the code that handles it | ADF's **Triggers** — the mapping of "when this happens, run that pipeline," here "when a request hits this path, run that view." | what-a-web-app-needs-to-run.md |
| A migration file — one ordered, versioned schema change | A single incremental step in an SSDT/dacpac schema-diff-and-publish sequence. | database-migrations-and-dev-prod-parity.md |
| `django_migrations` — the table tracking which migrations already ran, per database | A **control/watermark table** from an ADF incremental-load pattern — tracks "what's already been applied" instead of "what's already been loaded." | database-migrations-and-dev-prod-parity.md |
| The ORM translating the same model code into different SQL dialects (SQLite vs. Postgres) | ADF's **Linked Service abstraction** — the same Copy Activity/pipeline logic runs against different underlying stores by swapping the Linked Service connection, not the pipeline code. | database-migrations-and-dev-prod-parity.md |
| A running server process (dev `runserver`, prod `gunicorn`) | A **Databricks cluster / SQL Warehouse in "Running" state** — definitions exist regardless, but nothing executes (or connects) until compute is actually up. | what-a-web-app-needs-to-run.md |
| A virtual environment (`.venv`) | A **Databricks cluster's isolated library configuration** — each cluster has its own installed libraries, isolated from every other cluster, even on the same underlying runtime/base Python. | python-dependency-management-pip-uv-venv.md |
| `uv.lock` (exact, reproducible dependency graph) | A **cluster policy / pinned library list** in Databricks — the exact version set is captured once and reapplied identically every time, instead of re-resolving "latest" on each run. | python-dependency-management-pip-uv-venv.md |
| `pyproject.toml` (declared intent, hand-edited) | The **spec you write** when defining a Databricks cluster policy or ADF linked service — "give me *a* runtime/connection like this," loosely, not the fully resolved result. | python-dependency-management-pip-uv-venv.md |
| Marker-based resolution (one lockfile, different resolved versions per Python) | A **parameterized ARM/ADF template** — one definition, multiple resolved outcomes depending on which environment/condition it's evaluated against. | python-dependency-management-pip-uv-venv.md |
| The scaffold's dev defaults (insecure key, `DEBUG=True`, SQLite) | An ADF pipeline authored in **Debug mode against a dev linked service** — useful, and precisely not the thing you publish. | from-dev-scaffold-to-production-ready.md |
| A platform health check probing `/health/` | An **Azure App Service / Load Balancer health probe** — pings a path on an interval, pulls the instance from rotation on anything that isn't a 200. | from-dev-scaffold-to-production-ready.md |
| `.python-version` pinning the build interpreter | Pinning the **Databricks Runtime version** on a job cluster instead of letting it float to "latest". | from-dev-scaffold-to-production-ready.md |
| `manage.py check --deploy` | The **Best Practices Analyzer / BPA rules** run over a model before publishing — a static audit against known production pitfalls, not a test run. | from-dev-scaffold-to-production-ready.md |
| Environment variables as per-environment config | **ARM template parameter files** (`parameters.dev.json` / `parameters.prod.json`) over one published definition — same artifact, values bound at deploy time. | config-in-dev-vs-prod.md |
| Secrets in env vars (`SECRET_KEY`, `DATABASE_URL`) | A **Databricks secret scope / Key Vault–backed reference** — code names the secret, never holds its value. | config-in-dev-vs-prod.md |
| Railway reference variable `${{Postgres.DATABASE_URL}}` | A **Key Vault reference in an App Service setting** — config holds a pointer, the platform resolves it at start-up. | config-in-dev-vs-prod.md |
| `DEBUG = True` | An **ADF Debug run / interactive Databricks notebook** — verbose and revealing by design, therefore not for consumers. | config-in-dev-vs-prod.md |
| `SECRET_KEY` (signing key for cookies, CSRF tokens) | The **signing key behind a Storage SAS or Power BI embed token** — possessing it is the authority to mint valid credentials, not merely to log in. | config-in-dev-vs-prod.md |
| `ALLOWED_HOSTS` | An **Azure SQL / Storage firewall allow-list**, but keyed on the name the caller used rather than its IP. | config-in-dev-vs-prod.md |
| Environment values always being strings | **ADF pipeline parameters being stringly-typed** until explicitly cast — same footgun as `bool("False")`. | config-in-dev-vs-prod.md |
| Static vs. dynamic responses | A **file served as-is from an ADLS container** vs. a **query result computed per request**. | static-files-collectstatic-and-whitenoise.md |
| `collectstatic` / `STATIC_ROOT` | A **build step raking many source folders into one landing container**, and that container itself — generated output, not hand-authored. | static-files-collectstatic-and-whitenoise.md |
| WhiteNoise (serving static files in-process) | Reading a small lookup file **directly in the notebook** instead of standing up a separate serving layer; a **CDN / Front Door** is what you graduate to. | static-files-collectstatic-and-whitenoise.md |
| CSRF (browser auto-attaching credentials cross-site) | A **Logic App with a managed identity** anyone who can trigger it can borrow — ability to invoke becomes ability to act as. | csrf-and-https-behind-a-proxy.md |
| TLS termination at a platform edge | **Azure Front Door / Application Gateway terminating SSL** in front of an App Service — the backend gets plain HTTP and must be told the original scheme. | csrf-and-https-behind-a-proxy.md |
| `CSRF_TRUSTED_ORIGINS` | A **CORS / reply-URL allow-list on an app registration** — explicit list of origins permitted to interact. | csrf-and-https-behind-a-proxy.md |
| CI — automated checks on every proposed change, before merge | An **Azure DevOps build validation policy** on a branch — the build runs on the PR, not after the fact. | ci-cd-and-deploy-triggers.md |
| CD — main-branch state automatically becoming production | The **ADF release pipeline** that publishes onward as soon as `adf_publish` updates. | ci-cd-and-deploy-triggers.md |
| A GitHub Actions **runner** | An **ephemeral Databricks job cluster** — spun up per run, torn down after; nothing persists, so every tool the job needs must be installed by the job. | ci-cd-and-deploy-triggers.md |
| **Workflow / job / step** (the CI YAML) | An ADF **pipeline / activity** definition — declarative, version-controlled, describes what runs in what order. | ci-cd-and-deploy-triggers.md |
| A **repository secret** (`RAILWAY_TOKEN`) | A **Key Vault–backed secret scope**, but owned by GitHub rather than the runtime platform — write-only, injected at run time, masked in logs. Same shape as the env-var secret mapping above, different vault. | ci-cd-and-deploy-triggers.md |
| **Required status check** / branch protection | A **branch policy in Azure Repos** requiring a successful build before a PR can complete. | ci-cd-and-deploy-triggers.md |
| `concurrency` group, `cancel-in-progress: false` | An ADF pipeline with **concurrency set to 1** — runs queue instead of overlapping. | ci-cd-and-deploy-triggers.md |
| Platform-native repo integration (Railway connecting to GitHub itself) | **App Service Deployment Center** pointed at a repo — the platform owns the trigger, wired by clicking rather than by committing. | ci-cd-and-deploy-triggers.md |
| An **assertion** in a test | A **data-quality expectation** on a load — declares what must be true and fails loudly when it isn't, rather than reporting what happened. | automated-testing-types-and-django-mechanics.md |
| **Unit test** | Validating a single **DAX measure or transformation function** against a tiny hand-built input table — no pipeline, no source systems. | automated-testing-types-and-django-mechanics.md |
| **Integration test** | An **ADF pipeline debug run** end-to-end against dev linked services — several activities wired together, real connections. | automated-testing-types-and-django-mechanics.md |
| **Smoke test** | A **"does it run at all" debug run over a tiny sample**, before committing to the full load. | automated-testing-types-and-django-mechanics.md |
| **End-to-end test** | **UAT against the published report** in the real workspace, driven the way a consumer drives it. | automated-testing-types-and-django-mechanics.md |
| The **throwaway test database** (created, migrated, destroyed per run) | A **scratch schema spun up for a validation run and dropped afterwards** — never the dev or prod store. | automated-testing-types-and-django-mechanics.md |
| **Per-test transaction rollback** | A sandbox that **resets between runs**, so run order never affects the result. | automated-testing-types-and-django-mechanics.md |
| Test **discovery by naming convention** (`test*.py`) | `adf_publish` **picking up everything in the declared folders** — the layout is the registration; you never enumerate items by hand. | automated-testing-types-and-django-mechanics.md |
| A **regression test** (written after a bug, to pin it shut) | A **data-quality check added after a bad load slipped through** — same mechanism as the checks you wrote up front, added for a different reason, and the one you trust most because you know exactly what it caught. | automated-testing-types-and-django-mechanics.md |
| A **flaky test** | An **intermittently failing pipeline** whose failures are timing rather than logic — it trains everyone to re-run instead of investigate. | automated-testing-types-and-django-mechanics.md |
| `manage.py test` (executes your code) | **Actually running the refresh**, as opposed to the static BPA-style audit that `check --deploy` performs (mapped above). | automated-testing-types-and-django-mechanics.md |
| A Django model class doubling as the schema definition | Schema-as-code, closer to a **dbt model / Delta Live Tables table definition** than SSDT — the object you write *is* the deployable schema artifact, not a separate script kept in sync by hand. | orm-models-and-sql-ddl.md |
| `OneToOneField` (FK + `UNIQUE`, enforced at insert time) | A **1:1 relationship in an Azure SQL schema** via a unique constraint on the foreign-key column — same pattern, expressed as a Python field instead of `CREATE UNIQUE INDEX`. | orm-models-and-sql-ddl.md |
| A session (cookie holds a key, real data stored server-side) | A **Power BI Service report session** — the browser holds a small token, the real state lives server-side, looked up by that token. | sessions-and-login-persistence.md |
| `request.session` surviving across requests | A **Databricks notebook's cluster-scoped state while the cluster stays "Running"** — a later command can read what an earlier one wrote, as long as the same session is still up. | sessions-and-login-persistence.md |
| `request.session.pop(key, None)` — read once, then gone | A **queue message explicitly acknowledged and removed after processing**, not a value left sitting for the next unrelated run to pick up. | sessions-and-login-persistence.md |
| `{% extends %}` / `{% block %}` template inheritance | A **Power BI report theme + shared master layout** — the shell is defined once, each page supplies only what's genuinely different. | django-templates-and-css.md |
| `{% static %}` resolving a path via a finder, not a hardcoded URL | A **Power BI report referencing a theme file by logical name**, resolved to wherever it actually lives at render time. | django-templates-and-css.md |
| `secrets.token_urlsafe(32)` — a cryptographically secure random token | Generating a **Power BI embed token / SAS token** — possessing the value *is* the authorization, with no separate identity check behind it. | unguessable-invite-tokens.md |
| Revocation by regenerating a token (no denylist) | **Rotating a Key Vault secret / SAS token** — the old value stops existing anywhere that matters, instead of being tracked and blocked. | unguessable-invite-tokens.md |
| The git commit history / `.git` object store | A **Delta Lake transaction log** — immutable, append-only ordered versions; nothing is ever edited in place. | branches-worktrees-and-parallel-work.md |
| A **branch** (movable pointer to one commit) | A **Delta table alias/tag pointing at a version** — a label, cheap to create, not a copy of the data. | branches-worktrees-and-parallel-work.md |
| The **working tree** (the files on disk) and `git switch` | **Materializing one `VERSION AS OF` into a dataframe** — one version realized at a time from one location; switching re-reads at a different version into that same location rather than opening a second view. | branches-worktrees-and-parallel-work.md |
| `git worktree` (a second folder sharing one `.git`) | **Two Databricks clusters attached to the same metastore** — separate compute and local scratch, one shared underlying storage. | branches-worktrees-and-parallel-work.md |
| **Squash merge** (branch commits collapsed into one on `main`) | **Collapsing a run's incremental steps into a single published change** — same result, lineage not preserved, so lineage-based checks (`git branch --merged`) answer wrongly. | branches-worktrees-and-parallel-work.md |
| A **merge conflict** | **Two people editing the same section of the same PBIX** — different sections merge cleanly; the same lines need a human. | branches-worktrees-and-parallel-work.md |

> **Note on "trigger".** `urls.py` is mapped to ADF triggers above (request path → view).
> A CI deploy trigger is a different layer entirely (repository event → pipeline run).
> Same word, two layers apart — `ci-cd-and-deploy-triggers.md` says so explicitly.
