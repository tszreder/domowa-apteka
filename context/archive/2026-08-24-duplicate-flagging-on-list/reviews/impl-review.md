<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: Duplicate flagging on the household list

- **Plan**: `context/changes/duplicate-flagging-on-list/plan.md`
- **Scope**: Phases 1–3 of 3 (full plan)
- **Date**: 2026-08-25
- **Verdict**: NEEDS ATTENTION → **APPROVED after triage** (all 5 findings fixed 2026-08-25)
- **Findings**: 0 critical, 3 warnings, 2 observations — 5 fixed, 0 skipped, 0 accepted

## Verdicts

| Dimension | Verdict (at review) | After triage |
|-----------|---------------------|--------------|
| Plan Adherence | WARNING | PASS — F2 written back into the plan |
| Scope Discipline | PASS | PASS |
| Safety & Quality | WARNING | PASS — F1 ordering pinned |
| Architecture | PASS | PASS |
| Pattern Consistency | PASS | PASS — F4 empty-`<ul>` guard added |
| Success Criteria | WARNING | PASS — F3 test added, F5 verified live |

## Post-triage verification (2026-08-25)

| Command | Result |
|---|---|
| `uv run manage.py test` | PASS — 178 tests (was 176; +2 added by F1 and F3), OK |
| `uv run mypy .` | PASS — no issues in 60 source files |
| `uv run manage.py check` | PASS — 0 issues |

Both new tests were mutation-checked rather than merely observed green: F1's fails under
`PYTHONHASHSEED` 1–6 with the sort removed, F3's fails under either
`.order_by('product__name')` or `.order_by('added_at')` on the view's queryset.

## Automated verification (re-run during this review)

| Command | Result |
|---|---|
| `uv run manage.py test` | PASS — 176 tests, OK |
| `uv run mypy .` | PASS — no issues in 60 source files |
| `uv run manage.py check` | PASS — 0 issues |

## Findings

### F1 — Badge substance and partner order is nondeterministic across worker processes

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: `pharmacy/duplicates.py:158`
- **Detail**: `for substance_key in key_a & key_b:` iterates a `frozenset[str]`. Python
  randomises string hashing per process (`PYTHONHASHSEED` is unset here), so that
  iteration order — and therefore the insertion order of `DuplicateGroup.partners`,
  the order of lines in the expanded `<details>` body, and the order of names in the
  `Wspólna substancja: …` summary via `partner_names` — differs between processes.
  Measured: five `uv run python` processes intersecting the same two sets produced
  three distinct orderings. In production this means two gunicorn workers render the
  same badge with the partner names in different orders, so the text under an item
  changes as the user reloads. The plan makes non-surprising ordering an explicit goal
  ("the screen does not reorder unpredictably around the user", Critical Implementation
  Details), and Phase 3's own test acknowledges the gap with the comment
  `# ... order not pinned` (`pharmacy/tests/test_item_list.py:166`). Nothing is
  misclassified — only the display order is unstable.
- **Fix**: Sort the shared keys by display name before building the partner map —
  `for substance_key in sorted(key_a & key_b, key=lambda k: substance_names[k]):` —
  and pin it with a test that asserts the rendered summary/detail order rather than
  using `assertIn` on unordered fragments.
  - Strength: One line; makes `partner_names` deterministic for free (it derives from
    `partners` insertion order); lets the Phase 3 tests drop their "order not pinned"
    caveat and assert real strings.
  - Tradeoff: Alphabetical order is not the registry's `source_order`, so a combination
    product's badge may not list substances in package order. Package order is ambiguous
    across two products anyway, so nothing is lost.
  - Confidence: HIGH — nondeterminism reproduced empirically; the fix is a stdlib sort
    over a set the function already has display names for.
  - Blind spot: None significant.
- **Decision**: FIXED — `sorted(key_a & key_b, key=lambda k: substance_names[k])` at
  `pharmacy/duplicates.py:158` with an explaining comment, pinned by
  `BuildListViewTests.test_shared_substances_are_ordered_alphabetically_not_by_set_iteration`
  (three shared substances, links created in reverse alphabetical order so a pass cannot
  come from insertion order). Mutation-checked: with the sort removed the test fails under
  `PYTHONHASHSEED` 1–6; with it restored it passes under all six. The Phase 3 rendering
  test's `# order not pinned` comment was replaced with an accurate note that its
  cross-group order comes from `added_at`, not set iteration.

