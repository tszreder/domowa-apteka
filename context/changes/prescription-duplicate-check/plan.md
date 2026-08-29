# Prescription Duplicate Check Implementation Plan

## Overview

Give an adult standing in a doctor's office a read-only screen that compares one
candidate product — the one just prescribed, or a proposed alternative — against
everything the household already has at home, and states whether anything there
shares its active substances. Nothing is written to the household list as a side
effect of asking.

This is roadmap slice `S-05`, the third surface for a rule the PRD already states
in §Business Logic (FR-003). It introduces no new comparison rule:
`pharmacy/duplicates.py` was deliberately written set-keyed for exactly this slice.

## Current State Analysis

**The rule already exists and needs no change.** `pharmacy/duplicates.py:33`
exposes `substance_keys(product: Product) -> frozenset[str]` and
`classify(a: frozenset[str], b: frozenset[str]) -> Overlap`. The module docstring
names this slice as the reason it was written that way: "a candidate registry
`Product` the household does not own … has no `Item` to pair against, so the rule
deciding 'are these duplicates' must not assume an `Item` exists on either side."

**What does not exist** is the aggregation. `build_list_view` is item-to-item: it
partitions a household's items into `DuplicateGroup`s and cross-annotates them.
Comparing *one candidate product* against *N household items* is a different shape
and needs a new function in the same module.

**The search stack is complete and reusable.**
`registry/suggestions.py:search_presentations` groups active products into pickable
presentations and applies the default-product tiebreak;
`pharmacy/views.py:product_suggestions` serves it as JSON at `/suggestions/`;
`pharmacy/static/pharmacy/js/autocomplete.js` drives the picker. That JS is currently
hardwired to the add screen's DOM: `clearSelection()` dereferences
`producerConfirmedField`, `producerField`, `producerSearchInput` and
`producerSuggestionsList` unconditionally, and two module-level listeners are attached
to `producerSearchInput`. Reuse on a screen with no producer step therefore requires
an extraction, not a second `<script>` tag.

**Two silent-guess traps are live in this design.** Both are inversions of the PRD's
strongest NFR (the app never guesses; an unverifiable entry is surfaced as such rather
than shown as fact):

1. A candidate product with zero substance links makes `classify` return `NONE`
   against every household item. A naive screen renders "no match" — which reads as a
   buy signal for a product we simply failed to resolve.
2. Household items whose own products are unresolved also classify as `NONE`, so they
   vanish from the result. A "nothing at home matches" verdict computed over a
   household that contains unresolved items overstates what we know.

**But identity is not a substance inference, and must not be suppressed with one.**
Whether a household item *is the same registry product* as the candidate is settled by
`Item.product_id == candidate.pk` — a primary-key equality over rows the registry
itself keyed, with stronger provenance than any substance set. It holds whether or not
either side resolved. So the unresolved-candidate case is not a total refusal: the
screen can still confirm "you already have exactly this product at home", and refuses
only the part it genuinely cannot answer — whether the household holds a *substitute*.
Suppressing a known fact because a different, weaker fact is missing is its own kind
of wrong answer.

