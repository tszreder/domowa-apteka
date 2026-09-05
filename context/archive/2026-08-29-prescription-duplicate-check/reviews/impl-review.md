<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: Prescription Duplicate Check

- **Plan**: `context/changes/prescription-duplicate-check/plan.md`
- **Scope**: Phases 1-3 of 3 (full plan)
- **Date**: 2026-09-05
- **Verdict**: NEEDS ATTENTION
- **Findings**: 0 critical, 3 warnings, 5 observations

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| Plan Adherence | PASS |
| Scope Discipline | WARNING |
| Safety & Quality | WARNING |
| Architecture | PASS |
| Pattern Consistency | PASS |
| Success Criteria | WARNING |

## Success criteria — measured

All automated gates re-run against the working tree at review time:

| Command | Result |
|---|---|
| `uv run manage.py check` | PASS — no issues |
| `uv run manage.py test` | PASS — 220 tests, OK (94.9 s) |
| `uv run mypy .` | PASS — 64 source files, no issues |
| `uv run manage.py collectstatic --noinput` | PASS — 132 post-processed |

Every Progress checkbox (1.1-1.6, 2.1-2.9, 3.1-3.9) is `[x]`. The manual rows carry
observable evidence: `.playwright-mcp/` holds browser console and page dumps dated
2026-08-29/30, and commit `3795b15` is a defect found *by* the Phase 3 add-flow sweep —
manual verification demonstrably happened rather than being rubber-stamped. See F1 for
what that commit did not write back.

## Plan adherence — summary

Every planned change landed, including both mid-implementation amendment blocks in
Phase 2 §4. Two deviations from the plan's literal text, both documented in the code and
both improvements:

- The candidate's `prefetch_related('substance_links__substance')` sits on
  `ProductCheckForm`'s queryset (`pharmacy/forms.py:190`) rather than in the view, because
  `ModelChoiceField` is what issues the lookup — prefetching in the view would fetch the
  row twice.
- The query-shape test uses `CaptureQueriesContext` + a `_measure()` helper
  (`pharmacy/tests/test_product_check.py:424`) rather than `assertNumQueries`, so the
  N+1 guard actually observes household size instead of asserting a literal twice. This is
  strictly stronger than what the plan specified.

Every "What We're NOT Doing" boundary holds except one — see F1. No migrations, no model
changes, no writes reachable from `product_check`, and `classify` / `substance_keys` /
`build_list_view` are byte-identical to `main` apart from the module docstring.

## Findings

### F1 — Commit `3795b15` changed add-flow behaviour and overran the CSS budget without a plan write-back

- **Severity**: ⚠️ WARNING
- **Impact**: 🔬 HIGH — architectural stakes; think carefully before deciding
- **Dimension**: Scope Discipline
- **Location**: `pharmacy/static/pharmacy/js/autocomplete.js:106-109`, `static/css/app.css:63-110`
- **Detail**:
  The plan's "What We're NOT Doing" states **"No changes to the add flow's behaviour.
  Phase 3 moves code; it does not change what the add screen does."** Phase 3 (`81d9235`)
  honoured that precisely — the extraction is verbatim. The follow-up commit `3795b15`
  then added a producer `focus` listener that renders the full holder list on focus, which
  is new add-screen behaviour, and 48 lines of picker CSS (`.suggestions`, `.active`,
  `.suggestion-message`, `.form-error`) against a Phase 2 §6 budget that reads
  **"At most a `.check-matches` list rule … Skip entirely if unstyled markup reads
  acceptably."**

  Both fixes are correct on the merits and unusually well-evidenced in the commit body
  (measured before and after, and deliberately held out of the p3 commit so that one stays
  a pure move). The defects are genuinely pre-existing: the `active` class has always been
  toggled by `attachKeyboardNav` and never had a rule, and Pico is classless, so keyboard
  navigation worked while looking broken on `main` too.

  The problem is that the plan of record still reads as though neither happened. Phase 2 §4
  already models the correct treatment twice — an inline amendment block saying what shipped
  and why. `context/foundation/lessons.md` carries an accepted rule for exactly this: *"When
  implementation finds that two parts of a plan cannot both hold, resolving it in code is
  only half the work. Edit the plan section that is now wrong in the same change … a commit
  message and a docstring do not reach the next reader of the plan."* The next reader of
  §6 will be misled about what the CSS budget was.
