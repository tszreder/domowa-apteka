# Add-item integrity Implementation Plan

## Overview

This is `test-plan.md` §3 Phase 2 ("Add-item integrity"), covering risks #1,
#3, and #4 from the risk map. Research (`research.md`) already narrowed the
gap to something much smaller than the phase's name suggests: most of risk
#3 and essentially all of risk #4 already have committed, mutation-verified
test coverage. What remains is one missing integration test that closes
risk #1's most concrete reachable shape, one small production fix plus its
proof for the phase's query-shape obligation, and a cookbook update.

## Current State Analysis

- **Risk #1** (wrong product picked from autocomplete): product identity
  already travels as a stable pk through a hidden `ModelChoiceField`
  (`pharmacy/forms.py:8-24`), never re-derived from typed text
  (`pharmacy/views.py:64-109`). The one reachable, currently-untested shape
  is the "Sortis 20" collision: two `Product` rows sharing name, strength,
  and form, with no distinct `marketing_holder` (so no producer picker ever
  shows), whose substance links disagree. `registry/suggestions.py`'s
  `_default_product` already has a deterministic tiebreak for this
  (`registry/tests/test_suggestions.py:151-167` pins it at the
  `search_presentations` layer) — no test drives that tiebreak's output
  through an actual `pharmacy:item_add` POST and asserts what got persisted.
- **Risk #3** (wrong substance set resolved): the parser-level unit
  coverage in `registry/tests/test_parser.py` already asserts multi-substance
  and placeholder-denylist correctness against source-derived expected
  values, not against "whatever the parser outputs." At the pharmacy layer,
  substances are always read live through `product.substance_links` — never
  copied — so the Phase 1 collision test additionally proves risk #3 for
  free: once the right product is persisted, its substances are definitionally
  right, because there is no intermediate transformation to get wrong.
- **Risk #4** (a resolution failure treated as success or silently dropped):
  already comprehensively covered. `pharmacy/tests/test_item_add.py:115-126`
  proves the item persists with a warning on a resolution miss.
  `pharmacy/tests/test_duplicates.py:92-96`
  (`test_both_empty_is_none_not_full`) is `classify()`'s empty-set guard,
  mutation-tested when written (2026-08-24 archive). Both the unit layer
  (`pharmacy/tests/test_duplicates.py:152-159`,
  `test_two_unresolved_items_are_not_grouped_with_each_other`, calling
  `build_list_view` directly) and the real view layer
  (`pharmacy/tests/test_item_list.py:403-419`,
  `test_two_unresolved_items_are_not_grouped_and_appear_in_unresolved_section`,
  a full `item_list` GET) already prove two different unresolved items never
  group. There is no coverage gap left to fill for risk #4 — the open
  question research left for this phase (stored fact vs. derived property)
  is a design decision, not a missing test, and is resolved below.
- **Query-shape gate**: confirmed live by reading `pharmacy/views.py:64-109`
  and `pharmacy/forms.py:8-24`. `ItemAddForm`'s `product` queryset has no
  `prefetch_related`, unlike `ProductCheckForm`
  (`pharmacy/forms.py:45-48`), which already prefetches
  `substance_links__substance` on its own `ModelChoiceField` for the
  identical reason. `item.product.substance_links.all()` is read three times
  across `pharmacy/views.py:75`, `pharmacy/duplicates.py:47` (via
  `check_candidate(item.product, ...)`), and `pharmacy/duplicates.py:337` —
  and because `item.product` is the same Python instance throughout the
  request (assigned by `ModelForm.save()`, never re-fetched), adding the
  same prefetch `ProductCheckForm` already uses collapses all three reads to
  the cost of one, with no changes needed in `views.py` or `duplicates.py`.

### Key Discoveries:

- `pharmacy/tests/test_product_check.py:421-481` already established this
  project's pattern for proving a query count is independent of a variable
  that used to scale it: measure at two sizes, assert equality, rather than
  pinning a single literal that would either encode a bug or require
  guessing the fixed post-fix count. `test_product_check.py` used household
  size as the variable; this phase's variable is substance count on the
  added product.
- `registry/tests/test_suggestions.py:151-167`
  (`test_default_is_lowest_registry_id_when_rows_disagree_on_substances`)
  is the exact "Sortis 20" fixture this phase's Phase 1 reuses. Its shape:
  two `Product` rows, same name, no `marketing_holder`, one substance link
  each that disagree — `_default_product` picks the lower `registry_id`.