**Testing baseline.** `manage.py test` (Django's built-in runner; no pytest), mypy +
django-stubs in CI. `assertNumQueries` is `test-plan.md` §4's chosen instrument for
the one-second acknowledgement NFR, and `pharmacy/tests/test_item_list.py:129` already
pins the list view's prefetch contract at 7 queries (4 request plumbing + 3 data).
There is **no e2e layer** — `test-plan.md` §4 records `e2e: none yet — see Phase 4` —
so no automated test in this repo can observe JavaScript behaviour.

## Desired End State

An authenticated household member can reach `Sprawdź lek` from the household list,
type a product name, pick a suggestion, and immediately see a flat, strongest-first
list of what the household already holds that shares the candidate's active
substances — each row labelled with how strongly it matches, showing the product's
name, strength and form, its pack count, and (for partial matches only) which
substances are shared.

When the candidate's substances cannot be established, the screen still answers the
identity question — "you already have exactly this at home", with its pack count — and
refuses only the substitute question, saying why. If the household does not hold that
exact product either, the screen refuses outright rather than reporting "no match".
When the household holds items whose own substances are unresolved, the screen
discloses that they were not compared.

Verified by: the integration tests in Phase 2 covering every result state; a test
asserting no `Item` row count changes across a check; and manual use of the flow on a
phone-width viewport.

### Key Discoveries:

- `pharmacy/duplicates.py:33` and `:48` — `substance_keys` and `classify` are
  candidate-ready; the new function composes them and must not restate the rule.
- `pharmacy/duplicates.py:141` — `build_list_view` sorts shared substances by display
  name with an explicit comment: `frozenset[str]` iterates in string-hash order, which
  Python randomises per process. Any new code emitting shared substance names must sort
  for the same reason.
- `registry/suggestions.py:82` — `search_presentations`'s docstring records that
  **1.24% of presentation groups have rows that disagree on substances**. This slice
  picks at presentation level with no producer step (decided), so in that 1.24% the
  comparison runs on `_default_product`'s substances. Mitigated by displaying the
  substances used, not by a producer step.
- `pharmacy/models.py:60` — `Item.unresolved` must read `.all()`, not `.exists()`, or
  it bypasses the prefetch cache and issues a query per item.
- `pharmacy/models.py` — one `Item` is one physical box, so "pack count" is a count of
  `Item` rows for a product and needs no new field.
- `pharmacy/forms.py:19` — `ItemAddForm`'s `invalid_choice` copy is
  `'Ten produkt nie jest już dostępny w rejestrze.'`; the check screen reuses it for a
  stale `?product=` id rather than inventing a second wording.
- `pharmacy/tests/test_item_list.py:124-129` — the established `assertNumQueries`
  comment style: state which queries are plumbing and which are the N+1 guard.
- `context/foundation/roadmap.md` §S-05 — the framing risk: "a screen that says 'you
  already have this' sits one wording away from saying 'so you do not need that
  prescription'."

## What We're NOT Doing

- **No producer/holder disambiguation step on the check screen** (decided). The
  comparison uses the presentation's default product.
- **No persistence of any kind.** No `CheckLog` model, no migration, no session
  history. The screen is a `GET` that writes nothing.
- **No expiration date.** `S-04` is parked. Phase 1 keeps `CandidateMatch.items` as
  the seam so an expiry column can be added later without a signature change, but no
  date is stored, read, or rendered here.
- **No therapeutic-effect matching.** Explicitly out of MVP scope (roadmap §Parked,
  2026-08-29). Substance-set identity only.
- **No changes to the duplicate rule itself** — `classify`, `substance_keys` and
  `build_list_view` are read, not edited.
- **No JS test toolchain.** Adding one is `test-plan.md` §3 Phase 4's business.
- **No changes to the add flow's behaviour.** Phase 3 moves code; it does not change
  what the add screen does.
- **No layout redesign of the household list.** `S-06` owns that; this slice adds one
  link.

## Implementation Approach

Three phases, ordered so that risk decreases monotonically:

1. **The rule, alone.** A pure function over a `Product` and an iterable of `Item`s,
   unit-tested with no HTTP and no template. Composes the existing primitives.
2. **The screen, without JavaScript.** A `GET` view keyed on `?product=<id>` plus a
   template. Because the screen is fully driveable by URL, every result state, both
   refusals, the no-write guarantee and the query shape are asserted here with the
   Django test client — the only layer this project's test stack actually has.
3. **The shared picker.** Extract the machinery out of `autocomplete.js`, rewire the
   add screen onto it, add a small `check.js` that navigates on pick.

Phase 3 is last because it is the only phase whose correctness CI cannot observe. By
the time it runs, the feature already works; if manual verification of the add flow
shows any regression, Phase 3 is droppable without losing the slice.

## Critical Implementation Details

**Polish plural agreement is a trap in the copy.** Polish uses three plural forms
(`1 opakowanie`, `2–4 opakowania`, `5+ opakowań`) and Django's `pluralize` filter
handles two. No i18n locale files exist in this project. Every count in this screen's
copy is therefore phrased as a label followed by a number (`Liczba opakowań: 3`),
which agrees for every value and needs no plural logic.

**Ordering must not come from a set.** Match tiers are assigned from `classify`'s
result, then the list is stable-sorted by tier. Because the input `items` arrive in
`Item.Meta.ordering` (`-added_at`) and Python's `sorted` is stable, newest-first
survives the tier sort for free — the same property `build_list_view` relies on.
Shared substance names must be explicitly sorted by display name; iterating the
intersection `frozenset` directly gives per-process-random order.

**Deferred scripts run in document order.** Phase 3's split depends on
`product-search.js` executing before `autocomplete.js` / `check.js`. Both carry
`defer`, and the HTML spec executes deferred scripts in document order, so tag order
in the template is the whole mechanism — which is why Phase 3 asserts that order in a
template test.

---

## Phase 1: The candidate-vs-household rule

### Overview

Add one pure function to `pharmacy/duplicates.py` that compares a candidate `Product`
against a household's `Item`s and returns a render-ready result, plus its unit tests.
No view, no template, no URL.

### Changes Required:

#### 1. The comparison function and its result types

**File**: `pharmacy/duplicates.py`

**Intent**: Aggregate the existing set-keyed rule into a one-candidate-against-many-items
answer, splitting the `FULL` result into "the household owns this exact product" and
"the household owns a different product with the same substances", because those are
different facts to someone deciding whether to fill a prescription. Answer the identity
question from primary keys rather than from substance sets, so it survives a resolution
failure. Carry enough with each match to render a row without the template re-querying,
and carry the count of household items that could not be compared at all.

**Contract**: A `MatchKind` enum (`SAME_PRODUCT`, `SAME_SUBSTANCES`,
`SHARED_SUBSTANCE`), a frozen `CandidateMatch` dataclass, a frozen `CandidateCheck`
dataclass, and `check_candidate(candidate: Product, items: Iterable[Item]) -> CandidateCheck`.

- `CandidateMatch` carries `product: Product`, `kind: MatchKind`, `shared: list[str]`
  (display names, sorted by display name; only meaningful for `SHARED_SUBSTANCE`), and
  `items: list[Item]` in caller order. `pack_count` is a property returning
  `len(items)` — one `Item` is one box, so there is no second source of truth. `items`
  is the deliberate seam for `S-04`: when an expiry field lands, the row reads dates
  off it with no signature change.
- `CandidateMatch` also exposes `is_same_product` / `is_same_substances` /
  `is_shared_substance` boolean properties. The enum is the value tests assert on; the
  booleans exist so the template needs no enum in its context, matching how
  `DuplicateGroup.same_product` already serves `item_list.html`.
- `CandidateCheck` carries `candidate_substances: list[str]` (display names of the
  substances the comparison actually used, sorted by display name),
  `matches: list[CandidateMatch]`, and `uncomparable_count: int`. `resolved` is a
  property returning `bool(candidate_substances)`.
- **`SAME_PRODUCT` is decided by identity, before and independently of any substance
  comparison** — `item.product_id == candidate.pk`, nothing else. It is therefore
  emitted whether or not either side resolved, which is what lets an unresolved
  candidate still answer "you already have exactly this at home". A `SAME_PRODUCT`
  match carries an empty `shared` list; the substances are identical by definition when
  they exist at all, so there is nothing to name.
- Every *other* relationship goes through `substance_keys` and `classify` — the
  function must not compare sets directly. When the candidate's key set is empty,
  `candidate_substances` and `uncomparable_count` are still populated but the only
  matches possible are `SAME_PRODUCT` ones; the caller distinguishes the two refusal
  shapes from `resolved` and whether `matches` is empty.
- Items are grouped by `product_id` preserving first-seen order, the identity test runs
  first, the remaining groups take their tier from `classify`, and the result is
  stable-sorted by tier.
- `uncomparable_count` counts items whose own `substance_keys` are empty, so the screen
  can disclose that they were not compared rather than let a "nothing matches" verdict
  silently include them. It is computed the same way regardless of whether the candidate
  resolved; the template decides when it is worth showing (see Phase 2 § 4).
- The function reads `product.substance_links.all()` only via `substance_keys`, so the
  caller's prefetch is honoured and no query is issued per item.

Docstrings follow this module's established density: say *why* a rule exists and what
it must hold against, not what the code does.

#### 2. Unit tests for the rule

**File**: `pharmacy/tests/test_duplicates.py`

**Intent**: Prove the aggregation against sets derived from how each fixture was built,
never snapshotted from the function's own output — the anti-pattern the module
docstring already names and `test-plan.md` §2 risk #3 forbids.

**Contract**: A new `CheckCandidateTests(TestCase)` class reusing the module's existing
`make_product` helper, covering at minimum:

- candidate with no substance links, **not** held by the household → `resolved` is
  `False` and `matches` is empty, even when the household holds a *differently-keyed*
  product with a similar name (a name collision is not identity);
- **candidate with no substance links that the household does hold → `resolved` is
  `False` but `matches` carries exactly one `SAME_PRODUCT` entry with the right
  `pack_count`.** This is the test that pins identity as independent of resolution;
  falsify it by making the identity test depend on a non-empty key set and watch it go
  red;
- the household owns the identical `Product` (resolved) → one match, `SAME_PRODUCT`,
  and its `shared` list is empty;
- the household owns a *different* product with an identical substance set → one match,
  `SAME_SUBSTANCES`, not `SAME_PRODUCT`;
- a combination candidate against a single-substance item → `SHARED_SUBSTANCE` with
  `shared` naming exactly the intersection;
- a disjoint household item produces no match at all;
- household items with no substance links are absent from `matches` **and** counted in
  `uncomparable_count` — except one that is the candidate's own product, which appears
  as `SAME_PRODUCT`;
- three boxes of one product collapse to one match with `pack_count == 3`;
- ordering: with all three tiers present, `matches` is ordered `SAME_PRODUCT` →
  `SAME_SUBSTANCES` → `SHARED_SUBSTANCE`;
- `shared` is ordered by display name, asserted on a pair whose alphabetical order
  differs from insertion order (mirrors the existing
  `test_shared_substances_are_ordered_alphabetically_not_by_set_iteration`).

### Success Criteria:

#### Automated Verification:

- Unit tests pass: `uv run manage.py test pharmacy.tests.test_duplicates`
- Full suite passes: `uv run manage.py test`
- Type checking passes: `uv run mypy .`
- Django system checks pass: `uv run manage.py check`

#### Manual Verification:

- Read the new docstrings against the module's existing ones: each says why the rule
  exists and what it must hold against, not what the code does.
- Confirm `check_candidate` contains no direct set comparison — every relationship goes
  through `classify`.

**Implementation Note**: After completing this phase and all automated verification
passes, pause here for manual confirmation from the human before proceeding.

---

## Phase 2: The check screen

### Overview

A `GET`-only view at `/check/`, its template and copy, and the entry link from the
household list. Driveable entirely by URL, so this phase carries the slice's full
integration coverage.

### Changes Required:

#### 1. The view

**File**: `pharmacy/views.py`

**Intent**: Resolve the `?product=<id>` query parameter to an active registry product,
run `check_candidate` against the caller's household items, and render. Reject nothing
with a 404 — a stale bookmark to a product the registry has since deactivated is a
message, not an error page.

**Contract**: `product_check(request: HttpRequest) -> HttpResponse`, decorated
`@household_required` then `@require_GET` (same order as `product_suggestions`).

- With no `product` parameter, render the empty search screen.
- With a `product` parameter, validate it through a small bound form over `request.GET`
  (see §2) rather than an ad-hoc `int()` cast, so a non-numeric, missing, or inactive id
  all produce the same reusable message.
- Load the candidate with `prefetch_related('substance_links__substance')` and the
  household items with `select_related('product')` +
  `prefetch_related('product__substance_links__substance')`, matching `item_list`'s
  contract exactly.
- Writes nothing. No `save()`, no `create()`, no `messages.*` call.

#### 2. The query-parameter form

**File**: `pharmacy/forms.py`

**Intent**: Give the check view one validation path for the `product` parameter,
reusing the add form's existing wording for a product the registry no longer carries.

**Contract**: `ProductCheckForm(forms.Form)` with a single
`product = forms.ModelChoiceField(queryset=Product.objects.filter(is_active=True), ...)`
carrying the same `invalid_choice` message as `ItemAddForm`
(`'Ten produkt nie jest już dostępny w rejestrze.'`). Not a `ModelForm` — nothing is
being saved.

#### 3. The URL

**File**: `pharmacy/urls.py`

**Intent**: Give the check its own route, so `S-06` can move the entry point without
touching the screen.

**Contract**: `path('check/', views.product_check, name='product_check')`.

#### 4. The template and its copy

**File**: `pharmacy/templates/pharmacy/product_check.html`

**Intent**: State the substance-set fact and name no consequence. The screen is allowed
to say what is at home; it is not allowed to say what that means for the prescription.
It must also make its own read-only nature visible, since "nothing was added" is the
property that distinguishes this screen from the add screen.

**Contract**: Extends `base.html`. Sections, each rendered only when it applies:

- **Heading and standing line** — `Sprawdź lek`, and a line stating that nothing will
  be added to the list.
- **Search field** — a text input plus an empty suggestions `<ul>`, using the same
  element ids and `role="listbox"` markup as `item_form.html` so Phase 3's shared module
  attaches without special-casing. Inert until Phase 3; the screen is reached by URL in
  this phase.
- **Candidate header** (whenever the `?product=` id validated — not to be confused with
  `CandidateCheck.resolved`, which is about substances) — name, strength and form in the
  same order `_item_row.html` renders them, plus the substances the comparison used,
  listed explicitly when there are any. This listing is the transparency mitigation for
  picking at presentation level: the user can see what was compared.
- **Refusal, two shapes** (when `resolved` is false). The screen still owes the user the
  identity answer, so what it refuses depends on whether a `SAME_PRODUCT` match exists:
  - *Partial* (`matches` non-empty) — render the match row as normal, and beneath it a
    message that the product's active substance could not be established, so the
    household could not be checked for substitutes. The confirmation comes first; the
    limitation qualifies it.
  - *Total* (`matches` empty) — a message that the active substance could not be
    established and that no comparison is possible. Rendered *instead of* any result
    list, never above an empty one, and never alongside the no-match statement.
- **Match list** (when matches exist) — one flat `<ul>`, one row per matching product, in
  `check_candidate`'s order. Each row carries its own label from the booleans on the
  match, reusing the household list's vocabulary so the two screens do not speak
  different languages: the same product, the same active substance, or a shared
  substance. `SHARED_SUBSTANCE` rows name the shared substances; the other two do not
  (they are identical by definition). Every row shows name, strength, form and
  `Liczba opakowań: N`.

  > **Added 2026-08-30, during Phase 1 implementation — the `SAME_PRODUCT` label
  > degrades on multi-holder presentations.** The check screen picks at presentation
  > level with no producer step, so the candidate is always the presentation's
  > `_default_product`. The add screen *does* have a producer step, so a household item
  > can point at a different holder's row under the same presentation. When that
  > happens, `item.product_id == candidate.pk` is false, `classify` still returns
  > `FULL`, and the row is labelled `SAME_SUBSTANCES` rather than `SAME_PRODUCT`.
  >
  > Measured against the 20,254 active products in the dev registry: **1,003 of 16,200
  > presentations (6.19%) carry more than one `marketing_holder`** — that is the
  > ceiling on how often this can happen, not how often it does, since it additionally
  > requires the item to have been added with `producer_confirmed` on a non-default
  > holder. (`Nurofen 200 mg, tabletki powlekane` is a single row and never degrades;
  > `Nurofen dla dzieci Forte truskawkowy 40 mg/ml` spans 6 holders and can.)
  >
  > The failure is a one-tier softening, never a false positive and never a "no match":
  > `SAME_PRODUCT` is a primary-key equality, so it can be missed but not invented, and
  > the row still appears at the top of the list with its pack count. The cost is
  > credibility — the screen would label a box reading *Nurofen dla dzieci Forte
  > truskawkowy* as "a different product with the same active substance".
  >
  > **Decision for this phase: absorb it in the copy.** Word the `SAME_SUBSTANCES`
  > label so it does not insist the product is *different*; the row already prints the
  > name, so the reader reconciles it at a glance. Two alternatives were considered and
  > rejected here: treating the whole presentation as identity inverts the never-guess
  > NFR (it would claim "exactly this" across the 1.24% of presentations whose rows
  > disagree on substances), and matching the item against every `Producer.product_id`
  > in the presentation is honest but forces `duplicates.py` to know what a presentation
  > is and changes `check_candidate`'s signature — a design change that needs its own
  > plan, not a mid-phase edit. Revisit under `S-06` if the softened label reads badly
  > in real use.
- **No-match statement** (resolved, zero matches) — a plain statement that nothing in the
  household contains those substances. A fact, with no consequence attached.
- **Uncomparable disclosure** (when `resolved` **and** `uncomparable_count > 0`) — a line
  stating how many household items have no established active substance and were not
  compared. Rendered alongside a match list *and* alongside a no-match statement, because
  it qualifies both. Suppressed when `resolved` is false: no substance comparison ran at
  all there, the refusal message already says so, and the count would otherwise be
  reported against the very item just shown as a match.
- **Invalid-product message** — the form's error, rendered in the same
  `class="form-error"` shape `item_form.html` uses.

  > **Amended 2026-08-30 during Phase 2, at the user's direction — what actually
  > shipped.** Four changes to the contract above, all in the template only; no
  > field of `CandidateCheck` or `CandidateMatch` was added, removed or renamed.
  >
  > 1. **Row labels are sentences, not noun phrases.** `SAME_PRODUCT` renders
  >    *"Masz już N opakowań tego samego leku."*, `SAME_SUBSTANCES` *"Masz już lek
  >    z tą samą substancją czynną."*, `SHARED_SUBSTANCE` *"Masz już lek, który ma
  >    przynajmniej jedną wspólną substancję czynną."* The vocabulary still tracks
  >    the household list's three relationships; the wording is fuller. `Zamienniki`
  >    was deliberately not reused as a row label — neutral on a list screen, it
  >    edges toward a substitution claim next to a prescription.
  > 2. **A `SAME_PRODUCT` row repeats neither the product name nor a separate pack
  >    count.** Both are redundant against the candidate heading directly above it,
  >    and the count now sits inside the sentence. The other two kinds still name
  >    their product and carry `Liczba opakowań: N` — knowing *which* other box is
  >    the entire content of those rows.
  > 3. **The candidate-substances line is suppressed when identity is the whole
  >    answer**, via a new `CandidateCheck.only_same_product` property (true when
  >    `matches` is non-empty and every match is `SAME_PRODUCT`). The line is the
  >    presentation-level-picking mitigation, and it only earns its place while
  >    there is a substance match for it to explain; nothing was decided by
  >    substances when the answer came from a primary key. It still renders on a
  >    no-match screen, and on a screen that shows both a same-product row and a
  >    substitute.
  > 4. **The uncomparable disclosure is not rendered at all.** The bullet above
  >    describing when to show it is superseded. `uncomparable_count` is still
  >    computed and still unit-tested in `test_duplicates.py`, so restoring the
  >    line is a one-line template change.
  >
  > **What (4) costs, recorded rather than left implicit.** This was one of the two
  > silent-guess traps named in Current State Analysis: a "nothing at home matches"
  > verdict is now shown over a household the comparison only partly saw, with
  > nothing on screen saying so. The decision was made on clutter grounds after
  > seeing the line on every resolved screen in manual testing. If it is revisited,
  > the narrower form — disclose only alongside the no-match statement, where it
  > qualifies a verdict rather than decorating a match list — is where it earns its
  > place. `ProductCheckUncomparableSuppressionTests` pins the removal so it stays
  > a decision rather than something a later edit reintroduces by accident.
  >
  > **One consequence outside the template.** Putting a count inside a Polish
  > sentence reintroduces the plural problem this plan's Critical Implementation
  > Details dodged by mandating label-then-number phrasing. Polish takes three
  > forms and `pluralize` gives two, so Phase 2 adds `pharmacy/templatetags/polish.py`
  > with a `plural_pl` filter and `pharmacy/tests/test_polish_filters.py` covering
  > the teens exception (12/13/14 take "many" despite ending in 2/3/4). The
  > label-then-number rule still stands everywhere else on the screen.

All copy is Polish. No sentence may recommend, discourage, or imply an action about the
prescription.

#### 5. Entry point from the household list

**File**: `pharmacy/templates/pharmacy/item_list.html`

**Intent**: Make the screen reachable. One link beside the existing `Dodaj lek` button —
the smallest thing for `S-06` to relocate.

**Contract**: An anchor to `{% url 'pharmacy:product_check' %}` in the existing
paragraph that holds the add button.

#### 6. Styles, only if needed

**File**: `static/css/app.css`

**Intent**: Match-row separation consistent with the list screen's existing treatment.
Add nothing that `S-07` will have to undo.

**Contract**: At most a `.check-matches` list rule reusing the existing Pico custom
properties (`--pico-muted-border-color`, `--pico-border-radius`) the way
`.duplicate-cluster-items` already does. Skip entirely if unstyled markup reads
acceptably.

#### 7. Integration tests

**File**: `pharmacy/tests/test_product_check.py` (new)

**Intent**: Assert the screen's four load-bearing claims: it answers correctly, it
refuses rather than guessing, it writes nothing, and its query count does not grow with
the size of the household.

**Contract**: A new test module following `test_item_list.py`'s conventions (module
docstring stating what the file pins, a local `make_product` helper, `force_login`).
Cases:

