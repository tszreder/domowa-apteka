---
title: "What makes a deploy happen automatically? CI, CD, and deploy triggers"
slug: ci-cd-and-deploy-triggers
date: 2026-08-04
tags: [deployment, ci-cd, github, automation, security]
classification: mixed
prerequisites: [from-dev-scaffold-to-production-ready, config-in-dev-vs-prod, database-migrations-and-dev-prod-parity]
---

# What makes a deploy happen automatically? CI, CD, and deploy triggers

## Why this came up

Up to this point every deploy of this project happened because a human typed
`railway up --service web --ci` on a laptop. That works, but it means the deployed
version is "whatever was in one particular working directory at one particular
moment" — not "whatever is in the repository." We set up a private GitHub repo and
wired it so that **merging a pull request into `main` deploys to production**, which
required choosing between two quite different mechanisms and understanding what each
one actually trusts.

## Builds on

- [from-dev-scaffold-to-production-ready.md](from-dev-scaffold-to-production-ready.md)
  for what production readiness means here and what `manage.py check --deploy` is.
- [config-in-dev-vs-prod.md](config-in-dev-vs-prod.md) for environment variables and
  the "code names the secret, never holds its value" principle — a CI secret is the
  same idea, stored somewhere new.
- [database-migrations-and-dev-prod-parity.md](database-migrations-and-dev-prod-parity.md)
  for why `migrate` running at container start is the thing that makes concurrent
  deploys dangerous.

## The concept, from the ground up

### The vocabulary, quickly

**CI — Continuous Integration.** Every proposed change gets built and checked
*automatically*, before anyone merges it. The point is not "we run tests"; it's that
nobody can forget to.

**CD — Continuous Delivery/Deployment.** Once a change lands on the main branch, it
goes to production *automatically*, with no human running a command.

They are separate, and this project now does both — but note that they answer
different questions. CI answers "is this change safe to merge?" CD answers "what
should be running right now?"

### The three moving parts

**1. A remote repository.** Your `git` history lived only on your laptop. A *remote*
is a shared copy — here, a private GitHub repo at `tszreder/domowa-apteka`. Once it
exists, "what should be deployed" has an unambiguous answer: whatever is on the
`main` branch of the remote.

**2. A pull request (PR).** You work on a branch (`deploy/railway-phase-0`), then open
a PR proposing to merge it into `main`. The PR is where automated checks report and
where a review would happen. Merging the PR is a normal git merge — it just produces a
new commit on `main`, which is the event everything else keys off.

