---
title: "Managing Python dependencies: pip, uv, and virtual environments"
slug: python-dependency-management-pip-uv-venv
date: 2026-08-01
tags: [python, tooling, web-fundamentals]
classification: mixed
prerequisites: []
---

# Managing Python dependencies: pip, uv, and virtual environments

## Why this came up

Getting `domowa-apteka` running locally meant running `uv sync`, then
`uv run manage.py migrate/runserver`. Along the way we discovered `uv` was already
installed but not on `PATH`, and that a `.venv` folder already existed in the project. That
surfaced three separate ideas at once — a virtual environment, a package installer (pip),
and a newer tool (uv) that does more than just install packages — worth separating cleanly.

## The concept, from the ground up

Three different problems, three different tools:

1. **The isolation problem — virtual environments.** Your machine has one (or a few) Python
   installations shared by *everything* — every project, every script. If Project A needs
   `django==5.2` and Project B needs `django==4.1`, installing packages straight into that
   shared Python breaks one of them. A **virtual environment** (a `.venv` folder) is a
   private, throwaway copy of just the package-installation directory — same interpreter,
   isolated `site-packages` — so each project gets its own set of installed libraries with
   no cross-contamination.

2. **The installation problem — pip.** `pip` is Python's standard package installer. Given
   a package name, it fetches it (and its dependencies) from PyPI and puts it in whichever
   Python/venv is currently active. Classic pip workflow is manual and imperative: you
   create the venv yourself (`python -m venv .venv`), activate it (which temporarily
   rewrites your shell's idea of "which Python/pip runs" for that terminal session), then
   `pip install` one thing at a time or from a `requirements.txt` you maintain by hand.

3. **The reproducibility problem — uv.** `uv` is a newer, much faster tool that does what
   pip does (install packages) *and* what `venv` does (create the isolated folder) *and*
   adds one more piece pip doesn't give you natively: a **lockfile** (`uv.lock`). Your
   `pyproject.toml` says "I need `django>=5.2.16`" — a range. `uv.lock` records the *exact*
   resolved version (and every transitive dependency's exact version) that was actually
   installed, so `uv sync` on any machine, any time, reproduces the identical dependency
   tree byte-for-byte. Plain pip has no equivalent unless you bolt on a separate tool
   (pip-tools, Poetry) to generate and honor a lock file yourself.

What we actually ran: `uv sync` read `pyproject.toml` + `uv.lock` and installed exactly
`django` into the existing `.venv` (which — per its `pyvenv.cfg` metadata — uv itself had
created two days earlier). `uv run manage.py migrate` then ran `manage.py` *using that
venv's Python*, without you ever typing an "activate" command — `uv run` finds the
project's `.venv` automatically and runs the command inside it.

One separate, unrelated snag: `uv` the *program* was installed (via `pip install --user uv`
onto your base Python, landing in `%APPDATA%\Python\Python311\Scripts\uv.exe`), but that
folder wasn't in your terminal's `PATH` — the OS-level list of folders searched when you
type a bare command name. That's a Windows/shell configuration issue, not a Python concept;
it's why `uv` "wasn't found" even though it was sitting on disk the whole time.

## The manifest and the lockfile, in detail: TOML, pyproject.toml, and uv.lock

**What TOML actually is.** `pyproject.toml`'s file extension names its *format*: **TOML**
("Tom's Obvious Minimal Language"), a plain-text config syntax — a sibling of JSON and
YAML, not a Python-specific thing. Its whole design goal is to be unambiguous enough for
tools to parse reliably, while still being easy for a human to hand-write and diff. The
building blocks are small:

```toml
[project]                       # a "table" — like a named section/object
name = "domowa-apteka"          # string
version = "0.1.0"               # also a string
requires-python = ">=3.11"      # string — Python itself doesn't parse this, pip/uv do
dependencies = [                # an array
    "django>=5.2.16",
]
```

That's genuinely all of this project's `pyproject.toml` right now. `[project]` is a table
(TOML's word for a named group of key-value pairs); other tools bolt their own tables onto
the same file — a linter might add `[tool.ruff]`, a formatter `[tool.black]` — which is why
`pyproject.toml` has become Python's single shared manifest file rather than one config file
per tool. TOML shows up outside Python too — Rust's Cargo uses it for the same "project
manifest" role.

**`pyproject.toml` is not `settings.py`.** Easy to conflate since both are "config," but
they're different layers entirely: `pyproject.toml` is read by **uv/pip**, before your app
even starts, to know what to install and how to build the package. `settings.py` (see
[what-a-web-app-needs-to-run.md](what-a-web-app-needs-to-run.md)) is read by **Django
itself**, at app startup, for runtime behavior (database connection, debug mode, etc.).
Nothing in `pyproject.toml` is Django-specific — a Flask or FastAPI project uses the exact
same file format for the exact same "what packages does this project need" purpose.

**`pyproject.toml` is hand-edited; `uv.lock` is not.** You (or an install command like
`uv add django`) write `pyproject.toml` — it states *intent*, loosely: "some version of
django that's `>=5.2.16`." `uv.lock` is generated by uv itself by actually resolving that
intent against everything on PyPI; you're not meant to hand-edit it, only regenerate it
(`uv lock`) when `pyproject.toml` changes. It gets committed to git specifically so every
machine that runs `uv sync` gets the identical resolved result — that's the whole
reproducibility point from the section above.

**Why `uv.lock` lists Django twice.** Open it and you'll see two `[[package]]` blocks named
`django` — 5.2.16 and 6.0.7 — each with its own `resolution-markers` line:

```toml
[[package]]
name = "django"
version = "5.2.16"
resolution-markers = ["python_full_version < '3.12'"]
...
[[package]]
name = "django"
version = "6.0.7"
resolution-markers = ["python_full_version >= '3.12'"]
```

This isn't a mistake or a stale leftover — `requires-python = ">=3.11"` in `pyproject.toml`
means this project claims to support *any* Python from 3.11 upward, and Django 6.0 dropped
support for Python 3.11 (it needs 3.12+). Since one lockfile has to stay correct across
every Python version the project claims to support, uv resolves *both* branches and records
which Django version applies to which Python, using a **marker** — a condition uv checks at
install time. Your actual `.venv` runs Python 3.11.9 (`python_full_version < '3.12'`), so
`uv sync` installed **5.2.16** for you specifically — the 6.0.7 entry sits in the lockfile
unused unless someone later runs this same project on Python 3.12+. Plain pip's
`requirements.txt` has no concept of this at all — one file, one flat list, no per-Python
branching; you'd need entirely separate requirement files to express the same thing.

## In terms you already know

| This project's concept | What it's like in your world |
| --- | --- |
| A virtual environment (`.venv`) — an isolated set of installed libraries for one project | A **Databricks cluster's library configuration** — each cluster has its own installed libraries, isolated from every other cluster, even though all of them might run the same underlying Databricks Runtime (≈ your one shared base Python install). Installing a library on cluster A never affects cluster B. |
| `pip install` (imperative, no built-in lock) | Running `%pip install some-lib` ad hoc in a Databricks notebook cell — it installs *something* matching what you asked for, but two people running that same cell weeks apart can silently get different resolved versions unless they're careful to pin every version by hand. |
| `uv.lock` (exact, reproducible dependency graph) | A **cluster policy / init-script-pinned library list** in Databricks — the exact set of library versions is captured once and reapplied identically every time the cluster (re)starts, instead of re-resolving "whatever's latest" on each run. |
| `pyproject.toml` (declared intent, hand-edited) | The **request/spec you write** when defining a Databricks cluster policy or an ADF linked service — "give me *a* runtime version like this," loosely. |
| Marker-based resolution (`uv.lock` picking Django 5.2.16 vs. 6.0.7 by Python version) | A **parameterized ARM/ADF template** that resolves to different actual values depending on which environment it's applied against — one definition file, multiple possible resolved outcomes, evaluated at apply-time rather than authored separately per case. |

## What's universal vs. specific to this project's choices

**True for any Python project**, not just this one:
- The isolation problem (venvs) and the installation problem (pip or equivalent) exist for
  every Python project — this isn't a Django thing.
- Lockfiles solving "reproducible installs" is a pattern that shows up everywhere in
  software, not just Python — `uv.lock` plays the same role as a `package-lock.json`
  (npm) or a pinned Terraform provider version.

**Specific because this project picked uv** (per `context/foundation/tech-stack.md`):
- A pip-only project would need `python -m venv .venv` run explicitly, manual activation
  per terminal session, and a separately-maintained `requirements.txt` with no built-in
  guarantee it matches what's actually installed.
- With uv, `AGENTS.md`'s documented commands (`uv sync`, `uv run manage.py ...`) already
  assume uv is present — there's no pip-based fallback documented for this repo.

## Go deeper

- [uv: Python packaging in Rust — Astral's announcement post](https://astral.sh/blog/uv) —
  written for people who already know pip's pain points, explains what uv adds and why.
- [uv documentation — Astral](https://docs.astral.sh/uv/) — authoritative reference for
  `uv sync`, `uv run`, and lockfile behavior.
- [TOML's own site, toml.io](https://toml.io/en/) — the full spec, but short and readable;
  the front page alone covers every syntax element you'll actually encounter in
  `pyproject.toml`.

## Quick recap

**Q: If `uv sync` already installs everything, why does `.venv` need to exist at all?**
A: `uv sync` needs *somewhere* isolated to install into — `.venv` is that isolated folder;
uv just creates and manages it for you instead of you running `python -m venv` yourself.

**Q: What's the actual difference between what pip does and what uv does?**
A: Pip only installs packages you tell it to, with no built-in lockfile. Uv installs
packages *and* manages the venv *and* maintains `uv.lock` so installs are exactly
reproducible across machines and time.

**Q: Why didn't typing `uv` work even though it was installed?**
A: It was installed to a real folder on disk, but that folder wasn't listed in the
terminal's `PATH`, so the shell had no way to find it by name alone — unrelated to Python
or uv itself, purely an OS-level lookup issue.

**Q: When would you reach for plain pip instead of uv?**
A: Rarely for a new project today — uv is a drop-in replacement that's faster and adds
locking for free. Pip still shows up in older projects, tutorials, and environments where
installing an extra tool isn't an option.

**Q: Why does `uv.lock` list two different Django versions (5.2.16 and 6.0.7)?**
A: `pyproject.toml` claims support for Python 3.11+, but Django 6.0 dropped Python 3.11
support — so one version can't cover the whole claimed range. Uv resolves both branches and
tags each with a `resolution-markers` condition; your actual Python (3.11.9) installs
5.2.16, and 6.0.7 sits there unused unless the project later runs on Python 3.12+.

**Q: Is `pyproject.toml` the same kind of "config" as Django's `settings.py`?**
A: No — different layer entirely. `pyproject.toml` is read by uv/pip before your app runs,
to know what to install; `settings.py` is read by Django itself, at runtime, for app
behavior. Same word ("config"), unrelated purposes.

**Q: Should I ever hand-edit `uv.lock`?**
A: No — treat it like generated output. Change `pyproject.toml` (or run `uv add <package>`)
and let `uv lock`/`uv sync` regenerate it; hand-editing it risks a lockfile that no longer
matches what uv would actually resolve.