- anonymous request redirects to login; a member of another household never sees this
  household's items in a result;
- each result state renders its own copy: `SAME_PRODUCT`, `SAME_SUBSTANCES`,
  `SHARED_SUBSTANCE`, and resolved-with-no-matches;
- **total refusal**: an unresolved candidate the household does *not* hold renders the
  total-refusal copy and `assertNotContains` the no-match copy — the assertion that
  separates "we could not tell" from "there is nothing";
- **partial refusal**: an unresolved candidate the household *does* hold renders the
  match row with its pack count **and** the substitutes-not-checked copy, and
  `assertNotContains` the total-refusal copy — the state this update exists to add;
- **uncomparable disclosure**: a household holding one unresolved item renders the
  disclosure line alongside a no-match statement for a *resolved* candidate, and
  `assertNotContains` that same line when the candidate is unresolved;
- **no write**: `Item.objects.count()` is unchanged across a request that produces
  matches, and the response to a `POST` is 405 (`require_GET`);
- a `?product=` id that is non-numeric, absent from the registry, or inactive renders the
  invalid-product message with status 200, not a 404;
- **query shape**: `assertNumQueries` around a check against a household of 2 items and
  again against a household of 12, asserting the *same* count both times. Comment the
  split between request plumbing and data queries in the style of
  `test_item_list.py:124-129`. Asserting equality across two household sizes is the N+1
  guard; the absolute constant is recorded once the implementation settles.

