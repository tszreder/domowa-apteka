# Duplicate flagging on the household list — Plan Brief

> Full plan: `context/changes/duplicate-flagging-on-list/plan.md`

## What & Why

Roadmap slice **S-03** — the payoff the whole product is built around. A household buys
duplicate medicine because a plain list cannot tell them "Apap" and "Paracetamol Hasco"
are the same drug. Every item on the list already resolves to a set of active substances;
this change compares those sets and shows the result, so identical sets surface as full
duplicates (zamienniki), overlapping-but-different sets surface as partial duplicates, and
unresolved items are held out of the comparison entirely.

## Starting Point

The data path is complete and needs no migration: `Item` → `Product` → `substance_links`
→ `Substance`, with the list view already prefetching every substance it would compare
(`pharmacy/views.py:27-29`). `item.unresolved` already exists. The list renders a flat
`<ul>` in newest-first order with a `.unresolved` class on unflagged rows. What is missing
is only the comparison rule and its presentation.

Notably, F-01 already built a guard **for this slice specifically**:
`registry/denylist.py:6-9` keeps registry category words like `Produkt złożony` out of the
substance vocabulary, because loading them would make "every product carrying it a
full-substance-set duplicate of every other one, so S-03 would confidently flag 78
unrelated medicines as identical."

## Desired End State

Opening the household list, an adult sees items with identical substance sets grouped into
one visible cluster; items that overlap but differ carrying an expandable badge reading
*"Wspólna substancja: …"*; and items whose substances could not be resolved in their own
section below, carrying no duplicate flag at all. The screen issues the same 7 queries it
does today.

## Key Decisions Made

| Decision | Choice | Why (1 sentence) |
| --- | --- | --- |
| Display shape | Group full duplicates, badge partial ones | Identical-set is an equivalence relation and partitions cleanly; partial overlap is not transitive, so sectioning it would force a row to be duplicated or arbitrarily assigned. |
| Same-product repeats | Flagged, but labelled distinctly | Two boxes of one product *is* useful to know, but calling it "zamiennik" is wrong in Polish and makes the flag read as noise on the most common case. |
| Compute strategy | Derive on read, primitive keyed on substance **sets** | Cannot go stale when F-02's daily refresh changes a substance set, needs no migration — and the set-keyed shape is what the planned prescription check reuses instead of reimplementing. |
| Partial badge content | Partner names collapsed, per-substance breakdown on expand | Keeps a combination product's many partners from making the list unreadable while still answering *why* on demand. |
| Unresolved items | Own section, below the list | Once neighbouring rows are visibly clustered, an unflagged inline row reads as "checked, no duplicates" rather than "not checked". |
| Containment vs crossing overlap | Both render as plain partial | Exactly as FR-003 and US-03 word it; containment can be added later as a refinement of an existing flag. |
| Testing depth | Unit + integration + falsification | This project has already shipped three tests that could not fail, and here a wrong flag is a wrong medical claim. |

## Scope

**In scope:** the comparison primitive; full-duplicate clustering with the same-product
label distinction; partial-overlap badges; the unresolved section; CSS for both; unit and
integration tests with a recorded falsification each.

**Out of scope:** persisting duplicate relationships; dismissing a flag; distinguishing
containment in the UI; sort/filter controls; a strength-mismatch caveat; the prescription
check; re-implementing the substance denylist; editing `test-plan.md`.

## Architecture / Approach

A new `pharmacy/duplicates.py` holds the whole rule as pure functions with no HTTP
attached — the shape `registry/suggestions.py` established so correctness is testable in
isolation. `substance_keys(product) -> frozenset[str]` reads prefetched links and keys on
`Substance.name_key` (the identity; `name` is display-only). `classify(a, b) -> Overlap`
returns `FULL | PARTIAL | NONE`. A list-level builder partitions unresolved items out,
clusters the rest by identical set, and computes partial partners *between clusters*. The
view passes the builder's output to the template; the template contains no comparison
logic and the view contains no loop.

## Phases at a Glance

| Phase | What it delivers | Key risk |
| --- | --- | --- |
| 1. Comparison primitive | `pharmacy/duplicates.py` + unit tests; no user-visible change | The empty-set trap — `frozenset() == frozenset()` is `True`, so a naive rule groups every unresolved item together |
| 2. Grouping + unresolved section | Full duplicates clustered on screen; unresolved split out | Regressing the `assertNumQueries(7)` contract by touching links outside the prefetch cache |
| 3. Partial-overlap badges | `<details>` badge with per-substance breakdown, plus CSS | The "reads as noise" failure — correct flags that make the screen feel like a warning wall |

**Prerequisites:** S-02 (done, archived). No new dependencies, no migration, no infra.
**Estimated effort:** ~3 evenings, one per phase. Phase 2 ships value standalone, so
phase 3 is the slippable one against the 2026-09-14 deadline.

## Open Risks & Assumptions

- The roadmap warns this slice "is judged on feel rather than correctness" — a technically
  correct partial-duplicate flag that reads as noise fails US-03. Phase 3's manual
  criteria are the only guard against that, and they are judgement calls.
- Assumes the upstream denylist holds. If a category word ever reaches the substance
  vocabulary, this slice will confidently group unrelated medicines — the failure would
  surface here but the fix belongs in F-01.
- O(n²) pairing is immaterial at household scale and would need revisiting only at
  thousands of items, which `target_scale: small` does not anticipate.
- This slice fires two `test-plan.md` §7 re-evaluation triggers and brings §4's deferred
  multimodal row due. Foundation docs are not hand-edited — run `/10x-test-plan --refresh`
  after this change archives.

## Success Criteria (Summary)

- Two differently-named boxes resolving to the same substance set are visibly presented as
  the same drug, without the user having to read substance names to notice.
- A combination product shows which items it partially overlaps and which substance drove
  each match.
- An item whose substances could not be resolved is never grouped with anything — including
  with another unresolved item.
