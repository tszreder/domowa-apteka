# Add a Drug and See Its Active Substance(s) Resolved — Plan Brief

> Full plan: `context/changes/add-drug-with-substance-resolution/plan.md`

## What & Why

Roadmap item **S-02** — the north star. A household member types a pharmaceutical's
name, picks it from registry-backed autocomplete, and the app records which active
substance(s) it contains, or says plainly that it could not tell. The item appears on
the shared household list. This is the one claim in the PRD that has never been tested
against reality: if a real brand name a household would type cannot be resolved to a
substance set they would recognise, duplicate flagging has nothing to compare and the
product has no reason to exist.

## Starting Point

Both prerequisites are `done` and real. `registry` holds 20,245 active products, 3,391
substances and 25,884 links in production Postgres, each link carrying a `source_field`
provenance marker. `households` has auth, `Household`, `Membership`, and a
`household_required` decorator. What is missing is any item model at all — `/list/` is
a placeholder view rendering the string *"no medicines added yet"*, and because
`LOGIN_REDIRECT_URL` points at it, that placeholder is the first page every user sees.

## Desired End State

A member types `grip`, sees real registry presentations with strength and form, picks
one, optionally narrows to the producer printed on the box, and saves. The item lands
on the household list showing its active substances. Members of the same household see
it on their next page load; members of another household never do. A product the
registry has no substances for still saves, warns the user, and displays in a distinct
unresolved state. Items can be deleted.

## Key Decisions Made

| Decision | Choice | Why (1 sentence) |
| --- | --- | --- |
| Change ID | Renamed folder to `add-drug-with-substance-resolution` | Roadmap sync and `/10x-archive` match on exact string; the old name would have left the north star reported as `proposed` forever. |
| App placement | New `pharmacy` app | Items are neither reference data (`registry`) nor identity (`households`); S-03 and S-04 get an obvious home. |
| Entry mode | Autocomplete-only, free text a later migration | Non-null product FK means every item traces to a source row, and "lookup failed" narrows to one honest case. |
| Suggestion unit | One row per `(name, strength, form)` | 20,245 products collapse to 16,191 presentations — `Concor Cor 2,5` alone repeats 28 times, so a raw-row picker offers 28 indistinguishable options. |
| Producer field | Optional, type-to-narrow, inlined in the payload | Only 6.2% of groups have >1 producer and none has more than 10, so ~2 KB of inlined data removes a whole round-trip. |
| Default product | Prefer a row with substances, then lowest `registry_id` | Avoids reporting "unknown" for products whose sibling row resolves fine (`Peditrace`, `Moviprep`); `registry_id` is stable across re-imports, pks are not. |
| Producer on the list | Stored `producer_confirmed` flag; shown only when true | The product FK alone can't tell "user picked Merck" from "Merck was the tiebreak default" — displaying it either way would show a 1-in-8 guess as fact. Auto-true for single-holder groups, so the template stays a boolean read. |
| Unresolved items | Saved, warned about, displayed distinctly | The only reading that satisfies US-01 ("failure visible") and US-03 ("shown separately") together — 428 groups genuinely have zero substances. |
| Substance storage | Derived live through the product FK | Always matches the registry, per the freshness NFR; F-01's `PROTECT` + keep-and-mark-inactive were designed to make this safe. |
| Transport | JSON endpoint + ~30 lines of vanilla JS | Feels like autocomplete with zero new dependencies and no build step, in the slice already carrying the most risk. |
| Operations | Add + delete, no edit | A mistyped entry must be recoverable; S-04 will reopen the edit surface anyway to add its date field. |
| Tests | Model + view + endpoint, hand-built fixtures | Matches the existing `households/tests/` bar and keeps CI offline like F-01's suite. |
| Performance | Nothing added speculatively; Phase 2 measures first | A bounded `icontains` query ran in 0.5–10 ms, but the grouped search has a different shape and is unmeasured — so the plan schedules the measurement instead of asserting the number transfers. |

## Scope

**In scope:** a `pharmacy` app with an `Item` model (including a `producer_confirmed`
flag); moving `item_list` into it while
keeping the `/list/` path; `registry/suggestions.py` owning presentation grouping and
the default-product tiebreak; a JSON suggestion endpoint; the add form with
autocomplete and an optional producer field; the unresolved-save path; POST-only
delete; a nav link.