### Success Criteria:

#### Automated Verification:

- New tests pass: `uv run manage.py test pharmacy.tests.test_product_check`
- Full suite passes: `uv run manage.py test`
- Type checking passes: `uv run mypy .`
- Django system checks pass: `uv run manage.py check`

#### Manual Verification:

- Visit `/check/` with a valid `?product=` id for a product the household owns, one it
  owns a substitute for, one it partially overlaps, and one it has nothing related to.
  Each reads correctly. (The search field is inert until Phase 3 — reach the screen by
  URL, taking an id from the admin or the shell.)
- Visit `/check/?product=` for a product with no substance links that the household does
  not hold, and confirm the screen refuses to compare rather than reporting no match.
- Add a box of a product with no substance links, then check that same product: the
  screen confirms it is already at home with its pack count, and says beneath it that
  substitutes could not be checked.
- Read every sentence on the screen against the licence decision: it states what is at
  home and never what to do about the prescription.
- View the screen at phone width (≈390 px) and confirm the match rows and labels stay
  readable.

**Implementation Note**: After completing this phase and all automated verification
passes, pause here for manual confirmation from the human before proceeding.

---

## Phase 3: Shared product-search module

### Overview

Extract the search machinery out of `autocomplete.js` into a module both screens use,
rewire the add screen onto it, and give the check screen its picker. The only phase
whose behaviour no automated test in this repo can observe — so the extraction is
mechanical by design and the add flow is verified by hand.