- **Fix A ⭐ Recommended**: Append amendment blocks to Phase 2 §6 and Phase 3 §2 recording what `3795b15` changed and why, in the same shape as Phase 2 §4's existing two.
  - Strength: Matches the pattern this very plan already established, and the information
    already exists in the commit body — it just needs to reach the plan. Keeps two real
    usability fixes.
  - Tradeoff: The plan becomes a slightly moving target; the NOT-doing line ends up
    qualified rather than clean.
  - Confidence: HIGH — Phase 2 §4 is a working precedent in this same file, and
    `lessons.md` names the rule.
  - Blind spot: Does not settle whether the producer focus listener is the right UX; it
    only records that it happened.
- **Fix B**: Revert the producer `focus` listener out of this change and re-land it as its own change; keep only the CSS (amended into §6).
  - Strength: Leaves "no changes to the add flow's behaviour" literally true, and gives an
    unverifiable-by-CI behaviour change its own review.
  - Tradeoff: Loses a real usability fix from this slice and costs a second change folder;
    the CSS still needs the §6 amendment either way.
  - Confidence: MEDIUM — the listener is 4 lines and trivially revertible, but no automated
    test covers the add flow, so re-landing it carries the same verification cost again.
  - Blind spot: Have not checked whether the manual sweep rows 3.6-3.9 were signed off
    before or after the listener landed.
- **Decision**: FIXED (Fix A) — amendment blocks appended to Phase 2 §6 and Phase 3 §2 of `plan.md`.

### F2 — The uncomparable-suppression tests assert the absence of a string nothing produces

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Success Criteria
- **Location**: `pharmacy/tests/test_product_check.py:42`, `:314`, `:325`
- **Detail**:
  `UNCOMPARABLE = 'Leków w domu bez ustalonej substancji czynnej:'` appears nowhere in the
  codebase except its own definition — verified by grep across `pharmacy/` and `static/`.
  Both `assertNotContains(response, UNCOMPARABLE)` calls therefore pass unconditionally.

  `ProductCheckUncomparableSuppressionTests`'s docstring claims these tests exist "so that
  removal stays a decision someone made, not something a later edit reintroduces or drops
  by accident", and the Phase 2 §4 amendment repeats the claim. They cannot do that: they
  would pass with `uncomparable_count` deleted from `CandidateCheck` entirely, and would
  also pass if the disclosure were reintroduced with any other wording. Neither test asserts
  that its fixture actually produces an uncomparable item, so the precondition is unpinned
  too. The paired `assertContains(NO_MATCH)` / `assertContains(TOTAL_REFUSAL)` halves are
  real, so the tests are not worthless — just not the tests they say they are.
- **Fix**: In both tests, assert the precondition on context — `self.assertEqual(response.context['check'].uncomparable_count, 1)` — and pin the decision against the template source rather than a guessed sentence, e.g. asserting `'uncomparable_count'` does not appear in `product_check.html`. Then delete the `UNCOMPARABLE` constant.
- **Decision**: FIXED — precondition assertions added to both tests; the removal is now pinned by a new `test_uncomparable_count_is_not_wired_into_an_active_template_tag`, which reads `product_check.html`, strips `{% comment %}` blocks (the field name is still named inside the explanatory comment, so a plain `assertNotContains`/substring check on the raw source would false-positive), and asserts the identifier is absent from what remains. Verified the new test actually fails when the field is wired into a live tag, then reverted the mutation. `UNCOMPARABLE` constant deleted.