### F2 — A planned Phase 1 test case was replaced by a weaker one and the plan was left stating the original

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Plan Adherence
- **Location**: `pharmacy/tests/test_duplicates.py:103` (plan: `plan.md:234-235`, `plan.md:437-438`)
- **Detail**: The plan requires "two products whose substances differ only in
  `Substance.name` but share a `name_key` → `FULL` (proves the comparison is keyed on
  identity, not display form)". That state is unrepresentable: `Substance.name_key` is
  unique, so two rows cannot share a key with different names. The implementation
  correctly substituted `test_reads_name_key_not_display_name` (one substance whose
  `name` and `name_key` differ) and documented the reasoning in a 12-line test comment.
  The resolution is right; the disclosure is in the wrong place. `plan.md:234-235` and
  `plan.md:437-438` still assert the impossible case as a delivered contract, and the
  plan is what `/10x-impl-review` and the next implementer read as ground truth. This is
  the exact situation `context/foundation/lessons.md` records as an accepted rule ("A
  plan can contradict itself; resolve it in code *and* write the resolution back" —
  "a commit message and a docstring do not reach the next reader of the plan").
- **Fix**: Edit the two plan bullets to state that the shared-`name_key`/differing-`name`
  pair is unrepresentable under `Substance.name_key`'s unique constraint, and that the
  delivered test proves `substance_keys` reads the identity column instead. Mark it as
  corrected during implementation.
  - Strength: Applies a rule this project already accepted; costs two sentences; stops a
    future reader from "restoring" a test that cannot be written.
  - Tradeoff: Edits a plan after the fact, so the plan is no longer a pristine record of
    what was believed at planning time.
  - Confidence: HIGH — the constraint is verifiable in `registry/models.py`, and
    lessons.md already prescribes this exact remedy.
  - Blind spot: None significant.
- **Decision**: FIXED — both plan bullets struck through and annotated **Corrected during
  implementation**, naming the unique constraint on `Substance.name_key` as the reason the
  case is unrepresentable and `SubstanceKeysTests.test_reads_name_key_not_display_name` as
  the delivered substitute carrying the same intent.