### Changes Required:

#### 1. The shared module

**File**: `pharmacy/static/pharmacy/js/product-search.js` (new)

**Intent**: Hold the parts of the picker that are genuinely identical on both screens,
moved verbatim, so there is one answer to "how does product search behave" rather than
two that drift.

**Contract**: An IIFE assigning a single global, exposing the DOM helpers currently
private to `autocomplete.js` (`clearList`, `makeOption`, `renderList`, `optionsOf`,
`activateOption`, `attachKeyboardNav`, `renderMessage`), a
`presentationLabel(presentation)` formatter, and
`attachPresentationSearch({ input, list, onPick, onInput })` carrying the debounce,
minimum-length, abort-controller, sequence-guard, fetch and error-message logic exactly
as it stands today.

- `onInput` exists so the add screen can keep clearing its hidden fields on every
  keystroke — that behaviour stays on the add screen, it does not move into the module.
- The producer picker does **not** move. It filters an in-memory list with no debounce
  and no fetch; routing it through the shared path would change its behaviour, and the
  check screen has no producer step to share with.
- `DEBOUNCE_MS`, the minimum query length, the `/suggestions/` path and both Polish
  error strings move across **unchanged**. This phase moves code; it does not tune it.
- Preserve the existing comments explaining *why* each guard exists (mousedown before
  blur, `textContent` never `innerHTML`, the `response.ok` check before parsing, the
  sequence guard against a superseded response). They are the reason the extraction is
  reviewable.

