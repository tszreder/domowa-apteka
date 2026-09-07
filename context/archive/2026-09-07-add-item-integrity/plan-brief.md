# Add-item integrity — Plan Brief

> Full plan: `context/changes/add-item-integrity/plan.md`
> Research: `context/changes/add-item-integrity/research.md`

## What & Why

This is `test-plan.md` §3 Phase 2: prove the product an autocomplete pick
resolves to is the product actually saved, that its substances match the
source row, and that a resolution failure stays visible rather than silent
— the three risks (#1, #3, #4) the frozen test-plan assigned to this
rollout phase.

## Starting Point

The add-item flow already does the hard part right: product identity
travels as a stable registry primary key through a hidden form field, never
re-derived from typed text, and substance resolution is read live off that
product with no copying. Research found the design is solid but three
things were unproven or unfixed: no test connects the suggestions-layer
tiebreak for a genuine name/strength/form collision to what `item_add`
actually persists; `item_add` has an unguarded N+1 reading the same
product's substances three times; and one open design question remained
about whether risk #4 needs a stored field. Digging further during
planning found risk #4 already has complete test coverage at both the unit
and real-view layers — that question turned out to need an answer, not a
test.

## Desired End State

A committed test proves that when two registry rows collide on
name/strength/form with no distinguishing producer, the item that gets
saved is the one the suggestion tiebreak actually offered — not
incidentally correct, but proven. `item_add`'s query count for a successful
add stops scaling with the added product's substance count, and a test
would catch it if that regression ever came back. The test-plan's cookbook
sections that pointed at this phase are filled in, and the "does risk #4
need a stored fact" question is answered in writing rather than left open.

## Key Decisions Made

| Decision | Choice | Why (1 sentence) | Source |
|---|---|---|---|
| Sortis-20 collision test | In scope, add it | It's risk #1's single highest-risk (High/High), most concrete reachable shape, and the fixture already exists one layer down | Plan (user-confirmed) |
| Risk #4 stored state | No schema change; confirm derived design | Existing coverage already proves the guard end to end at both unit and view layers, and the archived plan already rejected a stored boolean for drift reasons | Plan (user-confirmed) |
| N+1 fix shape | Inline prefetch on `ItemAddForm`, matching `ProductCheckForm` | Zero new abstraction for a two-line queryset only used in two places; matches existing convention exactly | Plan (user-confirmed) |
| Query-shape test pattern | Two-substance-count comparison, not a fixed literal | Matches `test_product_check.py`'s established pattern for proving a count is independent of a variable that used to scale it | Research + Plan |
| Risk #4 new test | None — cite existing coverage instead | `test_duplicates.py` and `test_item_list.py` already prove this at both layers; a third test would be cost without signal | Plan |

## Scope

**In scope:**
- One integration test driving the "Sortis 20" collision shape through `item_add`, proving both risk #1 and risk #3 for that shape.
- A one-line prefetch fix in `ItemAddForm` plus a query-shape test proving `item_add`'s query count no longer scales with substance count.
- A documentation-only phase confirming risk #4's existing coverage is complete, and filling in `test-plan.md`'s §6.1/§6.2/§6.6 cookbook entries.

**Out of scope:**
- Changing `registry/suggestions.py`'s tiebreak algorithm or resolving the underlying 1.24% substance-disagreement ambiguity.
- Any schema change (no stored `resolution_status` field).
- A new test for risk #4's grouping guarantee — it already exists twice over.
- A shared queryset helper between `ItemAddForm` and `ProductCheckForm`.
- Risks #2, #5, #6, #7 (later rollout phases), and the roadmap S-02 documentation gap.

## Architecture / Approach

No architecture changes. Three independently-committable sub-phases: a new
integration test (no production code), a one-line production fix plus its
proof (query-shape test), and a documentation-only closing phase. The
collision test reuses the exact fixture shape already pinned at the
`registry/suggestions.py` layer, driven one layer up through the real save
path. The N+1 fix relies on a fact already true of `ModelForm.save()`: the
`Product` instance assigned to `item.product` is the same prefetch-cached
instance `ModelChoiceField.clean()` returned, so a single form-level
prefetch fixes every downstream read with no view-level changes.

## Phases at a Glance

| Phase | What it delivers | Key risk |
|---|---|---|
| 1. Collision persistence test | Proves the suggestions-layer tiebreak's output is what `item_add` actually saves | Fixture drift if `_default_product`'s tiebreak logic changes without updating this test |
| 2. N+1 fix and query-shape assertion | `item_add`'s query count stops scaling with substance count, proven not asserted | A too-loose measurement (e.g. not holding household size constant) could mask a reintroduced N+1 |
| 3. Risk #4 confirmation and cookbook update | Written closure on the stored-fact question; cookbook entries filled in | None — documentation only |

**Prerequisites:** None beyond the existing test suite and fixtures already in the repo.
**Estimated effort:** Small — roughly one session across the three phases; no schema work, no new files beyond test additions.

## Open Risks & Assumptions

- The collision test's assertion depends on `_default_product`'s tiebreak staying "lowest `registry_id` wins" — if that rule ever changes, the test's expected values change with it (by design: it protects the connection between suggestions and persistence, not the specific tiebreak rule).
- The query-shape test's exact query count is not predicted in the plan; it will be recorded once observed during implementation, following `test_product_check.py`'s own convention.

## Success Criteria (Summary)

- A collision between two registry rows on name/strength/form no longer risks silently persisting the wrong row's identity untested — it's proven.
- Adding an item with several documented substances costs the same number of queries as adding one with a single substance.
- Nobody re-opens the "does risk #4 need a stored field" question without first reading why this phase closed it as no.
