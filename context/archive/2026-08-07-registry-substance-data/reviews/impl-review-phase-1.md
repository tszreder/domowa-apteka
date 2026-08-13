<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: Registry-backed product and active-substance data (F-01)

- **Plan**: `context/changes/registry-substance-data/plan.md`
- **Scope**: Phase 1 of 4 — App scaffold, data model, and read-only admin
- **Date**: 2026-08-13
- **Verdict**: APPROVED
- **Findings**: 0 critical, 2 warnings, 3 observations — all 5 triaged (2026-08-13)
- **Triage**: F1 Fix A · F2 accepted · F3 Fix A · F4 fixed · F5 fixed. Per-finding outcomes are
  on each `Decision:` line below.

## Method note

Reviewed inline rather than via the skill's two sub-agents. The diff is 8 new files plus two
one-line edits, and the reviewing context already held the plan, `lessons.md`, the `households`
patterns being compared against, and every line of the new code. Two cold agents would have
re-derived that at cost without adding coverage. Pattern depth was scaled to scope, as the skill
itself directs for small diffs.

## Change scope

Phase 1 is **uncommitted** — the whole phase sits in the working tree, so scope was taken from
`git status` rather than a commit range.

| Path | Status | In plan? |
| --- | --- | --- |
| `registry/__init__.py`, `registry/apps.py` | new | ✅ Phase 1 § 1 |
| `registry/models.py` | new | ✅ Phase 1 § 2 |
| `domowa_apteka/settings.py` | modified (+1 line) | ✅ Phase 1 § 3 |
| `pyproject.toml` | modified (+1 word) | ✅ Phase 1 § 4 |
| `registry/admin.py` | new | ✅ Phase 1 § 5 |
| `registry/migrations/0001_initial.py`, `migrations/__init__.py` | new | ✅ Phase 1 § 6 |
| `registry/tests/__init__.py` | new | ✅ Phase 1 § 1 (tests package replaces `tests.py`) |
| `registry/views.py` | new | ⚠️ startapp scaffold, unused — see F4 |
| `context/changes/registry-substance-data/plan-brief.md` | modified | ⚠️ EXTRA — see F2 |
| `context/changes/registry-substance-data/change.md` | modified | ✅ skill-mandated status stamp |
| `context/foundation/roadmap.md` | modified | ➖ pre-existing dirty from `/10x-new`; untouched this phase |

No planned item is missing. Every field, flag, and value in the Phase 1 § 2 model contract is
present verbatim, including the `db_index=True` on `Product.name` that plan-review F9 added and
the single `last_seen_as_of` column that F5 settled on.

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| Plan Adherence | PASS |
| Scope Discipline | WARNING |
| Safety & Quality | WARNING |
| Architecture | WARNING |
| Pattern Consistency | PASS |
| Success Criteria | PASS |

## Success criteria

| ID | Criterion | Result |
| --- | --- | --- |
| 1.1 | `makemigrations --check --dry-run` | PASS — "No changes detected", exit 0 |
| 1.2 | `manage.py migrate` | PASS — `registry.0001_initial` applied, exit 0 |
| 1.3 | `mypy` with `registry` in scope | PASS — no issues, 28 source files, exit 0 |
| 1.4 | `manage.py check` | PASS — no issues, exit 0 |
| 1.5 | `manage.py test` | PASS — 33 tests OK, exit 0 |
| 1.6 | Admin pages load, empty lists | PENDING — correctly `[ ]`, awaiting user |
| 1.7 | No Add / Save / Delete affordance | PENDING — correctly `[ ]`, awaiting user |

No rubber-stamping: both manual rows are unchecked, matching the fact that the user has not yet
confirmed them. Phase 1 § 6's DDL review was performed — `registry_productsubstance` carries no
unique constraint on `(product, substance)`, verified against `sqlmigrate` output, not just the
migration file.

## Findings