**Out of scope:** duplicate flagging (S-03); expiration dates (S-04); editing an item;
free-text entry of drugs absent from the registry; scheduled refresh (F-02);
real-time updates; quantity, dosage, notes, barcode; any change to `registry`'s models
or import pipeline; substance search; speculative query tuning.

## Architecture / Approach

`pharmacy` reads `registry`; `registry` never imports `pharmacy` — the same one-way
dependency F-01 established between its pure parser and its dumb loader.

```
pharmacy (user data)                     registry (reference data)
  Item ──FK──────────────────────────────▶ Product ──▶ ProductSubstance ──▶ Substance
    household, added_by, added_at
    views: item_list, item_add,   reads
           item_delete,          ───────▶  suggestions.py  [pure queries]
           product_suggestions                presentation grouping
                                               producers + default-product tiebreak
```

There is no item→substance table: substances are read through the product FK at
display time. The grouping and tiebreak rules — the correctness-critical part of this
slice — live in a pure query module with no HTTP attached, so they are testable in
isolation. By the time the form is submitted, the user's choice has already collapsed
to a single `Product` id, keeping the form trivial.

## Phases at a Glance

| Phase | What it delivers | Key risk |
| --- | --- | --- |
| 1. App + `Item` + list | `pharmacy` app, model, migration, list view moved from `households`, unresolved rendering | Moving the view renames `households:item_list`, touching 6 existing test references; forgetting the prefetch turns the list into N+1 |
| 2. Search + endpoint | `registry/suggestions.py` grouping and tiebreak, JSON endpoint, tests, and the first real timing of the grouped query | The tiebreak is the slice's correctness core — the naive "lowest id" rule reports false "unknown" for measured products; and grouping cannot be sliced in SQL naively, so the query shape is unmeasured |
| 3. Add flow | Form, view, templates, autocomplete JS, producer control, unresolved message | The only hand-written JS: stale responses, and a stale product id surviving an edited search box |
| 4. Delete + verification | POST-only scoped delete, nav link, end-to-end manual pass | This is the first real test of the product's central claim; a GET-based delete would let a prefetcher wipe a list |

**Prerequisites:** F-01 and S-01, both `done`; registry data already live in
production Postgres, so no data step is needed to deploy.
**Estimated effort:** ~3 sessions. Phase 3 is the largest (the only JavaScript);
phases 1 and 4 are small.

## Open Risks & Assumptions

- **Salt-form variants defeat set equality.** `Sortis 20` resolves to `atorvastatinum`
  in one row and `atorvastatinum calcicum` in another, so S-03 will miss that class of
  true duplicate. Merging the names would be inferring an identity the source does not
  state — banned by the NFR. Recorded as an accepted limitation, measured at 201 of
  16,191 groups (1.24%).
- **The tiebreak picks one of two defensible answers** in those groups when no producer
  is chosen. Deterministic, not "correct". `producer_confirmed` keeps that
  arbitrariness off the screen but the item is still linked to the tiebreak row, so its
  substances come from there.
- **The performance measurement covers a bounded query, not the grouped search.**
  `icontains` with a SQL `LIMIT 10` ran in 0.5–10 ms on SQLite dev, but
  `search_presentations` must group before it can slice, so that number does not
  transfer. Phase 2 measures the real shape with a worst-case 2-character query before
  any conclusion is drawn. Postgres parity is separately an inference, not a
  measurement — both stated as such per `lessons.md`.
- **Hand-built fixtures could encode a wrong assumption**, mitigated by building each
  one to reproduce a shape measured against the real data and naming it after that shape.
- **Drugs absent from the registry cannot be recorded in v1** — the accepted cost of
  autocomplete-only entry.
- **Substances can change under the user** when a re-import corrects a product. This is
  the freshness NFR working as designed, but it means what was shown at add time is not
  a permanent record.
- **Autocomplete requires JavaScript.** No non-JS path to picking a product ships in v1.

## Success Criteria (Summary)

- A member types a real brand name, picks it, and sees the active substance(s) a
  household would recognise — the north star, verified by hand against the real 20k-row
  snapshot.
- A product the registry cannot resolve is saved, flagged to the user, and shown
  distinctly — never dropped, hidden, or guessed at.
- Items are visible to every member of the owning household on ordinary navigation, and
  to no one outside it.