**3. A runner.** GitHub Actions gives you an ephemeral Linux VM per job. It boots with
nothing but the OS, you tell it every step ("check out the code", "install uv", "run
the tests"), and when the job ends the machine is destroyed. Nothing persists between
runs. This is why the workflow file explicitly installs `uv` and the Railway CLI — they
aren't there otherwise.

### What actually runs, in this project

`.github/workflows/deploy.yml` defines one *workflow* with two *jobs*:

- **`check`** — runs on every PR into `main` *and* on every push to `main`. Installs
  dependencies with `uv sync --locked`, runs `manage.py check` and `manage.py test`.
- **`deploy`** — `needs: check`, so it only starts if `check` went green. Runs only
  when the event was a push to `main` (not on PRs), installs the Railway CLI, and runs
  `railway up --service web --ci`.

So: open PR → `check` runs → merge → `check` runs again on `main` → `deploy` runs →
Railway builds and restarts the container. Roughly four minutes end to end.

### How the runner is allowed to deploy

The runner is a blank machine on GitHub's infrastructure. Railway has never heard of
it. It gets in with a **Railway project token** — a long-lived credential scoped to
one project and one environment — stored as a **GitHub repository secret** named
`RAILWAY_TOKEN`.

A repository secret is write-only from the outside: you paste a value in, and after
that GitHub will inject it into a workflow's environment but never display it again,
and it's masked in log output. The workflow refers to it as
`${{ secrets.RAILWAY_TOKEN }}` — the same "code names the secret, never holds its
value" pattern as `DATABASE_URL`, just with GitHub playing the vault instead of
Railway.

Two consequences worth internalising:

- **Anyone who can merge to `main` can run arbitrary code with that token.** A
  workflow file is code, and it lives in the repo. That's the security model of CD:
  the deploy credential is only as protected as the merge button.
- **Never let a token touch a command line.** Railway's API can mint one
  programmatically and `gh secret set --body <value>` can store one — both put the
  credential into shell history, terminal scrollback, and (when an agent is driving)
  its transcript. Dashboard → GitHub web UI, by hand, is the boring correct path.

### Two things in the workflow that are subtler than they look

**Path filters can deadlock a PR.** Most commits in this repo are documentation, and
deploying for a typo fix is waste — so `paths-ignore` skips the deploy when only
`context/**`, `docs/**`, or `**.md` changed. But that filter is on the `push` trigger
*only*, deliberately. If a required check is skipped by a path filter, GitHub does not
mark it "passed" — it stays **pending forever**, and the PR can never be merged. Path
filters and required checks interact badly; keep filters off `pull_request`.

**Concurrency, because of migrations.** `railway.json`'s `startCommand` runs
`migrate --noinput` before starting gunicorn, and `numReplicas` is pinned to 1 exactly
so two containers never migrate at once. Two PRs merged a minute apart would launch
two overlapping deploys and reintroduce that race. The `deploy` job therefore declares
a concurrency group with `cancel-in-progress: false` — deploys queue, never overlap,
and are never killed mid-migration.

### The choice we made, and the one we didn't

Railway has its own GitHub integration: install its GitHub App, connect the repo to
the service, and Railway watches the branch itself. No token, no workflow file, no
runner minutes — and deploys get labelled with the commit that caused them. It can
even wait for GitHub's checks before deploying.

We went with GitHub Actions anyway, for two project-specific reasons:

1. **The trigger stays in git.** `railway.json` is version-controlled precisely so the
   deploy is reproducible from source. The native integration would put "deploy on push
   to main" into Railway dashboard state — the same category of un-reproducible
   configuration that `deploy-plan.md` already flags as a weakness for the Postgres
   region.
2. **The App isn't installed and can't be installed headlessly.** Confirmed
   empirically: `railway api 'query { githubRepos { fullName } }'` returns
   `Not Authorized`.

The honest cost: deploys show up in Railway's UI as anonymous CLI uploads rather than
"commit abc123 by tszreder", and there's now a long-lived token to rotate.

## In terms you already know

| This project's concept | What it's like in your world |
| --- | --- |
| CI — automated checks on every proposed change | An **Azure DevOps build validation policy** on a branch: the build runs on the PR, not after the fact |
| CD — main branch state automatically becomes production | The **ADF release pipeline** that publishes the ARM template onward as soon as `adf_publish` updates |
| A GitHub Actions **runner** | An **ephemeral Databricks job cluster** — spun up per run, does its work, torn down; nothing persists, so every library it needs must be installed by the job itself |
| **Workflow / job / step** (the YAML) | An ADF **pipeline / activity** definition — declarative, version-controlled, describes what runs and in what order |
| A **repository secret** (`RAILWAY_TOKEN`) | A **Key Vault–backed secret scope**, but owned by GitHub instead of Railway; write-only, injected at run time, masked in logs |
| **Required status check** before merge | A **branch policy in Azure Repos** requiring a successful build before the PR can complete |
| `concurrency` group with `cancel-in-progress: false` | Setting an ADF pipeline's **concurrency to 1** so runs queue instead of overlapping |
| Railway's native GitHub integration | **App Service Deployment Center** pointed at a repo — the platform owns the trigger, wired by clicking |
| A GitHub Actions workflow calling `railway up` | An explicit **Azure DevOps release pipeline** calling `az webapp deploy` — more YAML, but the trigger logic is reviewable in source control |

Note this is a *different* kind of trigger from the ADF-trigger analogy used for
`urls.py` in [what-a-web-app-needs-to-run.md](what-a-web-app-needs-to-run.md). There,
"trigger" meant request path → view. Here it means repository event → pipeline run.
Same word, two layers apart.

## What's universal vs. what's specific to this project's choices

**True for any web app on any platform:**

- Deploying from a laptop means the deployed artifact came from an unverifiable state.
  Deploying from a shared branch makes it auditable.
- CI is about *when* checks run (before merge, automatically), not *what* they check.
- A build machine that deploys needs a credential, and that credential is as protected
  as whoever can change the pipeline.
- Anything that mutates shared state at start-up — schema migrations, cache warms,
  seed data — makes overlapping deploys hazardous, so deploys need serialising.
- Automation makes the *branching policy* the real control. Without protection on
  `main`, "deploy on merge" also means "deploy on accidental direct push".

**Specific because this project picked Django + Railway + GitHub Actions:**

- `migrate` runs inside `railway.json`'s `startCommand`. Many stacks run migrations as
  a distinct release phase (Heroku's `release:`, a Kubernetes init container), which
  removes the replica constraint. That refactor is the prerequisite for ever raising
  `numReplicas` above 1.
- The gate is `uv sync --locked`. That specific check matters because Railway's build
  runs `uv sync --locked --no-dev`, so a `uv.lock` out of step with `pyproject.toml`
  fails the deploy — CI catches it one step earlier. A stack using plain `pip` and
  unpinned requirements has no equivalent check to run.
- `manage.py check --deploy` is Django's own production audit and is deliberately
  non-blocking here, because two of its findings are known accepted gaps.
- The token is a Railway *project* token, scoped to project + environment, which is why
  the workflow needs no `railway link` step — the token carries that context.
- On GitHub's Free plan, private-repo Actions get 2,000 Linux runner minutes per month
  with a default spending limit of $0. At ~4 minutes per deploy that's ~500 deploys a
  month, and no path to a surprise bill. Public repos are unmetered.

## Go deeper

- Martin Fowler, [Continuous Integration](https://martinfowler.com/articles/continuousIntegration.html)
  — the essay that defined the practice. Written about the *why*, assumes no
  web-specific background, and is largely about team habits rather than tooling.
- [GitHub Actions documentation](https://docs.github.com/en/actions) — the
  authoritative reference for workflow syntax, events, secrets, and runners.
- [Controlling GitHub Autodeploys](https://docs.railway.com/guides/github-autodeploys)
  — Railway's own docs for the path we did *not* take, including its "wait for CI"
  option, if the trade-off is ever worth revisiting.

## Quick recap

**Q: What's the difference between CI and CD?**
A: CI checks a proposed change automatically *before* it merges — it answers "is this
safe to merge?" CD takes whatever is on the main branch and puts it in production
automatically — it answers "what should be running right now?"

**Q: Why does the workflow install `uv` and the Railway CLI every single run?**
A: A runner is an ephemeral VM that boots with only the OS and is destroyed when the
job ends. Nothing carries over between runs, so every tool a job needs must be
installed by that job — the same reason a fresh Databricks job cluster installs its
libraries on every start.

**Q: The deploy token lives in GitHub. What does that mean for who can deploy?**
A: Anyone who can merge to `main` can run arbitrary code with that token, because the
workflow file is itself code in the repo. Branch protection on `main` isn't cosmetic —
it's the actual access control on production.

**Q: When would you choose the platform's own GitHub integration over writing a workflow?**
A: When you value commit-level traceability and one less credential more than you value
having the deploy trigger version-controlled — typically a smaller project, or one
where the platform's UI is already the source of truth. We went the other way because
`railway.json` had already established config-as-code as this project's stance.

**Q: Why can't the path filter that skips docs-only deploys also be applied to pull requests?**
A: A workflow skipped by a path filter never reports its checks, and a required check
that never reports stays pending forever — so any docs-only PR would become permanently
unmergeable.