### F3 — `plural_pl`'s defensive guard does not cover what its docstring promises

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: `pharmacy/templatetags/polish.py:30`, `:34`, `:36-39`
- **Detail**:
  The Polish three-form rule itself is **correct** — verified against 0, 1, 2, 4, 5, 11-15,
  21, 22, 25, 101, 102, 111, 112, 114, 121, 122 and negatives; all inflect correctly,
  including the teens exception.

  The guard around it does not hold. The comment at `:31-33` says "an unusable value falls
  back rather than 500-ing the page". Measured in this repo:

  - `plural_pl(Decimal('2'), …)` returns the **"many"** form. `Decimal` is outside the
    `isinstance(count, (int, float, str))` whitelist at `:34`, so a wrong inflection is
    returned silently, with no signal.
  - `plural_pl(float('inf'), …)` raises **`OverflowError`** — `except ValueError` at `:36`
    does not catch it. That is a 500, which is exactly what the comment says cannot happen.
  - `one, few, many = forms.split(',')` at `:30` runs *before* the guard, so
    `plural_pl(2, 'a,b')` raises **`ValueError`**. The guard protects the count argument;
    the template-author typo the docstring names is in the *other* argument.

  All three are latent today: the sole call site passes an `int` `pack_count` and a literal
  three-form string. `test_polish_filters.py` cannot see any of them — it also never covers
  negatives (delete `abs()` at `:37` and nothing goes red) or numeric strings (remove `str`
  from the whitelist and nothing goes red), both of which are deliberate decisions in the
  code.
- **Fix**: Drop the isinstance whitelist and lean on the `try:` block the way Django's own `pluralize` does (`int(Decimal('2'))` already works); widen the catch to `except (TypeError, ValueError, OverflowError)`; and validate the form spec before unpacking (`parts = forms.split(','); if len(parts) != 3: return forms`). Add test cases for `Decimal`, a negative, and a numeric string so the existing decisions are pinned.
- **Decision**: FIXED — `pharmacy/templatetags/polish.py` rewritten as described; `mypy` needed `# type: ignore[call-overload]` on the widened `int(count)` call (not `[arg-type]` — checked against the actual mypy error code). Added 6 test cases (`Decimal`, overflow, negative, numeric string, malformed form-spec) to `test_polish_filters.py`, all pass; `uv run mypy .` clean (64 files); manually verified all three previously-broken inputs (`Decimal('2')`, `float('inf')`, a 2-form spec) no longer crash or misclassify.

### F4 — The within-tier newest-first ordering is documented but untested

- **Severity**: 📝 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Success Criteria
- **Location**: `pharmacy/duplicates.py:364`
- **Detail**: The comment states that the sort is stable "so `Item.Meta.ordering`
  (`-added_at`) survives inside each tier for free — the same property `build_list_view`
  relies on." Nothing tests it.
  `test_matches_are_ordered_strongest_first` places one match in each of the three tiers, so
  it pins cross-tier order only. Replace the key with
  `(_MATCH_ORDER.index(kind), match.product.name)` — destroying the documented property —
  and the whole suite stays green.
- **Fix**: One test with two `SHARED_SUBSTANCE` products added at different times, asserting the newer product's match comes first.
- **Decision**: FIXED — `test_within_tier_order_is_newest_first` added to `CheckCandidateTests` in `pharmacy/tests/test_duplicates.py`, following `test_item_list.py`'s established `.update(added_at=...)` pattern for spreading `auto_now_add` timestamps. Verified it fails when the sort key is changed to `(_MATCH_ORDER.index(match.kind), match.product.name)` (the exact mutation the finding named), then reverted the mutation; full `CheckCandidateTests` class stays green.

### F5 — `check.js` leaves the suggestion list painted during navigation

- **Severity**: 📝 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency
- **Location**: `pharmacy/static/pharmacy/js/check.js:23-30`
- **Detail**: `onPick` sets `searchInput.value` then navigates, but never calls
  `clearList(suggestionsList)`. The add screen's `pickPresentation` does
  (`autocomplete.js:64`) — that call stayed in screen-specific code when the module was
  extracted, and the check screen never got its own. The dropdown therefore stays open over
  the page for the whole navigation.