- `ModelForm.save()`'s field assignment (`instance.product = cleaned_data['product']`)
  keeps the exact model instance `ModelChoiceField.clean()` returned,
  prefetch cache included — this is why the form-level prefetch fix requires
  no view-level restructuring.

## Desired End State

- `item_add` has a committed test proving that when two registry rows
  collide on name/strength/form with no distinguishing producer, the
  product `search_presentations` would offer as the default is the one
  actually persisted, with its own (not the colliding row's) substances.
- `item_add`'s query count for a successful add no longer scales with the
  added product's substance count, proven by a test that would fail if the
  scaling ever came back — not by a hardcoded literal.
- `context/foundation/test-plan.md` §6.1, §6.2, and §6.6 read as filled-in
  cookbook entries instead of `TBD`, and the risk #4 "stored fact vs.
  derived property" open question is answered in writing, not left open.

**Verification:** `uv run manage.py test pharmacy registry`, `uv run mypy`,
and a manual add-item pass in the browser confirming the flow still works
end to end.

## What We're NOT Doing

- Not changing `registry/suggestions.py`'s tiebreak algorithm, or resolving
  the underlying 1.24% substance-disagreement ambiguity it accepts. This
  phase tests that the current, deliberate design does what it claims —
  it does not change what it claims.
- Not adding a stored `resolution_status` (or similar) field to `Item` or
  `Product`. Confirmed with the user: the derived `unresolved` property plus
  `classify()`'s empty-set guard is the intended permanent design, matching
  the archived plan's explicit rejection of a stored boolean (drift risk on
  re-import).
- Not writing a new test for risk #4's grouping guarantee. It already exists
  at both the unit layer (`test_duplicates.py`) and the real-view layer
  (`test_item_list.py`) — see Current State Analysis. Adding a third,
  narrower version would be cost without signal.
- Not extracting a shared queryset helper between `ItemAddForm` and
  `ProductCheckForm`. Confirmed with the user: inline, matching
  `ProductCheckForm`'s existing pattern.
- Not touching risks #2, #5, #6, or #7 — those belong to later rollout
  phases (§3 Phases 3-5).
- Not striking through roadmap S-02 Unknown 1 as resolved. Research flagged
  this as a real documentation gap, but explicitly out of scope for this
  phase's test target.
- Not adding household-size query variation to the new query-shape test.
  That axis is already covered by the same `select_related`/
  `prefetch_related` pattern `item_list` and `product_check` use for
  `other_items`, and research measured it flat (14→16 queries, a one-time
  step for "any other items exist at all," not per-item growth) — it is not
  the identified gap.

## Implementation Approach

Three sub-phases, each independently committable: a new integration test
closing risk #1's reachable collision shape (also proving risk #3 for that
shape, since substances are read live off whichever product gets
persisted); a one-line production fix plus the query-shape test the phase
goal requires; and a documentation-only closing phase that records why risk
#4 needs no new test and fills in the cookbook. No schema changes, no
changes to `registry/suggestions.py`, no changes to `pharmacy/duplicates.py`.

## Phase 1: Collision persistence test (risks #1, #3)

### Overview

Prove that for the "Sortis 20" collision shape — two registry rows sharing
name/strength/form with no distinguishing producer, disagreeing on
substances — the product `search_presentations` computes as the default is
the one `item_add` actually persists, along with that product's own
substances.

### Changes Required:

#### 1. Collision-persistence test

**File**: `pharmacy/tests/test_item_add.py`

**Intent**: Add a test to `ItemAddTests` that builds the same two-row
collision shape `registry/tests/test_suggestions.py:151-167` already pins
at the `search_presentations` layer, derives `default_product_id` from
`search_presentations` the same way the client would, POSTs that id through
`pharmacy:item_add`, and asserts the persisted `Item.product_id` and its
substance are the lower-`registry_id` row's — not the higher row's. This is
the one place research found no test connecting the suggestions-layer
tiebreak to what `item_add` actually saves.

**Contract**: Reuses the existing local `make_product` helper in
`test_item_add.py` for both rows (no `marketing_holder` on either, matching
the fixture that makes them collapse into one presentation with no producer
picker). Chains the two calls the way the browser effectively does —
suggestion lookup, then save:

```python
presentation = search_presentations('sortis')[0]
response = self.client.post(
    reverse('pharmacy:item_add'),
    {'product': presentation.default_product_id, 'producer_confirmed': 'false'},
)
```

