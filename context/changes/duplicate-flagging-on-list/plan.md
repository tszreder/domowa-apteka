# Duplicate flagging on the household list — Implementation Plan

## Overview

Roadmap slice **S-03** (PRD FR-003, US-03). The household list currently renders items
as unrelated flat entries. This change derives full-duplicate and partial-duplicate
relationships from each item's resolved active-substance set and renders them: items
with identical substance sets group into visible clusters, items whose sets overlap but
differ carry an expandable badge naming the overlap, and items whose substances could
not be resolved are held out of the relation entirely and shown in their own section.

Nothing is persisted. Flags are derived per request from data the list view already
prefetches, so they cannot fall out of step with F-02's daily registry refresh.

## Current State Analysis

The data path this slice needs is already complete and requires no migration.

- `Item` → `Product` (FK, `pharmacy/models.py:29-33`) → `substance_links`
  (`ProductSubstance`, `registry/models.py:67-108`) → `Substance`.
- `pharmacy/models.py:1-6` states the governing rule: an item **never copies** registry
  data; its substances are read live through the product FK so they always match what
  the registry currently states.
- `pharmacy/views.py:27-29` already issues
  `select_related('product').prefetch_related('product__substance_links__substance')`.
  Every substance this slice compares is therefore already in memory when the template
  renders — the comparison costs zero additional queries.
- `pharmacy/tests/test_item_list.py:127` pins that query shape at
  `assertNumQueries(7)`, with a comment explaining the split (4 request plumbing, 3
  data). This is a contract, not an incidental number.
- `item.unresolved` (`pharmacy/models.py:53-61`) already exists and already carries the
  reason it must use `.all()` rather than `.exists()` — `.exists()` bypasses the
  prefetch cache and issues a query per item.
- `pharmacy/templates/pharmacy/item_list.html` renders a flat `<ul class="item-list">`
  ordered by `Item.Meta.ordering = ['-added_at']`, with a `.unresolved` class and a
  `<mark>` warning on unresolved rows.
- Styling is Pico CSS (classless) vendored at `static/css/pico.min.css`, with
  `static/css/app.css` as the override seam — currently a comment and nothing else.

What is missing is only the comparison rule and its presentation.

### Key Discoveries:

- **Substance identity is `Substance.name_key`, not `name`.** `registry/models.py:28-34`
  makes `name_key` the unique identity and `name` "only the display form", with merged
  spellings resolved first-seen-wins by the parser. A comparison keyed on `name` would
  split a merged pair and miss real duplicates.
- **`ProductSubstance` deliberately has no unique constraint on `(product, substance)`**
  (`registry/models.py:70-73`): 89 source rows across 29,064 legitimately repeat a
  substance on the same product at a different amount. A multiset comparison would make
  such a product fail to match its own equivalent. The comparison must be over a genuine
  `frozenset`.