- **Fix**: Add `clearList(suggestionsList)` in `onPick` before setting `window.location`, destructuring `clearList` from `window.ProductSearch` alongside the other two.
- **Decision**: FIXED — `check.js` now destructures `clearList` from `window.ProductSearch` and calls it before setting `window.location`. Confirmed `clearList` is exported (`product-search.js:181`). No automated test exists for this — the plan's own "No JS test toolchain" boundary (`test-plan.md` §3 Phase 4) — so this is unverified beyond a source-level read; `manage.py test`/`collectstatic` re-run clean.

### F6 — An out-of-range `?product=` id may 500 on Postgres rather than render the message

- **Severity**: 📝 OBSERVATION
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality
- **Location**: `pharmacy/views.py:116-119`
- **Detail**: **Unverified, and pre-existing rather than introduced here.** The view's
  docstring promises that a bad `?product=` id "is a message, not a 404". Django 5.2's
  `ModelChoiceField.to_python` catches only `(ValueError, TypeError, DoesNotExist)` —
  confirmed by reading the installed source. An id larger than a Postgres `integer` would
  surface as a psycopg `DataError`, which escapes as a 500. Production is Postgres
  (`psycopg[binary]` in `pyproject.toml`, `DATABASE_URL` via `dj_database_url`); dev is
  SQLite, which cannot reproduce it. The same shape already exists in `ItemAddForm` and
  `item_delete`, so this is not a regression from this slice.
- **Fix**: One `curl` against the deployed app with `?product=99999999999999999999` to settle whether psycopg3 raises or simply matches nothing. Only if it raises does this need a guard — and then it belongs in a shared place, not just this view.
- **Decision**: PENDING

### F7 — `/check/?product=` with an empty value shows a required-field error, not the search screen

- **Severity**: 📝 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: `pharmacy/views.py:124`
- **Detail**: `form = ProductCheckForm(request.GET) if 'product' in request.GET else None`
  keys on the parameter's *presence*, so `?product=` (present but empty) binds and fails
  required-validation, rendering Django's "To pole jest wymagane." — Polish, since
  `LANGUAGE_CODE = 'pl'`, so it is not broken, just a different answer than the plan's
  invalid-product wording. Arguably indistinguishable from "no parameter" and should render
  the bare search screen. Untested either way.
- **Fix**: Key on truthiness — `if request.GET.get('product')` — so an empty value falls through to the search screen, and add a test for it.
- **Decision**: FIXED — `pharmacy/views.py:124` now keys on `request.GET.get('product')`; comment updated to describe both the absent and empty cases. Added `test_empty_product_parameter_renders_the_search_screen_not_a_required_field_error` to `ProductCheckResultStateTests`. Verified it fails against the original `'product' in request.GET` guard, then confirmed it passes with the fix; full `test_product_check` module (26 tests) green.

### F8 — `.playwright-mcp/` is untracked and absent from `.gitignore`

- **Severity**: 📝 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: repo root
- **Detail**: 20+ browser console and page-snapshot dumps dated 2026-08-29/30, left over
  from the manual verification behind `3795b15`. Not committed, but one `git add .` away
  from being so. `staticfiles/` is already gitignored; this is not.
- **Fix**: Add `.playwright-mcp/` to `.gitignore` and delete the directory.
- **Decision**: FIXED (partial) — `.playwright-mcp/` added to `.gitignore` (new "Browser automation output" section). Confirmed with the user first that this ignores only generated console-log/page-snapshot output, not the Playwright MCP tool itself. The directory's contents were **not** deleted: this review ran as a background job in an isolated worktree, and `.playwright-mcp/` lives in the main checkout outside it — Bash refused the `rm -rf` as a destructive op on the shared checkout. Harmless either way now that it's gitignored; delete `.playwright-mcp/` at the repo root by hand if you want it gone.
- **Verified by**: N/A — no automated check applies to a `.gitignore` entry beyond re-running `git status` after merge to confirm the directory no longer shows as untracked.
