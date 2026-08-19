<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: Add a Drug and See Its Active Substance(s) Resolved

- **Plan**: `context/changes/add-drug-with-substance-resolution/plan.md`
- **Scope**: Phases 1–4 of 4 (full plan)
- **Date**: 2026-08-14
- **Verdict**: NEEDS ATTENTION → **APPROVED** after triage (all findings resolved or
  consciously skipped; see "Verdicts after triage" below)
- **Findings**: 0 critical, 4 warnings, 3 observations
- **Triage**: 6 fixed (F1, F7, F2, F3, F4, F6), 1 skipped (F5)

Reviewed inline rather than via sub-agents (harness prohibits unrequested agent
spawning; the diff is 15 small files and was read directly).

## Verdicts (original, before triage)

| Dimension | Verdict |
|-----------|---------|
| Plan Adherence | WARNING |
| Scope Discipline | PASS |
| Safety & Quality | WARNING |
| Architecture | PASS |
| Pattern Consistency | WARNING |
| Success Criteria | WARNING |

## Verification run during this review

All automated criteria re-run from a clean tree:

| Check | Result |
|---|---|
| `uv run manage.py test` | **OK** — 124 tests |
| `uv run mypy` | **OK** — no issues in 52 source files (`pharmacy` is in `[tool.mypy] files`, so the four "type checking passes" boxes are real) |
| `uv run manage.py check` | **OK** — 0 issues |
| `uv run manage.py makemigrations --check --dry-run` | **OK** — no changes detected |
| `uv run manage.py collectstatic --dry-run --noinput` | **OK** — sees `autocomplete.js` |
| `uv run manage.py check --deploy` (DEBUG=False, real SECRET_KEY) | **OK** — exactly the two parked items (W004 HSTS, W008 SSL redirect). The 4 extra warnings under the local dev `.env` are DEBUG=True artifacts, not introduced by this slice. |

Mutation claim 2.3 verified empirically, not taken on trust: removing the
"prefer a row with substances" preference from `_default_product` was applied to
a scratch copy of `registry/suggestions.py` and made
`test_default_is_the_row_with_links_when_another_row_has_none` fail with
`AssertionError: 2 != 1`. File restored; working tree clean.

Every trap the plan named for itself was handled correctly:

- `Item.unresolved` reads `self.product.substance_links.all()`, **not** `.exists()`
  (`pharmacy/models.py:61`) — the spelling the plan flagged twice as obvious-and-wrong.
- No `innerHTML` or `eval` anywhere in `pharmacy/static/`; suggestions are built with
  `textContent` (`autocomplete.js:42`). The XSS guard over publisher-controlled
  registry names holds.
- The `registry_id` tiebreak is Python-side `min(key=…)` throughout, never mixed with a
  database-side `order_by('registry_id')` (`registry/suggestions.py:42`).
- `product` renders as `HiddenInput`, not a `Select` over 20,245 options
  (`pharmacy/forms.py:14`).
- `item_delete` is `@household_required` + `@require_POST` with a household-filtered
  lookup; the decorator order gives anonymous→redirect *and* member GET→405, and both
  are tested.
- `marketing_holder` renders iff `producer_confirmed` (`item_list.html:15`), with
  positive and negative tests.
- The list view's `assertNumQueries(7)` uses 5 items, so it discriminates the prefetched
  shape (7) from an N+1 regression (15).
- All six access-control references were **retargeted, not deleted**:
  `grep -c "pharmacy:item_list" households/tests/test_access_control.py` returns 6,
  matching criterion 1.6. (A dropped test would also have left the suite green.)
- `households.views.item_list` and its `path('list/', …)` are actually deleted; `/list/`
  is unchanged so `LOGIN_REDIRECT_URL` still resolves.
- `domowa_apteka/settings.py` changes `INSTALLED_APPS` only — no hardcoded setting, so
  the AGENTS.md env-var rule is not engaged.
- `registry` never imports `pharmacy`; the one-way dependency holds.
- Scope guardrails clean: no edit view, no expiration field, no duplicate comparison,
  no change to `registry`'s models/migrations/parser/loader, and `pharmacy/admin.py` is
  the untouched `startapp` stub.

## Re-verification after triage (2026-08-16)

Every automated check re-run after the five fixes landed — the table above was taken from
a clean tree and went stale the moment the code changed.

| Check | Result |
|---|---|
| `uv run manage.py test` | **OK** — 130 tests (was 124; +6 from this triage) |
| `uv run mypy` | **OK** — no issues in 52 source files |
| `uv run manage.py check` | **OK** — 0 issues |
| `uv run manage.py makemigrations --check --dry-run` | **OK** — no changes detected |

Both new guards were mutation-checked rather than trusted green (see F1 and F7
decisions). Dimension verdicts after triage:

| Dimension | After triage |
|---|---|
| Plan Adherence | PASS — F1, F7, F4 fixed |
| Scope Discipline | PASS (unchanged) |
| Safety & Quality | PASS — F2 fixed, but see the caveat below |
| Architecture | PASS (unchanged) |
| Pattern Consistency | WARNING — F5 consciously skipped |
| Success Criteria | PASS — F3 fixed; F6 fixed 2026-08-16 after the user confirmed 3.11 / 4.12 directly at ~375px. |

**One fix is verified by inspection only.** F2 changed `autocomplete.js`, and this repo has
no JavaScript test harness (`manage.py test` only — no vitest/playwright config), so the
`!response.ok` branch, `renderMessage`, and the `optionsOf` rescoping have no test behind
them. The other four fixes all gained tests. The `optionsOf` change deserves particular
note: it modified *working* keyboard-navigation code — `activateOption`, the keydown
handler, and both `attachKeyboardNav` call sites — as a side effect of making the message
row non-interactive. `querySelectorAll('[role="option"]')` is behaviourally identical to
`list.children` only because `makeOption` is the sole producer of rows in those lists and
`renderMessage` deliberately omits the role. That holds by inspection, but the 130 green
tests say nothing about it. A JS test harness is out of scope for this slice (Module 3
territory); flagged here so this is not read as equivalently verified to F1/F3/F4/F7.

## Findings

### F1 — Suggestion endpoint issues 31 queries per request where the plan specified two

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Plan Adherence / Safety & Quality (performance)
- **Location**: `registry/suggestions.py:88-99`
- **Detail**: The plan's "Performance Considerations" § 2 described the chosen shape as
  "**Two bounded queries**, so the database limits the work rather than Python."
  The implementation groups in SQL correctly, then hydrates in a **per-group loop**:
  one query for the keys, then for each of the ≤10 groups a `Product` query plus a
  two-query `prefetch_related`. Measured under `CaptureQueriesContext` with 10
  presentations: **31 queries** (1 + 3N), not 2.

  `measurements.md` records 20 ms worst case, which is real and well inside the 1-second
  NFR — but that is SQLite in-process on dev. Production is Postgres over a network,
  where 31 sequential statements each carry round-trip latency, and this endpoint fires
  on every debounced keystroke. The list view has an `assertNumQueries` guard; this
  endpoint, which runs far more often, has none, so the shape can worsen silently.
- **Fix A ⭐ Recommended**: Hydrate all chosen groups in one query — build a single `Q`
  over the ≤10 `(name, strength, form)` tuples, `prefetch_related` once, then group the
  rows in Python. Add an `assertNumQueries` test to `test_suggestions_endpoint.py`.
  - Strength: Restores the plan's stated two-bounded-query contract and makes cost
    independent of `limit`; 31 → 3 queries. The grouping keys are already in hand, so
    it is a rewrite of one loop, not a redesign.
  - Tradeoff: A `Q`-OR over 10 triples is a wordier query; `limit` must stay small for
    the OR to stay cheap (it is capped at 10 by default).
  - Confidence: HIGH — the fix is local to `search_presentations` and
    `registry/tests/test_suggestions.py` already pins the observable behaviour, so a
    regression would surface immediately.
  - Blind spot: Not measured against Postgres — the claim that 31 round trips cost more
    than 3 is inference from network latency, consistent with `lessons.md` on not
    stating cross-engine behaviour as measured fact.
- **Fix B**: Keep the loop, and add an `assertNumQueries` guard plus a note in
  `measurements.md` recording the 1+3N shape as accepted.
  - Strength: Zero behavioural risk; the measured latency already satisfies the NFR,
    and the guard stops the shape degrading unnoticed.
  - Tradeoff: Leaves a documented gap between the plan's contract and the code, and
    leaves the per-keystroke endpoint as the most query-heavy path in the app.
  - Confidence: MEDIUM — depends on Postgres round-trip latency nobody has measured.
  - Blind spot: Production `search_presentations` timing is unmeasured either way.
- **Decision**: FIXED via Fix A (2026-08-16) — `search_presentations` now hydrates all
  chosen groups in one `Q`-OR query with a single `prefetch_related`. Measured 31 → **4**
  queries (7 per HTTP request including the 3 auth queries), slowest sampled search 15.6 ms.
  Guarded by two tests in `pharmacy/tests/test_suggestions_endpoint.py`:
  `test_query_count_does_not_grow_with_the_number_of_groups` (the load-bearing property)
  and `test_query_count_is_bounded` (pins 7). Mutation-checked: restoring the per-group
  loop fails both with `34 != 7`. The absolute count was measured, not taken from this
  report's predicted "3" — the second prefetch level is skipped when no substance links
  exist, so the test fixture creates links deliberately.