### F3 — Cluster ordering is called a Critical Implementation Detail but no test pins it

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Success Criteria
- **Location**: `pharmacy/tests/test_item_list.py` (plan: `plan.md:151-155`, `plan.md:439`)
- **Detail**: The plan elevates ordering to Critical Implementation Details ("A cluster's
  position ... is determined by its newest member's `added_at`, so adding an item still
  moves its group to the top") and its Testing Strategy names "the builder's
  partitioning, clustering, labelling, and **ordering** rules" as unit-test scope. The
  implementation is correct — `build_list_view` preserves first-appearance order and the
  view relies on `Item.Meta.ordering = ['-added_at']` — but a grep across
  `pharmacy/tests/` finds no test asserting order at either level. `build_list_view`'s
  docstring explicitly disclaims responsibility ("`items` must already be ... iterated in
  the caller's intended display order"), which pushes the guarantee onto the view, where
  it is equally untested: adding `.order_by('product__name')` to `pharmacy/views.py:29`
  would silently break newest-first grouping with a green suite. Progress item 2.7
  verified this manually once, live; nothing prevents regression.
- **Fix A ⭐ Recommended**: Add an integration test to `ItemListRenderingTests` — build an
  older cluster plus a newer single, then add an item that joins the older cluster, and
  assert the cluster's markup appears before the single in `response.content`.
  - Strength: Covers both halves of the guarantee at once — the builder's
    first-appearance rule *and* the view's queryset ordering, which is the half the
    builder's docstring hands off and the half a future `.order_by()` would break.
  - Tradeoff: A string-position assertion over rendered HTML is more brittle than a
    structural one; needs an explicit `added_at` setup since `auto_now_add` fires within
    the same test tick.
  - Confidence: HIGH — mirrors how the existing rendering tests already assert on
    `response.content`.
  - Blind spot: Have not checked whether `auto_now_add` timestamps in a single test body
    separate reliably on this SQLite build; the setup may need explicit `added_at` writes.
- **Fix B**: Add a unit test to `BuildListViewTests` asserting `view.groups` order follows
  the input iterable's first-appearance order.
  - Strength: Cheapest and most precise — tests the rule where it actually lives, with no
    HTML parsing.
  - Tradeoff: Cannot catch a regression in the view's queryset ordering, which is where
    the plan's stated failure mode ("adding an item still moves its group to the top")
    would actually break.
  - Confidence: HIGH — the builder already takes a plain iterable, so the test is three
    lines.
  - Blind spot: Leaves `pharmacy/views.py:28-32` unguarded.
- **Decision**: FIXED via Fix A — added
  `ItemListRenderingTests.test_adding_to_an_older_cluster_moves_it_above_a_newer_single`.
  Product names are chosen so alphabetical order differs from `added_at` order, and
  `added_at` is written explicitly through `.update()` (Fix A's blind spot — `auto_now_add`
  stamps all three items in one tick and cannot be set on create — confirmed and handled).
  Two assertions: the joined cluster renders above the older single, and within the cluster
  the newest member renders first. Mutation-checked: adding either
  `.order_by('product__name')` or `.order_by('added_at')` to the view's queryset fails the
  test; `pharmacy/views.py` restored unmodified.

### F4 — An empty `<ul class="item-list">` renders when every item is unresolved

- **Severity**: 📋 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency
- **Location**: `pharmacy/templates/pharmacy/item_list.html:8-9`
- **Detail**: The outer guard is `{% if items %}`, but the `<ul class="item-list">` it
  opens is filled from `list_view.groups`. A household whose items all failed substance
  resolution — the exact S-02 lookup-failure path this slice was built to handle —
  has a non-empty `items` and an empty `groups`, so the page emits an empty `<ul>` above
  the unresolved section. Pico styles bare `ul` with vertical margin, so it renders as a
  stray gap. Cosmetic only; no test covers it because
  `test_two_unresolved_items_are_not_grouped_and_appear_in_unresolved_section` asserts
  content, not layout.
- **Fix**: Wrap the `<ul class="item-list">` block in `{% if list_view.groups %}`, leaving
  the outer `{% if items %}` to keep owning the "no items at all" message.
- **Decision**: FIXED — guard added and the block re-indented. The explanatory note uses
  `{% comment %}`/`{% endcomment %}`, not `{# … #}`: Django's `{# #}` is single-line only,
  so the first draft would have leaked comment text into the rendered page. Pinned by a
  new `assertContains(response, 'class="item-list"', count=1)` on
  `test_two_unresolved_items_are_not_grouped_and_appear_in_unresolved_section` — one list
  (the unresolved section's), not two.

### F5 — Progress item 3.6 is checked but half its criterion was not verified

- **Severity**: 📋 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Success Criteria
- **Location**: `context/changes/duplicate-flagging-on-list/plan.md:537`
- **Detail**: Phase 3's manual criterion reads "a collapsed badge fits without wrapping
  into a paragraph, **and expanding one does not shift the rest of the list
  disruptively**". The Progress note verifies the first clause live at 390×844 and states
  plainly that "the live click-to-expand interaction was not separately captured before
  this session wrapped up early on a quota warning" — then marks the item `[x]`. The
  disclosure is honest and the residual risk is small (native `<details>` reflow is
  standard browser behaviour), but a checked box that contains its own exception is the
  rubber-stamping shape the review looks for.
- **Fix**: Open the list on a phone-width viewport, expand one badge, confirm the reflow
  is not disruptive, and amend the 3.6 note — or split 3.6 into a checked half and an
  unchecked half.
- **Decision**: FIXED — verified live rather than split. The page was rendered through the
  real view and template and loaded in Chrome at a true 390px viewport; the worst-case badge
  (combination product overlapping both a single and a cluster) was toggled with rects
  measured before and after. `scrollY` 0→0, `<h1>` top 151.93→151.93, badge top
  392.79→392.79, badge height 32→134, next `<li>` top 440.78→542.32: nothing above the badge
  moves and the badge's own top is fixed, so the whole +102px is downward growth below the
  tap point. Criterion met; plan note 3.6 amended with the measurements.
  **Nuance recorded:** with three long partner names the collapsed summary wraps to 2 lines
  at 390px, not the 1 line the earlier shorter-named check saw — still not "a paragraph", so
  the first clause holds, but the badge is not strictly single-line for realistic product
  names.
  (Login was done server-side via `force_login`, not by typing a password into the browser.)

## Notes on what passed

- **Architecture**: `pharmacy/duplicates.py` is genuinely set-keyed (`substance_keys` /
  `classify` never reference `Item`; only `build_list_view` does) and mirrors
  `registry/suggestions.py`'s pure-function shape. The module docstring records *why*,
  as Phase 1 criterion 1.6 required. The planned prescription-check slice can call
  `classify(substance_keys(candidate), …)` with no `Item` on either side.
- **The empty-set guard is real and load-bearing**: `classify` checks `not a or not b`
  before `a == b`, `build_list_view` additionally partitions unresolved items out, and
  both layers have tests. The recorded Phase 1 mutation (reordering the guard below the
  equality test) is the right falsification.
- **Query-shape contract holds**: `assertNumQueries(7)` passes on the original
  5-item test (which now exercises the cluster path, since all five share one substance),
  on a cluster+single+unresolved household, and on a partial-overlap household. Every
  read in `duplicates.py` and both new template partials goes through
  `.substance_links.all()`; no `.exists()`/`.filter()`/`.count()` was introduced.
- **Scope discipline**: nothing outside the plan's file list except two template partials
  (`_item_row.html`, `_partial_overlap_badge.html`), which are decomposition of the
  restructure the plan authorised, and the `roadmap.md` `in-progress` flip, which
  `/10x-implement` owns by design. The denylist was not re-implemented; no model,
  migration, dismiss action, sort/filter control, or strength caveat was added.