- **The denylist upstream exists for this slice specifically.** `registry/denylist.py:6-9`
  records that the registry sometimes states a *category* where a substance name belongs
  (`Produkt złożony` on 28 rows, `Preparat złożony` on 3, `Wyciągi alergenowe` on 4), and
  that loading them as ordinary substances would make "every product carrying `Produkt
  złożony` a full-substance-set duplicate of every other one, so S-03 would confidently
  flag 78 unrelated medicines as identical." That guard is already in place at load time.
  **This slice inherits it and must not re-implement it** — a second denylist in
  `pharmacy/` would be a competing copy of a rule F-01 owns.
- **A product whose only substance row was denylisted ends with zero links**, and
  therefore arrives here as `unresolved` — which is the correct outcome, and is why the
  unresolved handling below is a correctness guard rather than a cosmetic one.
- **`registry/suggestions.py` is the module shape to follow**: pure query/grouping
  functions with no HTTP attached, "so the rules that decide whether this slice is
  correct are testable in isolation" (`registry/suggestions.py:1-7`).
- **`registry/suggestions.py:32` exposes `Presentation.substances` as display names**, not
  keys. The planned prescription-check slice must not take its candidate set from that
  payload; it should resolve `product_id → Product → substance_keys()`, the same way
  `ItemAddForm` (`pharmacy/forms.py:12-18`) already resolves a chosen product.

## Desired End State

An adult viewing the shared household list sees:

- Items whose resolved substance sets are **identical** rendered as one visible cluster,
  labelled as true zamienniki when the products differ and as a same-product repeat when
  they do not.
- Items whose sets **overlap but differ** carrying a badge reading *"Wspólna substancja:
  &lt;partner names&gt;"*, which expands to show which substance drove each match.
- Items whose substances **could not be resolved** in their own section below the list,
  keeping their existing warning, and carrying no duplicate flag of any kind.
- The same 7 database queries as today.

Verified by: the phase success criteria below, `uv run manage.py test`, and a manual pass
on a phone-width viewport.

## What We're NOT Doing

- **Not persisting duplicate relationships.** No model, no migration, no backfill.
- **Not adding a dismiss/acknowledge action** on a flag. Chosen deliberately (see brief);
  it would need a model, a migration, and a rule for what happens when a dismissed item's
  substances change on the next refresh.
- **Not distinguishing containment from crossing overlap** in the UI. `{paracetamol}` ⊆
  `{paracetamol, pseudoefedryna}` and `{A,B}` vs `{B,C}` both render as partial, exactly
  as FR-003 and US-03 word it.
- **Not adding sort or filter controls.** The grouping *is* this slice's ordering answer.
- **Not adding a strength-mismatch caveat** inside a full-duplicate group. Strength is
  already rendered on every row (`item_list.html:13`), so grouped rows that differ in
  strength are already visibly different; a caveat line would add words, not information.
- **Not building the prescription check** ("does the household already hold what the
  doctor prescribed"). That is a future slice. This plan only ensures the primitive it
  will call is shaped to be reusable.
- **Not re-implementing the substance denylist.** F-01 owns it.
- **Not editing `context/foundation/test-plan.md`.** This slice fires two of its §7
  re-evaluation triggers, but foundation docs are written by the `/10x-*` chain — see
  "References" for the follow-up.

## Implementation Approach

Derive on read, keyed on substance sets.

The core primitive is deliberately **set-vs-set**, not item-pair:

```
substance_keys(product) -> frozenset[str]     # from prefetched links, on name_key
classify(a, b)          -> Overlap            # FULL | PARTIAL | NONE
```

with the list-level grouping built on top. This is the shape the planned prescription
check reuses: its input is a candidate registry product the household does not own, so it
has no `Item` to pair against. An item-pair primitive would force that slice to
reimplement the same rule, which is how two subtly different answers to "are these
duplicates?" end up shipping in one app.

Grouping and badging use two different idioms because the two relations have different
mathematical shapes. Identical-set is an **equivalence relation** — it partitions the
list cleanly, so clusters are well-defined. Partial overlap is **not transitive** — a
combination product can overlap two items that do not overlap each other — so it cannot
partition, and any attempt to render it as sections must either duplicate a row or
arbitrarily assign it to one cluster. Badges represent that many-to-many relation
honestly; grouping represents the partition honestly.

## Critical Implementation Details

**The empty set must be excluded before comparison, never compared.** `frozenset() ==
frozenset()` is `True` in Python, so a naive identical-set rule silently groups every
unresolved item as a full duplicate of every other unresolved item — the exact outcome
US-03's acceptance criteria forbid ("never silently grouped, hidden, or guessed into a
duplicate relationship"). `classify` must return `NONE` when either side is empty, and
the list builder must additionally partition unresolved items out before pairing. Both
guards are wanted: the first makes the primitive safe for the future prescription check
where there is no list to pre-partition; the second keeps the template simple.

**The query-shape contract is load-bearing and must not regress.** All comparison reads
must go through `product.substance_links.all()` on the already-prefetched instances. Any
use of `.exists()`, `.count()`, `.filter()`, or a fresh queryset on a link collection
bypasses the prefetch cache and reintroduces N+1 — `pharmacy/models.py:56-60` records
this trap having been hit once already. `assertNumQueries` is the guard, not review.

**Grouping must preserve the existing newest-first feel.** `Item.Meta.ordering` is
`['-added_at']`. A cluster's position in the rendered list is determined by its
newest member's `added_at`, so adding an item still moves its group to the top and the
screen does not reorder unpredictably around the user.

## Phase 1: Comparison primitive

### Overview

A new pure-logic module holding the whole duplicate rule, testable without HTTP, a
household, or a request. No user-visible change ships in this phase.

### Changes Required:

#### 1. Duplicate comparison module

**File**: `pharmacy/duplicates.py` (new)

**Intent**: Own the entire duplicate rule in one place, keyed on substance sets so the
planned prescription-check slice can reuse it against a candidate product that is not an
`Item`. Mirrors `registry/suggestions.py`'s "pure functions, no HTTP" shape, including a
module docstring recording *why* the primitive is set-keyed rather than item-paired.

**Contract**: Three public names.

- `substance_keys(product: Product) -> frozenset[str]` — reads
  `product.substance_links.all()` (prefetch-safe) and returns the deduplicated set of
  `link.substance.name_key`. The `frozenset` is what collapses the intentional
  `(product, substance)` repeats described in `registry/models.py:70-73`.
- `classify(a: frozenset[str], b: frozenset[str]) -> Overlap` — an `enum.Enum` with
  members `FULL`, `PARTIAL`, `NONE`. Returns `NONE` if either set is empty (see Critical
  Implementation Details), `FULL` on equality, `PARTIAL` on non-empty intersection,
  `NONE` otherwise.
- A list-level builder that takes an iterable of `Item` and returns the view's render
  data (see § 2).

#### 2. List-level grouping builder

**File**: `pharmacy/duplicates.py`

**Intent**: Turn a household's items into exactly what the template needs to render,
so the template contains no comparison logic and the view contains no loop. Partitions
unresolved items out, groups the rest into identical-set clusters, and annotates each
cluster with its partial-overlap partners.

**Contract**: One entry point returning a structure carrying (a) the ordered
full-duplicate clusters, (b) the ungrouped single items, and (c) the unresolved items —
with each cluster or single item carrying its partial-overlap partners as
`substance display name → [partner item labels]`.

Two rules the structure must encode:

- A cluster of size ≥ 2 is labelled by whether its members all share one `product_id`
  (a same-product repeat) or span more than one (true zamienniki). The distinction is
  the answer to "how are same-product repeats treated" — flagged, but not called
  zamienniki, which in Polish means a *different* brand.
- Cluster ordering is by the cluster's newest `added_at` (see Critical Implementation
  Details).

Partial-overlap partners are computed **between clusters**, not between raw items:
members of one cluster share an identical set by definition, so they have identical
partial relationships, and pairing raw items would emit the same badge N times inside
one group.

#### 3. Unit tests for the primitive

**File**: `pharmacy/tests/test_duplicates.py` (new)

**Intent**: Prove the rule against sets read off fixture rows — never against what the
function currently returns. Snapshotting current output as the expectation certifies
today's bugs, which `context/foundation/test-plan.md` §2 risk #3 names explicitly as the
anti-pattern to avoid.

**Contract**: Cases that must be covered, each with an expected set derived from the
fixture's own construction:

- identical sets → `FULL`; disjoint sets → `NONE`
- overlapping-but-different sets → `PARTIAL`, in both the containment and crossing shapes
- **either side empty → `NONE`** (the empty-set guard — the highest-value case here)
- a product with a repeated `(product, substance)` pair at different amounts matching a
  product carrying that substance once → `FULL`
- two products whose substances differ only in `Substance.name` but share a `name_key`
  → `FULL` (proves the comparison is keyed on identity, not display form)
- builder level: unresolved items appear in the unresolved bucket and in no cluster or
  partner list; a same-product cluster is labelled distinctly from a cross-product one;
  a combination product lands in the partner lists of two mutually disjoint items.

### Success Criteria:

#### Automated Verification:

- Test suite passes: `uv run manage.py test`
- New module's tests pass: `uv run manage.py test pharmacy.tests.test_duplicates`
- Type checking passes: `uv run mypy .`
- System checks pass: `uv run manage.py check`

#### Manual Verification:

- Each new test in `test_duplicates.py` has been watched to go **red** for the right
  reason, per `context/foundation/test-plan.md` §1 principle 4 — with the mutation used
  recorded alongside the test. The empty-set case must be falsified by making `classify`
  return `FULL` on two empty sets and confirming the test fails.
- The module docstring states why the primitive is set-keyed rather than item-paired, so
  the next reader does not "simplify" it into a closed item-pair function.

**Implementation Note**: After completing this phase and all automated verification
passes, pause for manual confirmation before proceeding.

---

## Phase 2: List grouping and the unresolved section

### Overview

Wire the builder into the list view and restructure the template into full-duplicate
clusters followed by a distinct unresolved section. Partial-overlap badges are Phase 3;
this phase ships full-duplicate grouping as standalone user-visible value.

### Changes Required:

#### 1. List view

**File**: `pharmacy/views.py`

**Intent**: Pass the builder's output to the template instead of a flat `items`
queryset, leaving the existing `select_related`/`prefetch_related` untouched so the
query shape does not change.

**Contract**: `item_list` keeps its existing queryset construction and decorators, and
adds the builder's result to the template context. The queryset must be materialised
once and handed to the builder — not re-iterated — so the prefetch cache is reused.

#### 2. List template restructure

**File**: `pharmacy/templates/pharmacy/item_list.html`

**Intent**: Render full-duplicate clusters as visually grouped units and move unresolved
items into their own labelled section beneath the list, so that an item carrying no flag
reads as "checked, nothing shared" rather than "not checked".

**Contract**: The template's per-item markup (name, strength, form, conditional producer,
substance list, delete form) is preserved as-is — only its container structure changes.
Existing behaviour that tests pin and must survive: the `.unresolved` class
(`test_item_list.py:88`), the producer shown only when `producer_confirmed`
(`test_item_list.py:90-108`), and the empty-list message. The unresolved section renders
only when at least one unresolved item exists.

Polish strings introduced in this phase: a cluster heading distinguishing zamienniki
(cross-product) from a same-product repeat, and a heading for the unresolved section.

#### 3. Cluster styling

**File**: `static/css/app.css`

**Intent**: Give a cluster a visible boundary so grouping is legible on a phone, using
the file's existing role as the override seam over classless Pico.

**Contract**: Class-based rules only, on classes the template introduces. No changes to
`static/css/pico.min.css`.

#### 4. Integration tests for grouping

**File**: `pharmacy/tests/test_item_list.py`

**Intent**: Prove a correct classification actually reaches the screen — the gap that
opens the moment styling starts carrying meaning, which `test-plan.md` §7 names as the
condition under which its template-styling exclusion stops applying.

**Contract**: Added to the existing `ItemListRenderingTests`, reusing its `make_product`
helper. Cases:

- two items with identical substance sets on **different** products render inside one
  cluster, labelled as zamienniki
- two items on the **same** product render as a cluster labelled as a same-product repeat,
  not as zamienniki
- two items with disjoint substance sets render as singles, in no cluster
- **two unresolved items are not grouped with each other** and appear in the unresolved
  section (the rendered counterpart of Phase 1's empty-set guard)
- an unresolved item and a resolved item are never grouped
- **`assertNumQueries` still passes at the existing count** with clustered items present

The query-count test must exercise a household containing at least one cluster, one
single, and one unresolved item — otherwise it passes over a shape the new code path
never takes.

### Success Criteria:

#### Automated Verification:

- Test suite passes: `uv run manage.py test`
- List tests pass: `uv run manage.py test pharmacy.tests.test_item_list`
- Type checking passes: `uv run mypy .`
- Query count is unchanged from the pre-change contract

#### Manual Verification:

- Each new test has been watched to go red for the right reason; the unresolved-grouping
  test is falsified by removing the unresolved partition from the builder.
- On a phone-width viewport, a cluster reads as one unit and the unresolved section reads
  as a separate concern, not as a third duplicate category.
- Adding a new item still places it (or its cluster) at the top of the list.

**Implementation Note**: Pause for manual confirmation before proceeding.

---

## Phase 3: Partial-overlap badges

### Overview

The partial-duplicate half of FR-003: an expandable badge naming the overlap. This is the
"feel" layer the roadmap warns this slice is judged on, and the slippable phase if
evenings run short before 2026-09-14.

### Changes Required:

#### 1. Badge markup

**File**: `pharmacy/templates/pharmacy/item_list.html`

**Intent**: Show partial overlap without letting a combination product's many partners
make the list unreadable — collapsed it names the partner items, expanded it shows which
substance drove each match.

**Contract**: A native `<details>`/`<summary>` element per item or cluster that has
partners. `<summary>` reads *"Wspólna substancja: &lt;partner item names&gt;"*; the
expanded body lists each shared substance with the partners it matched. Pico styles
`<details>` natively, so **no JavaScript is added to the list page** — the only existing
JS (`pharmacy/static/pharmacy/js/autocomplete.js`) belongs to the add form and is
untouched.

#### 2. Badge styling

**File**: `static/css/app.css`

**Intent**: Keep the badge subordinate to the item it annotates, so a list of mostly
non-duplicates does not read as a wall of warnings.

**Contract**: Class-based rules on the badge container only.

#### 3. Integration tests for partial overlap

**File**: `pharmacy/tests/test_item_list.py`

**Intent**: Prove the many-to-many case renders correctly — the case the roadmap flags as
this slice's hardest presentation problem.

**Contract**: Cases:

- a combination product `{paracetamol, pseudoefedryna}` with a `{paracetamol}` item and a
  `{pseudoefedryna}` item shows both partners, and each of the two singles shows only the
  combination product as its partner
- the expanded body attributes each partner to the correct shared substance
- an item with no overlap renders **no** badge element at all
- an unresolved item renders no badge (it has no partners by construction)
- containment (`{paracetamol}` ⊆ `{paracetamol, pseudoefedryna}`) renders as partial, not
  as full
- a badge is emitted once per cluster, not once per cluster member

### Success Criteria:

#### Automated Verification:

- Test suite passes: `uv run manage.py test`
- Type checking passes: `uv run mypy .`
- System checks pass: `uv run manage.py check`
- Query count assertion still passes with partial-overlap items present

#### Manual Verification:

- Each new test watched to go red; the "no badge when no overlap" test is falsified by
  making the builder emit an empty partner list instead of omitting the badge.
- On a phone-width viewport, a collapsed badge fits without wrapping into a paragraph,
  and expanding one does not shift the rest of the list disruptively.
- With ~10 real items where only two overlap, the screen reads as a list with two notes —
  not as a warning screen.

---

## Testing Strategy

### Unit Tests:

- `classify` across all four outcomes, with the empty-set case treated as the primary
  correctness guard rather than an edge case.
- `substance_keys` over the repeated-`(product, substance)` shape and the shared-`name_key`
  shape — the two cases the registry's own model comments say exist in real data.
- The builder's partitioning, clustering, labelling, and ordering rules.

### Integration Tests:

- Rendering of clusters, singles, the unresolved section, and badges, all through the
  real view and template.
- The `assertNumQueries` contract, exercised against a household containing every shape.

### Manual Testing Steps:

1. Add two differently-named products that resolve to the same single substance; confirm
   they group and are labelled as zamienniki.
2. Add the same product twice; confirm it groups but is *not* labelled zamienniki.
3. Add a combination product alongside two single-substance products it overlaps
   separately; confirm both partners appear and the expansion attributes each correctly.
4. Add a product with no resolvable substances; confirm it lands in the unresolved
   section, carries its warning, and appears in no cluster and no badge.
5. Add a second unresolved product; confirm the two are **not** flagged as duplicates of
   each other.
6. Repeat steps 1–4 on a phone-width viewport.

## Performance Considerations

The comparison is O(n²) over pairs, run in Python over data already in memory. At
household scale (tens of items) this is immaterial, and it adds **zero** queries — the
constraint that actually matters here, given the NFR requiring acknowledgement within one
second and `test-plan.md` §7's decision to assert query shape rather than wall-clock
latency. Pairing is done between clusters rather than raw items, which shrinks the
comparison set further whenever duplicates exist. If a household ever holds thousands of
items this needs revisiting; nothing in the PRD's `target_scale: small` suggests it will.

## Migration Notes

None. No model changes, no migration, no data backfill. The change is additive to the
read path and is reverted by reverting the commits.

## References

- Roadmap slice S-03: `context/foundation/roadmap.md` (Unknown 1 — partial-duplicate
  presentation; Unknown 2 — recompute on read vs write; both resolved in this plan)
- PRD FR-003 and US-03: `context/foundation/prd.md`
- Quality contract: `context/foundation/test-plan.md` — §1 principle 4 (falsification),
  §2 risks #3 and #4, §7 exclusions
- Module shape to mirror: `registry/suggestions.py:1-7`
- Upstream guard this slice depends on: `registry/denylist.py:6-14`
- Query-shape contract: `pharmacy/tests/test_item_list.py:110-130`
- **Follow-up (not this change):** this slice fires two `test-plan.md` §7 re-evaluation
  triggers — "duplicate-flagging correctness … re-evaluate the moment S-03 ships" and the
  template-styling exclusion's "re-evaluate if the list screen starts encoding meaning in
  styling". §4's deferred multimodal row ("deferred because the screen does not exist
  yet") also comes due. Foundation docs are not hand-edited; run
  `/10x-test-plan --refresh` after this change archives.

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands.
> Do not rename step titles. See `references/progress-format.md`.

### Phase 1: Comparison primitive

#### Automated

- [x] 1.1 Test suite passes: `uv run manage.py test`
- [x] 1.2 New module's tests pass: `uv run manage.py test pharmacy.tests.test_duplicates`
- [x] 1.3 Type checking passes: `uv run mypy .`
- [x] 1.4 System checks pass: `uv run manage.py check`

#### Manual

- [x] 1.5 Every new test watched to go red for the right reason, mutation recorded; empty-set case falsified by making `classify` return FULL on two empty sets — mutation: reordered `classify` to test `a == b` before the `not a or not b` guard, so `classify(frozenset(), frozenset())` returned `Overlap.FULL`; `test_both_empty_is_none_not_full` failed with `AssertionError: <Overlap.FULL: 1> != <Overlap.NONE: 3>`, confirming the guard is load-bearing. Reverted.
- [x] 1.6 Module docstring states why the primitive is set-keyed rather than item-paired

### Phase 2: List grouping and the unresolved section

#### Automated

- [x] 2.1 Test suite passes: `uv run manage.py test`
- [x] 2.2 List tests pass: `uv run manage.py test pharmacy.tests.test_item_list`
- [x] 2.3 Type checking passes: `uv run mypy .`
- [x] 2.4 Query count unchanged from the pre-change contract — `assertNumQueries(7)` holds both on the original 5-resolved-item test (now exercising the cluster path since they share one substance) and on a new test with a cluster, a single, and an unresolved item present simultaneously.

#### Manual

- [x] 2.5 New tests watched to go red; unresolved-grouping test falsified by removing the unresolved partition — mutation: changed `(resolved if keys else unresolved).append(item)` to unconditionally `resolved.append(item)` in `build_list_view`. `test_two_unresolved_items_are_not_grouped_and_appear_in_unresolved_section` failed: both unresolved items (empty substance sets are equal) collapsed into one `duplicate-cluster` labelled "Zamienniki", and `class="unresolved-section"` never appeared — exactly the silent-grouping bug the guard exists to prevent. Reverted.
- [x] 2.6 On a phone-width viewport a cluster reads as one unit and the unresolved section as a separate concern — verified live via Claude in Chrome at 390×844 against a seeded household: a "Zamienniki — ta sama substancja czynna" cluster rendered as one bordered box, and "Nie udało się ustalić substancji" rendered as a clearly separate section below with its own heading, not a third duplicate category.
- [x] 2.7 Adding a new item still places it or its cluster at the top of the list — verified live: adding a second "ManualTest Ibum" through the real add-item UI formed a same-product cluster labelled "Ten sam produkt dodany wielokrotnie" (not "Zamienniki") that appeared at the very top of the list, above all previously-newest items.

### Phase 3: Partial-overlap badges

#### Automated

- [ ] 3.1 Test suite passes: `uv run manage.py test`
- [ ] 3.2 Type checking passes: `uv run mypy .`
- [ ] 3.3 System checks pass: `uv run manage.py check`
- [ ] 3.4 Query count assertion still passes with partial-overlap items present

#### Manual

- [ ] 3.5 New tests watched to go red; "no badge when no overlap" test falsified by emitting an empty partner list instead of omitting the badge
- [ ] 3.6 Collapsed badge fits a phone-width viewport without wrapping into a paragraph; expanding does not shift the list disruptively
- [ ] 3.7 With ~10 real items where only two overlap, the screen reads as a list with two notes, not a warning screen