### F7 — Producer list is not deduplicated by holder, reintroducing the flaw grouping exists to fix

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Plan Adherence
- **Location**: `registry/suggestions.py:48-51`
- **Detail**: `_build_presentation` emits **one `Producer` per row**, not per distinct
  holder. Confirmed against the real 20,245-product local database:

  ```
  Concor Cor 2,5 | 2,5 mg | rows: 28 | distinct holders: 8
  ```

  The producer picker therefore offers **28 options where only 8 are distinguishable**.
  Typing `del` narrows to four entries all reading `Delfarma`, with nothing to choose
  between them — which is precisely the flaw the presentation grouping was built to
  eliminate. The plan's own Key Discovery says a raw-row picker "would offer 28 visually
  identical options with nothing to choose between them." The design fixed that at the
  product level and reintroduced it one level down, inside the producer control.

  This is not merely cosmetic. Picking the first vs the third identical `Delfarma` entry
  stores a **different `product_id`**, and in the 201 groups (1.24%) whose rows disagree
  on substances those ids can resolve to different substance sets. A distinction the
  user cannot see becomes a substance set they did not knowingly choose.

  The plan contradicts itself here, which is why this slipped: the literal Phase 2 § 1
  contract ("a list of `(marketing_holder, product_id)` pairs for the group") permits
  duplicates, while every measurement and rationale around it assumes distinct holders —
  Phase 1 § 2 says "8 distinct holders across 28 rows", manual criterion 3.6 says
  "measured: 8 distinct holders across 28 rows", and the inline-payload sizing rests on
  "no group has more than 10 [producers]" and "~2 KB for 10 results". The contradiction
  was resolved silently in the permissive direction. `measurements.md:39-40` records the
  symptom as a success ("**28** producer rows across several distinct holders").
  Criterion 3.6 was ticked because the field *does* narrow — just to duplicates.

  This is the `lessons.md` rule "A plan can contradict itself; resolve it in code **and**
  write the resolution back" firing again, in its unresolved form.
- **Fix**: Emit one `Producer` per distinct `marketing_holder`, choosing the
  representative row with the existing tiebreak — apply `_default_product`'s rule
  (prefer a row with substance links, then lowest `registry_id`) within each holder's
  rows. This reuses the rule already written and tested rather than adding a second
  one, and brings the payload back inside the plan's ~2 KB / ≤10-producers estimate.
  Add a test for the `Concor Cor` shape asserting distinct holders, and correct the
  Phase 2 § 1 contract wording in `plan.md` so the next reader does not "fix" it back.
- **Decision**: FIXED (2026-08-16) — `_build_presentation` groups rows by
  `marketing_holder` and picks each holder's representative with the existing
  `_default_product` tiebreak, so there is still one tiebreak rule in the module.
  Verified against the real 20,247-product database: `Concor Cor 2,5` now offers **8**
  producers for 8 distinct holders (was 28), every one a distinct name with a unique
  `product_id`. Two tests added to `registry/tests/test_suggestions.py` (holder collapse,
  and that the representative uses the substance-link preference); both mutation-checked
  to fail when the dedup is reverted. `plan.md:401` contract wording corrected with a
  dated note explaining the self-contradiction, and `measurements.md:39` — which had
  recorded the symptom as a success — corrected likewise.

### F2 — Autocomplete dies silently when the endpoint returns non-JSON

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality (reliability)
- **Location**: `pharmacy/static/pharmacy/js/autocomplete.js:150-161`
- **Detail**: `fetchSuggestions` never checks `response.ok` or the content type. When a
  session expires, `household_required` returns a 302 to the login page; `fetch`
  follows it, receives HTML, `response.json()` throws a `SyntaxError`, and the `catch`
  re-throws it because `error.name !== 'AbortError'` — an unhandled promise rejection.
  The user keeps typing and no suggestion ever appears, with no message and no visible
  failure. Since picking a suggestion is the only way to add an item in v1, the add flow
  is fully blocked in a state that looks like the drug simply is not in the registry.
  The PRD guardrail is that a lookup failure is never silent.
- **Fix**: Guard the response before parsing — `if (!response.ok) { … }` — and on failure
  render a single non-clickable message row in `#suggestions` (e.g. asking the user to
  log in again) instead of re-throwing.
- **Decision**: FIXED (2026-08-16) — `fetchSuggestions` now checks `response.ok` before
  parsing and renders a message row via a new `renderMessage`; the `catch` renders a
  connection-failure message instead of re-throwing, keeping the stale-response sequence
  guard on both paths. One thing the stated fix did not cover and was handled anyway:
  `attachKeyboardNav` iterated `list.children`, so arrow keys would have landed on the
  message row and Enter would have dispatched a `mousedown` with no listener. Navigation
  is now scoped to `[role="option"]` (set only by `makeOption`), which makes the message
  row genuinely non-interactive rather than merely unclickable by mouse.