### F1 — `source_order` is written but nothing ever orders by it

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality
- **Location**: `registry/models.py:114`
- **Detail**: The plan gives `source_order` one job — "the 0-based position of the source element
  within its product, **preserving row order for repeated substances**". The column is stored
  correctly, but no read path uses it. Verified empirically rather than assumed:
  `ProductSubstance._meta.ordering` is `[]`, and the SQL Django emits for
  `product.substance_links.all()` carries **no `ORDER BY` clause** at all.

  So the order in which `Altacet`'s two `Aluminii acetotartras` rows come back — the exact case
  the column exists for — is whatever the engine happens to return. That is unspecified in SQL,
  and it is the shape of assumption `lessons.md` rule 2 was written about: it will look stable on
  dev SQLite (insertion order) and is not guaranteed to stay stable on production Postgres, where
  the loader's per-snapshot delete-and-recreate churns the heap every import.

  It bites in three places downstream: Phase 1's admin inline renders links in unspecified order
  today; Phase 2's `Altacet` test asserts amounts against `source_order`; and S-02 will display
  substance lists to users.
- **Fix A ⭐ Recommended**: Add `class Meta: ordering = ['source_order']` to `ProductSubstance`
  and regenerate `0001_initial`.
  - Strength: Makes the guarantee global and unforgettable — no read site can omit it. The
    migration is still uncommitted, so regenerating is clean rather than an `AlterModelOptions`
    follow-up.
  - Tradeoff: Default ordering applies to every query on the model, including ones that don't
    want it. Harmless here — links are read per-product (≤46 rows, indexed on `product_id`), and
    `bulk_create`/`delete` ignore ordering entirely.
  - Confidence: HIGH — measured the absent `ORDER BY` directly.
  - Blind spot: None significant.
- **Fix B**: Leave the model alone; add `.order_by('source_order')` at each read site, plus
  `ordering = ('source_order',)` on the admin inline.
  - Strength: No default ordering surprises on future aggregate or subquery use.
  - Tradeoff: Every future read site must remember. The one guarantee the column exists to
    provide becomes opt-in, and a missed call site fails silently.
  - Confidence: HIGH.
  - Blind spot: None significant.
- **Decision**: FIXED via Fix A — `class Meta: ordering = ['source_order']` added to
  `ProductSubstance`; `0001_initial` deleted and regenerated so the option lands inside
  `CreateModel` rather than trailing an `AlterModelOptions` onto a never-shipped app. Verified:
  the emitted SQL now carries `ORDER BY "registry_productsubstance"."source_order" ASC`,
  `makemigrations --check` reports no changes, mypy clean, and the regenerated DDL still has no
  unique constraint on `(product, substance)`.

### F2 — `plan-brief.md` rewritten outside Phase 1's Changes Required

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Scope Discipline
- **Location**: `context/changes/registry-substance-data/plan-brief.md`
- **Detail**: Six rows of the brief were edited during Phase 1. The file is not in Phase 1's
  "Changes Required", so this is an EXTRA by the letter of the plan.

  The justification: the brief was untracked, so the phase-1 bootstrap rule pulls it into the
  first commit, and it contradicted the triaged plan on the production path (`railway ssh`, which
  plan-review F1 removed), the schema (`source_as_of`, which F5 dropped), the version guard (a
  pinned namespace assert, which F3 replaced with `namespace_for_url()`), and the retired 7 MB
  memory figure (F2). Committing a brief that states the opposite of the plan it summarizes is a
  real defect, and `/10x-impl-review` reads both.

  Flagged for the record rather than as a problem: it was disclosed at the time, it is confined
  to the change folder, and it touches no code.
- **Fix**: None needed — accept as a documented in-folder correction, or revert the brief and
  file the sync as a follow-up if you prefer strict phase boundaries.
- **Decision**: ACCEPTED — kept as a documented in-folder correction. A plan brief entering git
  history stating the opposite of the plan it summarizes is the worse outcome; the edit is
  disclosed here, confined to the change folder, and touches no code.

### F3 — `SourceField` placement pre-constrains Phase 2's "pure" parser