#### 2. Rewire the add screen

**File**: `pharmacy/static/pharmacy/js/autocomplete.js`

**Intent**: Keep every add-screen behaviour byte-identical while sourcing the shared
parts from the module. What remains here is what is genuinely add-screen-specific.

**Contract**: Retains `clearSelection`, `pickProducer`, `renderProducerOptions`,
`pickPresentation`, the producer input listener and the producer keyboard nav, all
calling the shared helpers. Replaces its own search wiring with one
`attachPresentationSearch({ input: searchInput, list: suggestionsList, onPick: pickPresentation, onInput: clearSelection })`
call. The early `if (!searchInput) return;` guard stays — it is what keeps the script
inert on pages without the field.

#### 3. The check screen picker

**File**: `pharmacy/static/pharmacy/js/check.js` (new)

**Intent**: Turn a pick into a navigation. The check screen has no form to fill and
nothing to submit.

**Contract**: Reads a result-URL base from a `data-` attribute on the search input
(populated by the template with `{% url %}`, so the route is not duplicated in
JavaScript), then calls `attachPresentationSearch` with an `onPick` that sets
`window.location` to that URL with `?product=<default_product_id>`. Guards on the
input's presence the same way `autocomplete.js` does.

#### 4. Wire both templates

**Files**: `pharmacy/templates/pharmacy/item_form.html`,
`pharmacy/templates/pharmacy/product_check.html`