Assert `Item.objects.get().product_id == presentation.default_product_id`,
that the persisted item's `product.substance_links` names match
`presentation.substances` (the lower row's `Atorvastatinum`, not the higher
row's `Atorvastatinum calcicum`), and that `producer_confirmed` is `False`
— documenting that no manufacturer disambiguation ever had a chance to fire
for this shape.

### Success Criteria:

#### Automated Verification:

- [ ] New test passes: `uv run manage.py test pharmacy.tests.test_item_add`
- [ ] Full pharmacy + registry suite still passes: `uv run manage.py test pharmacy registry`
- [ ] Typecheck passes: `uv run mypy`
- [ ] **Falsification recorded**: temporarily swap which row's `registry_id`
      is lower (or invert the tiebreak) and confirm the new test goes red
      for the stated reason, then revert.

#### Manual Verification:

- [ ] None required — this risk is unreachable through manual testing alone
      (it depends on two specific registry rows colliding), and the fixture
      is the only way to construct it deterministically.

---

## Phase 2: N+1 fix and query-shape assertion

### Overview

`item_add` reads `item.product.substance_links.all()` three times with no
prefetch, and the query count grows with the added product's substance
count — the exact anti-pattern `test-plan.md` warns a naive
`assertNumQueries` would otherwise encode as correct. Fix the read pattern,
then prove the count is now substance-count-independent using the same
two-size comparison `test_product_check.py` already established.

### Changes Required:

#### 1. Prefetch fix

**File**: `pharmacy/forms.py`

**Intent**: Eliminate the repeated `substance_links` reads by prefetching
once at the queryset level — the same fix `ProductCheckForm` already
applies to its own `ModelChoiceField`, for the identical reason (its own
docstring names it).

**Contract**: `ItemAddForm.product`'s queryset changes from
`Product.objects.filter(is_active=True)` to
`Product.objects.filter(is_active=True).prefetch_related('substance_links__substance')`.
No changes to `pharmacy/views.py` or `pharmacy/duplicates.py` — the fix
works because `item.product` stays the same prefetch-cached instance
`ModelChoiceField.clean()` returned all the way through the request.

#### 2. Query-shape test

**File**: `pharmacy/tests/test_item_add.py`

**Intent**: Prove the fix by measuring the same request at two different
substance counts on the added product and asserting equal query counts —
following `test_product_check.py:421-481`'s established pattern rather than
pinning a single literal, since the whole point is that the count must stop
depending on substance count, not that it equals some specific number today.

**Contract**: New `ItemAddQueryShapeTests` class, household held at zero
other items across both measurements so substance count is the only
variable. A `_measure(substance_count)` helper creates a product with that
many substances, POSTs it via `CaptureQueriesContext`, and returns
`len(captured)`. Test asserts `_measure(1) == _measure(3)`, plus the
concrete number observed (recorded once the fix is in place, not predicted
here — mirrors `test_product_check.py`'s `self.assertEqual(small, 10)`
sanity pin).

### Success Criteria:

#### Automated Verification:

- [ ] New query-shape test passes and is deterministic across repeated runs:
      `uv run manage.py test pharmacy.tests.test_item_add`
- [ ] **Falsification recorded**: temporarily revert the prefetch fix and
      confirm the query-shape test goes red (the two measured counts
      diverge), then re-apply the fix.
- [ ] Existing `test_item_add.py` tests unaffected by the prefetch change:
      `uv run manage.py test pharmacy.tests.test_item_add`
- [ ] Typecheck passes: `uv run mypy`

#### Manual Verification:

- [ ] Add an item through the running app's UI and confirm the add still
      succeeds, the flash message still names the right substances, and the
      duplicate-warning message still appears when adding a second item with
      an overlapping substance.

---

## Phase 3: Risk #4 confirmation and cookbook update

### Overview

No new test code. This phase records, in writing, that risk #4 already has
complete coverage and that the derived-property design is the accepted
permanent answer — closing research's Open Question #3 — then fills in
`test-plan.md`'s cookbook sections that named this rollout phase as their
source.

### Changes Required:

#### 1. Cookbook update

**File**: `context/foundation/test-plan.md`

**Intent**: Replace the `TBD — see §3 Phase 2` placeholders in §6.1 and
§6.2 with the patterns this phase actually established, and add a §6.6
entry recording what the phase taught — including the risk #4 finding, so
a future reader doesn't re-open a question this phase already answered.

**Contract**:
- §6.1 (unit test pattern): point to `registry/tests/test_parser.py`'s
  existing convention — expected substance sets read off the source XML
  fixture, never off current parser output — as the canonical answer for
  risk #3's unit layer.
- §6.2 (integration test pattern): describe Phase 1's pattern — derive the
  expected product/substances from the same `search_presentations` call the
  client relies on, then drive `pharmacy:item_add` and assert on what was
  persisted, rather than asserting against a hardcoded id.
- §6.6: 2-3 lines noting (a) the form-level `prefetch_related` fix for a
  `ModelChoiceField`-resolved FK that gets read multiple times downstream,
  (b) the query-shape two-size-comparison pattern generalizes beyond
  `product_check`, and (c) risk #4 required no new test — existing coverage
  at `test_duplicates.py` and `test_item_list.py` was already complete, and
  the derived-property design (no stored resolution state) is confirmed as
  final.

### Success Criteria:

#### Automated Verification:

- [ ] Named existing tests still pass, confirming the risk #4 coverage
      claim is accurate at time of writing:
      `uv run manage.py test pharmacy.tests.test_duplicates pharmacy.tests.test_item_list`
- [ ] Full suite passes: `uv run manage.py test`
- [ ] Typecheck passes: `uv run mypy`

#### Manual Verification:

- [ ] Read the updated §6.1/§6.2/§6.6 entries and confirm they describe the
      patterns actually committed in Phases 1-2, not an idealized version.

---

## Testing Strategy

### Unit Tests:

- No new unit tests — risk #3's unit layer (parser correctness) and risk
  #4's unit layer (`classify()`'s guard) are both already covered; this
  phase only adds integration-level tests.

### Integration Tests:

- Phase 1: collision shape through `item_add`, proving both risk #1
  (correct product persisted) and risk #3 (correct substances, since they
  are read live off that product) in one test.
