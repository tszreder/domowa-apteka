---
title: "Working on two changes at once: branches, one folder, and git worktrees"
slug: branches-worktrees-and-parallel-work
date: 2026-08-14
tags: [git, workflow, tooling, ci-cd]
classification: mixed
prerequisites: [ci-cd-and-deploy-triggers]
---

# Working on two changes at once: branches, one folder, and git worktrees

## Why this came up

Planning S-02 (`add-drug-with-substance-resolution`) and F-02 (`registry-freshness-refresh`)
raised two questions at once: will the two changes fight over the same files, and how do you
even hold two in-progress changes at the same time — one folder, or two? The second question
is really a git question, and it has a precise answer once you know what a branch actually
is. The session also turned up a surprise worth pinning down: `git branch --merged main`
claimed four already-merged branches were *not* merged.

## Builds on

See [ci-cd-and-deploy-triggers.md](ci-cd-and-deploy-triggers.md) for what a git remote, a
pull request, and merge-to-`main`-deploys-to-production mean in this repo — this doc assumes
those and goes one layer down, into what git is doing locally.

## The concept, from the ground up

### A commit is a version; the history is append-only

Git's storage is closest to a **Delta Lake transaction log**. Every commit is an immutable
snapshot of the whole tree plus a pointer to its parent. Nothing is ever edited in place;
new versions are appended. That's the entire object store — a chain of versions.

### A branch is a label, not a copy

Here's the part that surprises people coming from folder-based version control: **a branch
is a movable pointer to one commit.** It is a file containing a 40-character hash. Creating
a branch copies nothing and costs nothing — it's a Delta table alias pointing at a version,
not a second copy of the data.

`main` points at one commit. `feature/x` points at another. When you commit, the branch
pointer you're currently on moves forward to the new commit. "Currently on" has a name:
**HEAD**, which is just a pointer to *which branch pointer* you're moving.

### The working tree is the one materialized copy

The files you actually open and edit — `registry/models.py`, `db.sqlite3`, everything you
see in the folder — are the **working tree**. This is git *materializing* one version onto
disk so you can work with it, the way reading a Delta table `VERSION AS OF 12` materializes
one version into a dataframe.

And here's the constraint the whole question turns on: **one folder holds one materialization
at a time.** `git switch f-02` doesn't open a second view; it overwrites the files in place
to match a different commit. You cannot have S-02's `households/views.py` and F-02's
`registry/loader.py` both on disk simultaneously in one folder, because "on disk" is a single
slot.

This is why the constraint bites here specifically: `/10x-implement` commits to **whatever
branch HEAD points at**. Two agent sessions running in one folder would both commit to the
same branch, interleaving two unrelated changes — regardless of whether they touched the same
files.

### What `git worktree` changes

`git worktree add ../domowa-apteka-f02 -b feature/registry-freshness-refresh` creates a
**second folder with its own working tree and its own HEAD, sharing the same `.git` object
store.**