### F3 — The `producer_confirmed` value the browser actually sends is untested

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Success Criteria (test coverage)
- **Location**: `pharmacy/tests/test_item_add.py:117`
- **Detail**: `autocomplete.js` always submits the literal string `'true'` or `'false'`
  (lines 31, 95, 122, 130, 179) — it never omits the field. The only test covering the
  false path, `test_omitting_producer_confirmed_stores_false`, omits it entirely, which
  is a path the browser never takes.

  Probed directly against Django 5.2.16: `forms.BooleanField(required=False).clean('false')`
  returns `False`, because `BooleanField.to_python` special-cases the strings `'false'`
  and `'0'`. **The code is correct today.** But that correctness rests entirely on an
  undocumented framework nicety with no test behind it. If the field or widget were ever
  changed, `'false'` would become truthy, every unconfirmed item would render the
  tiebreak default producer as fact — precisely the flaw `producer_confirmed` exists to
  prevent, in the 6.2% of groups where the field matters most — and the suite would stay
  green.
- **Fix**: Add a test posting `{'product': p.id, 'producer_confirmed': 'false'}` and
  asserting the stored value is `False`, alongside the existing omission test.
- **Decision**: FIXED (2026-08-16) — `test_posting_producer_confirmed_false_stores_false`
  added to `pharmacy/tests/test_item_add.py`, alongside (not replacing) the existing
  omission test: omission is still a valid HTTP shape even though the browser never
  produces it. The comment records that the test passes only because
  `BooleanField.to_python` special-cases `'false'`/`'0'`, so the dependency is documented
  rather than implicit.

### F4 — `product_suggestions` is not method-restricted despite a GET-only contract

- **Severity**: 📝 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Adherence
- **Location**: `pharmacy/views.py:33-34`
- **Detail**: Plan Phase 2 § 3 specifies the endpoint as "`household_required`, GET-only".
  The view carries `household_required` but no `require_GET`, so a POST is served
  identically. Harmless in itself — the view only reads `request.GET` and mutates
  nothing — but it is a stated contract left unenforced, and `item_delete` in the same
  module does use `require_POST`, so the codebase is inconsistent with itself.
- **Fix**: Add `@require_GET` beneath `@household_required`, matching `item_delete`'s
  decorator ordering.
- **Decision**: FIXED (2026-08-16) — `@require_GET` added beneath `@household_required`,
  matching `item_delete`'s ordering. `test_post_is_rejected` added asserting 405.

### F5 — `_household_of` duplicated verbatim across two apps

- **Severity**: 📝 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency
- **Location**: `pharmacy/views.py:18-21`, `households/views.py:21-28`
- **Detail**: The private helper is copied byte-for-byte into `pharmacy`. The plan said
  to resolve the household "the same way `households/views.py:21` does", which reads
  either way, so this is not drift. It is fine at two call sites; it becomes a genuine
  duplication problem at the third app, and `households` already owns `decorators.py`
  as the natural home for it.
- **Fix**: Move it to `households/decorators.py` (or a new `households/scoping.py`) as a
  public helper and import it from both views modules.
- **Decision**: SKIPPED (2026-08-16) — conscious call: two call sites do not yet justify
  the shared module, and the finding itself notes this is not drift. Revisit when a third
  app needs household scoping, at which point the extraction becomes worth its churn.

### F6 — Plan closed out as `implemented` with two manual criteria still open

- **Severity**: 📝 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Success Criteria
- **Location**: `context/changes/add-drug-with-substance-resolution/plan.md:929,950`
- **Detail**: Criteria 3.11 and 4.12 (phone-width usability) are `- [ ]`, and `change.md`
  was stamped `status: implemented` and closed out by the epilogue commit `df7fd00`
  anyway. The disclosure itself is exemplary — the Progress notes and `measurements.md`
  both state plainly that `resize_window` reported success while `window.innerWidth`
  never left the desktop size, and explicitly label the favourable code-level signals
  (Pico is fluid, `base.html` has a correct `width=device-width` meta, no fixed-width
  elements) as inference rather than measurement. That is exactly the standard
  `lessons.md` asks for. The gap is only that "implemented" now reads as complete to
  `/10x-archive` and `/10x-status`, which do not see the two open boxes.
- **Fix**: Open the add flow at 375px in browser devtools (or on a phone), tick 3.11 and
  4.12, and note the result in `measurements.md`. It is a two-minute check that no
  tooling in this environment could perform.
- **Decision**: FIXED (2026-08-16) — user performed the 375px check directly against the
  running dev server and confirmed the add flow, suggestion list, and producer picker are
  usable, and the full search → pick → save → list → delete flow works end to end at that
  width. `plan.md` 3.11 and 4.12 ticked with the confirmation date; `measurements.md`
  updated with the result. This was a real narrow-viewport observation, not a repeat of
  the `resize_window` inference this finding flagged.