- Phase 2: query-shape assertion proving the N+1 fix.

### Manual Testing Steps:

1. Add an item through the UI end to end and confirm the success flash
   names the right substances.
2. Add a second item sharing a substance with the first and confirm the
   duplicate warning appears.
3. Add an item for a product with no registry substance links and confirm
   the warning-not-error flash appears and the item still shows up on the
   list, in the unresolved section.

## Performance Considerations

The prefetch fix is the performance-relevant change in this phase: it
converts `item_add`'s substance reads from O(reads-of-the-value) to O(1)
regardless of how many times the same prefetched instance is queried
downstream. No other performance implications.

## Migration Notes

None. No schema changes in this phase.

## References

- Related research: `context/changes/add-item-integrity/research.md`
- Governing risk map and rollout table: `context/foundation/test-plan.md` §2, §3
- Existing query-shape pattern to follow: `pharmacy/tests/test_product_check.py:421-481`
- Existing collision fixture reused: `registry/tests/test_suggestions.py:151-167`
- Existing risk #4 coverage: `pharmacy/tests/test_duplicates.py:92-96,152-159`, `pharmacy/tests/test_item_list.py:403-419`
- Prefetch precedent: `pharmacy/forms.py:45-48` (`ProductCheckForm`)

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles. See `references/progress-format.md`.

### Phase 1: Collision persistence test (risks #1, #3)

#### Automated

- [x] 1.1 New test passes: `uv run manage.py test pharmacy.tests.test_item_add` — b656aaa
- [x] 1.2 Full pharmacy + registry suite still passes: `uv run manage.py test pharmacy registry` — b656aaa
- [x] 1.3 Typecheck passes: `uv run mypy` — b656aaa
- [x] 1.4 Falsification recorded: tiebreak swap makes the test go red, then reverted — b656aaa

#### Manual

- [x] 1.5 None required (documented as N/A — risk unreachable through manual testing alone) — b656aaa

### Phase 2: N+1 fix and query-shape assertion

#### Automated

- [x] 2.1 Query-shape test passes and is deterministic: `uv run manage.py test pharmacy.tests.test_item_add`
- [x] 2.2 Falsification recorded: reverting the prefetch makes the test go red, then re-applied
- [x] 2.3 Existing `test_item_add.py` tests unaffected: `uv run manage.py test pharmacy.tests.test_item_add`
- [x] 2.4 Typecheck passes: `uv run mypy`

#### Manual

- [x] 2.5 Add-item flow still works end to end in the browser, including the duplicate-warning message

### Phase 3: Risk #4 confirmation and cookbook update

#### Automated

- [ ] 3.1 Named existing tests still pass: `uv run manage.py test pharmacy.tests.test_duplicates pharmacy.tests.test_item_list`
- [ ] 3.2 Full suite passes: `uv run manage.py test`
- [ ] 3.3 Typecheck passes: `uv run mypy`

#### Manual

- [ ] 3.4 Updated §6.1/§6.2/§6.6 entries read as accurate to what was actually committed