**Intent**: Load the shared module ahead of each screen's own script, and hand the check
screen its result URL.

**Contract**: `product-search.js` precedes the screen script in document order; both
keep `defer`. The check template adds the `data-` result-URL attribute to its search
input.

#### 5. Script-order test

**File**: `pharmacy/tests/test_product_check.py`

**Intent**: Catch the one failure mode a Django test *can* see here — a template that
loads the screen script without the module, or in the wrong order — since deferred
scripts execute in document order and a reversed pair breaks silently in the browser.

**Contract**: One test per template asserting both `<script>` tags are present in the
rendered HTML and that the module's tag appears at a lower index than the screen
script's.

### Success Criteria:

#### Automated Verification:

- Script-order tests pass: `uv run manage.py test pharmacy.tests.test_product_check`
- Full suite passes: `uv run manage.py test`
- Type checking passes: `uv run mypy .`
- Django system checks pass: `uv run manage.py check`
- Static files collect without error: `uv run manage.py collectstatic --noinput`

#### Manual Verification:

- **Add flow regression sweep** (the point of this phase's sequencing — no automated
  test covers any of it): on `/list/add/`, type a partial name and confirm suggestions
  appear after the pause; arrow keys move the highlight and Enter picks; Escape closes
  the list; picking a multi-producer presentation reveals the producer field and picking
  a producer fills it; editing the name after a pick clears the selection so a stale
  product id cannot be submitted; a pick followed by submit still saves the right product
  with the right producer confirmation.
- Confirm the add screen's failure message still appears when the session is expired
  (log out in a second tab, then type) — the `response.ok` guard survived the move.
- On `/check/`, type a name, pick a suggestion, and confirm the page navigates to the
  result for that product.
- Both flows on a phone-width viewport.

**Implementation Note**: This phase is droppable. If the add-flow sweep shows any
regression that is not immediately obvious, revert Phase 3 and ship Phases 1–2 — the
check screen still works from a URL, and the shared module can be retried once
`test-plan.md` §3 Phase 4 lands an e2e layer that can observe it.

---

## Testing Strategy

### Unit Tests:

- `check_candidate` against fixture-derived sets, never against its own output.
- The three match tiers, their ordering, and the `SAME_PRODUCT` / `SAME_SUBSTANCES`
  split.
- Identity independent of resolution: an unresolved candidate the household holds still
  produces its `SAME_PRODUCT` match.