Two materializations, one history. In your world: **two Databricks clusters attached to the
same metastore** — separate compute, separate local scratch, one shared underlying storage.
Commits made in either folder are immediately visible to the other (`git log` in one shows
the other's commits), because there's only one history. But each folder has its own checked-out
branch, and git refuses to check out the same branch in two worktrees — which is exactly the
guardrail you want.

Remove one with `git worktree remove ../domowa-apteka-f02` when the change is merged.

### What a worktree does *not* share: anything gitignored

This is the tax, and it's concrete in this repo. A new worktree starts with only the
git-tracked files. Everything in `.gitignore` is absent:

- **`.venv/`** — needs `uv sync` in the new worktree (see
  [python-dependency-management-pip-uv-venv.md](python-dependency-management-pip-uv-venv.md)
  for why each environment is isolated).
- **`db.sqlite3`** — 8.4 MB, holding 20,245 products, 3,391 substances and 25,884 links
  (counted 2026-08-14). A fresh worktree starts with **no database at all**, so any S-02
  autocomplete work there would need `migrate` plus a full registry import. Copying the file
  across (`cp db.sqlite3 ../worktree/`) is the shortcut.
- **`.env`** — exists locally in this repo and is gitignored, so a new worktree gets none and
  falls back to whatever defaults `settings.py` declares. Copy it across too.

### Conflicts are a separate question from branches

Two branches touching the same file only becomes a problem at merge time, and only if they
touched **overlapping lines**. Git merges different regions of the same file cleanly. Two
people editing different sections of the same PBIX is the closer analogy than two writers to
the same Delta partition — usually fine, occasionally a genuine conflict.

The exception in this project isn't a *text* conflict at all: two branches each adding
`registry/migrations/0002_*.py` produces two files git merges happily and Django then refuses
to run, because the migration graph would have two leaf nodes and no defined order. See
[database-migrations-and-dev-prod-parity.md](database-migrations-and-dev-prod-parity.md) for
why migrations are an ordered chain. The fix is ownership decided up front — one change owns
that app's migrations — not conflict resolution after the fact.

### Why `--merged` lied about four merged branches

`git branch --merged main` asks a purely structural question: *is this branch's tip commit an
ancestor of `main`?* This repo's PRs are **squash-merged** — GitHub collapses a branch's
commits into one new commit on `main`. The content arrives; the original commits do not. The
branch tip is therefore not an ancestor of `main`, and `--merged` says "no" for a branch whose
work is fully shipped.

That's the same shape as collapsing a pipeline run's incremental steps into a single published
change: the *result* is identical, the step-by-step lineage isn't preserved, so any check based
on lineage rather than content gives the wrong answer.

Consequences:

- `git branch -d` (safe delete) refuses; `git branch -D` (force) is required — and is
  legitimately safe once you've confirmed the work merged.
- The reliable check is the PR list, not git ancestry:
  `gh pr list --state all --json number,headRefName,state`. That's how the four branches
  deleted in this session were confirmed against merged PRs #15–#18.

## In terms you already know

| This project's concept | What it's like in your world |
| --- | --- |
| The commit history / `.git` object store | A **Delta Lake transaction log** — immutable, append-only ordered versions; nothing is edited in place. |
| A **branch** (movable pointer to one commit) | A **Delta table alias/tag pointing at a version** — a label, cheap to create, not a copy of the data. |
| **HEAD** | The **"current version" marker** — which label you're standing on and will move when you write. |
| The **working tree** (files on disk) | **Materializing one `VERSION AS OF` into a dataframe** — one version realized at a time, from one location. |
| `git switch` / checkout | **Re-reading the table at a different version into the same location** — the previous materialization is replaced, not kept alongside. |
| `git worktree` (second folder, shared `.git`) | **Two Databricks clusters attached to the same metastore** — separate compute and local scratch, one shared underlying storage. |
| **Squash merge** | **Collapsing a run's incremental steps into one published change** — same result, lineage not preserved, so lineage-based checks report wrongly. |
| A **merge conflict** | **Two people editing the same section of the same PBIX** — different sections merge fine; the same lines need a human. |

## What's universal vs. what's specific to this project's choices

**True for any git repository, any stack:**

- A branch is a pointer to a commit; creating one copies nothing.
- One working tree materializes one commit at a time — this is why one folder can only hold
  one branch's state.
- `git worktree` gives additional working trees over one shared history, and refuses to check
  out the same branch twice.
- Worktrees carry nothing that is gitignored — dependencies, local databases, `.env` files
  all start absent.
- Squash-merging breaks `--merged` / ancestry-based "is this branch done?" checks.

**Specific because this project picked Django + GitHub PRs + Railway + the 10x skill chain:**

- **The migration-leaf collision** is a Django (and Rails/Alembic-style) hazard. A project
  without an ordered migration graph — raw SQL scripts, or a schema-diff tool like SSDT that
  computes the delta at publish time — has no equivalent failure.
- **The empty-database tax** is specific to dev-on-SQLite-in-a-gitignored-file. If local dev
  pointed at a shared Postgres via `DATABASE_URL`, every worktree would share one database and
  this tax would vanish (along with the isolation it provides).
- **`/10x-implement` commits to whatever branch is checked out** is agent-tooling behavior, not
  git behavior. It's the reason concurrency matters here more than in ordinary solo work.
- **Squash-merge is a per-repo GitHub setting.** A repo configured for merge commits or
  fast-forward merges would keep the original commits, and `--merged` would answer correctly.
- **Merging to `main` deploys to production here**, so branch discipline is a production
  safety property, not just tidiness — see
  [ci-cd-and-deploy-triggers.md](ci-cd-and-deploy-triggers.md).

## The decision rule

The question is **not** "do the two changes touch the same files?" — that's a merge-time
question, usually minor. It's **"will two sessions be live at the same time?"**

| Situation | Use |
| --- | --- |
| One change at a time; `git switch` between them | **One folder.** No worktree tax, no duplicated database. |
| Two Claude Code sessions running concurrently | **Worktrees.** One folder cannot hold two HEADs, and cross-committing is silent when it happens. |

Claude Code exposes this directly: an agent can be launched with `isolation: "worktree"`, and
there's an `EnterWorktree` tool — the mechanics above are what those are doing underneath.

```bash
# create
git worktree add ../domowa-apteka-f02 -b feature/registry-freshness-refresh
cd ../domowa-apteka-f02
uv sync
cp ../domowa-apteka/db.sqlite3 .     # skip the 20k-product re-import
cp ../domowa-apteka/.env .           # gitignored, so the worktree has none

# see what exists
git worktree list

# clean up after the PR merges
git worktree remove ../domowa-apteka-f02
```

## Go deeper

- [Atlassian: Using branches](https://www.atlassian.com/git/tutorials/using-branches) — the
  clearest plain-language walkthrough of branches-as-pointers, with diagrams, no prior git
  internals assumed.
- [Pro Git §3.1: Branches in a Nutshell](https://git-scm.com/book/en/v2/Git-Branching-Branches-in-a-Nutshell)
  — the canonical explanation of the pointer model, still readable.
- [`git worktree` reference](https://git-scm.com/docs/git-worktree) — the official reference
  for `add` / `list` / `remove` and the same-branch restriction.

## Quick recap

**Q: What is a branch, physically?**
A: A file containing one commit hash — a movable pointer. Creating one copies no files and
costs nothing; it's a label on a version, not a copy of the data.

**Q: Why can't one folder hold two in-progress changes?**
A: The folder holds one *working tree* — one materialized version of the files. `git switch`
overwrites those files rather than opening a second view, so there is exactly one slot.

**Q: When would you reach for a worktree instead of just switching branches?**
A: When two sessions need to be live simultaneously — most concretely, two Claude Code
sessions, since `/10x-implement` commits to whatever branch is checked out and would otherwise
interleave two changes on one branch. For sequential solo work, switching is simpler and
avoids duplicating `.venv` and the dev database.

**Q: Two branches both add a file to `registry/migrations/` — what actually breaks?**
A: Not the git merge; git accepts both files. Django refuses to run, because the migration
graph then has two leaf nodes and no defined order. Prevent it by deciding up front which
change owns that app's migrations.

**Q: `git branch --merged main` says a branch isn't merged, but its PR is closed as merged. Who's right?**
A: Both, about different questions. `--merged` asks whether the branch tip is an *ancestor* of
`main`; squash-merging brings the content over as a new commit, so it isn't. Check the PR
state (`gh pr list`) for content, then delete with `-D`.