- **Severity**: 💡 OBSERVATION
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Architecture
- **Location**: `registry/models.py:11`
- **Detail**: `SourceField` is a `models.TextChoices` in `models.py`. Phase 2's parser must emit
  those two values, so it will either import `registry.models` — which requires the Django app
  registry to be loaded — or hardcode the literals and risk drift.

  The plan calls the parser "pure … no database and no network" and says it "imports no Django
  settings". Importing an enum is neither a settings import nor a query, so this is not a
  violation. But it is a decision Phase 1 has quietly made on Phase 2's behalf, and it is worth
  making deliberately now rather than discovering it mid-parser.

  Concrete consequence: Phase 2's manual criteria 2.5–2.7 parse the real 73.7 MB file and measure
  memory. Under this shape that measurement script must run through `manage.py shell` or call
  `django.setup()` — it cannot be a bare `python parse.py`.
- **Fix A ⭐ Recommended**: Keep it. Have `registry/parser.py` import `SourceField` from
  `registry.models` in Phase 2.
  - Strength: One source of truth for the two literals, which is the point of the column. The
    Django idiom. Adds no module the plan didn't ask for. Every context the parser runs in —
    tests, the management command, the Phase 2 measurement — has Django loaded anyway.
  - Tradeoff: `parse_registry` is not importable without `django.setup()`, so the memory
    measurement needs one extra line of harness.
  - Confidence: HIGH — the constraint is mechanical and already understood.
  - Blind spot: None significant.
- **Fix B**: Move the two literals into a Django-free module that both `models.py` and
  `parser.py` import.
  - Strength: The parser becomes importable standalone; the measurement script stays trivial.
  - Tradeoff: Adds a module the plan doesn't list, and splits the enum from the field that
    validates against it.
  - Confidence: HIGH.
  - Blind spot: None significant.
- **Decision**: FIXED via Fix A — no code change; the placement stands as a now-deliberate
  decision. **Binding on Phase 2**: `registry/parser.py` imports `SourceField` from
  `registry.models` and must not hardcode the two string literals. The Phase 2 memory
  measurement (criteria 2.5–2.7) accordingly runs through `manage.py shell` or an explicit
  `django.setup()`, not a bare `python parse.py`.

### F4 — Generated `views.py` left in place in a now-mypy-covered app

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Scope Discipline
- **Location**: `registry/views.py:1`
- **Detail**: `startapp` emitted `from django.shortcuts import render` plus a placeholder comment.
  The plan's "What We're NOT Doing" says "no views, no URLs — that is S-02", while Phase 1 § 1
  says "standard `startapp` layout", so the file is defensible either way. It is dead code inside
  a package that is now under `[tool.mypy] files`, and the plan explicitly deleted the *other*
  unused scaffold file (`tests.py`) for the same class of reason.
- **Fix**: Delete `registry/views.py`; S-02 recreates it when it actually adds a view.
- **Decision**: FIXED — `registry/views.py` deleted, matching the plan's own treatment of the
  unused `tests.py` scaffold.

### F5 — Admin inline issues one query per substance row

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: `registry/admin.py:13`
- **Detail**: `ProductSubstanceInline` renders `substance` as a read-only FK without
  `select_related`, so the product detail page issues one extra query per link row. Bounded and
  small — the observed maximum is 46 substances on one product — but `Vaminolact` alone (19 rows)
  will do 19 round trips on a single page view.

  The plan pre-empts this: Performance Considerations states "no query optimization is in scope"
  for F-01. Recorded so the decision is explicit rather than an oversight.
- **Fix**: Add `def get_queryset(self, request): return super().get_queryset(request).select_related('substance')`
  to the inline — or skip, on the plan's own scope note.
- **Decision**: FIXED — typed `get_queryset` added to `ProductSubstanceInline` returning
  `.select_related('substance')`. Collapses the per-row query to one join.

## Post-triage verification

Re-run after F1, F4 and F5 were applied:

| Check | Result |
| --- | --- |
| `makemigrations --check --dry-run` | PASS — "No changes detected", exit 0 |
| `mypy` | PASS — no issues, 27 source files (one fewer: `views.py` deleted), exit 0 |
| `manage.py check` | PASS — no issues, exit 0 |
| `manage.py test` | PASS — 33 tests OK, exit 0 |
| Admin smoke (temp test DB) | Product/Substance changelists 200 with no own Add link; detail page 200 with no Save and no Delete; `/product/add/` 403 |

The admin smoke check compares against the `households` Add link on the same page, so a false
"no Add button" result would be caught rather than assumed.