- Both empty-set paths: an unresolved candidate, and unresolved household items.
- `pack_count` aggregation across repeated boxes of one product.
- Shared-substance ordering on a pair whose alphabetical order differs from insertion
  order.

### Integration Tests:

- Every result state rendered end-to-end through the Django test client.
- Both refusal paths asserted *negatively* as well as positively — total refusal with
  the no-match copy absent; partial refusal with the total-refusal copy absent and the
  match row present.
- Household scoping: another household's items never reachable through this view.
- The read-only guarantee: `Item.objects.count()` unchanged; `POST` returns 405.
- Query shape held constant across a 2-item and a 12-item household.
- Template script order for both screens.

### Manual Testing Steps:

1. From `/list/`, follow the new link to the check screen.
2. Check a product the household owns outright, then one it owns a substitute for, then
   a combination product overlapping one item, then something unrelated.
3. Check a product with no registry substance links that the household does *not* hold;
   confirm a refusal, not a "no match".
4. Add an item whose product has no substances, then check that same product; confirm
   it is reported as already at home, with the substitutes-not-checked note beneath it.
5. With that unresolved item still on the list, check a *resolved* product; confirm the
   uncomparable disclosure appears.
6. Confirm the household list is unchanged after every check above.
7. Run the full add-flow regression sweep from Phase 3.
8. Repeat 1–4 at ≈390 px viewport width.

## Performance Considerations

The check runs the same prefetch contract as the household list — one query for the
candidate plus its substance links and substances, one for items with their products,
and one each for the item substance links and substances — none of which grow with item
count. `check_candidate` reads only `product.substance_links.all()` through
`substance_keys`, so it never escapes the prefetch cache; a `.filter()`, `.exists()` or
`.count()` anywhere in it would reintroduce N+1, which is what the two-household-size
`assertNumQueries` pair exists to catch. The screen is well inside the one-second
acknowledgement NFR, and the suggestion endpoint it reuses is already bounded to ten
presentation groups per keystroke.

## Migration Notes

None. No model changes, no migrations, no data backfill. The slice adds a route, a
view, a form, a template, a pure function and three static files.

## References

- Roadmap slice: `context/foundation/roadmap.md` §S-05
- Quality contract: `context/foundation/test-plan.md` §3 (rollout), §4 (stack), §5 (gates)
- The rule this slice reuses: `pharmacy/duplicates.py:33`, `:48`
- Presentation grouping and the 1.24% substance-disagreement note:
  `registry/suggestions.py:82`
- Prefetch and `assertNumQueries` precedent: `pharmacy/tests/test_item_list.py:124`
- Prior slice: `context/archive/2026-08-24-duplicate-flagging-on-list/`

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles. See `references/progress-format.md`.

### Phase 1: The candidate-vs-household rule

#### Automated

- [x] 1.1 Unit tests pass: `uv run manage.py test pharmacy.tests.test_duplicates` — aaa4482
- [x] 1.2 Full suite passes: `uv run manage.py test` — aaa4482
- [x] 1.3 Type checking passes: `uv run mypy .` — aaa4482
- [x] 1.4 Django system checks pass: `uv run manage.py check` — aaa4482

#### Manual

- [x] 1.5 Docstrings match the module's existing density — why, not what — aaa4482
- [x] 1.6 `check_candidate` contains no direct set comparison; every relationship goes through `classify` — aaa4482

### Phase 2: The check screen

#### Automated

- [x] 2.1 New tests pass: `uv run manage.py test pharmacy.tests.test_product_check`
- [x] 2.2 Full suite passes: `uv run manage.py test`
- [x] 2.3 Type checking passes: `uv run mypy .`
- [x] 2.4 Django system checks pass: `uv run manage.py check`

#### Manual

- [x] 2.5 All four result states read correctly when reached by URL
- [x] 2.6 Unresolved candidate the household does not hold refuses to compare rather than reporting no match
- [x] 2.7 Unresolved candidate the household does hold is confirmed as already at home, with substitutes-not-checked beneath it
- [x] 2.8 Every sentence states what is at home and never what to do about the prescription
- [x] 2.9 Screen readable at ≈390 px viewport width

### Phase 3: Shared product-search module

#### Automated

- [ ] 3.1 Script-order tests pass: `uv run manage.py test pharmacy.tests.test_product_check`
- [ ] 3.2 Full suite passes: `uv run manage.py test`
- [ ] 3.3 Type checking passes: `uv run mypy .`
- [ ] 3.4 Django system checks pass: `uv run manage.py check`
- [ ] 3.5 Static files collect without error: `uv run manage.py collectstatic --noinput`

#### Manual

- [ ] 3.6 Add-flow regression sweep passes: suggestions, keyboard nav, producer step, selection clearing, save
- [ ] 3.7 Add screen still shows the failure message on an expired session
- [ ] 3.8 Check screen navigates to the result on pick
- [ ] 3.9 Both flows verified at phone width
