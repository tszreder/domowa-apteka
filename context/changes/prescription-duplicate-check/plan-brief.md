# Prescription Duplicate Check — Plan Brief

> Full plan: `context/changes/prescription-duplicate-check/plan.md`

## What & Why

An adult standing in a doctor's office should be able to check a product they are about
to be prescribed against what the household already has at home — **without adding it to
the list**. Roadmap slice `S-05`. It is a third surface for a rule the PRD already
states (FR-003, §Business Logic), not a new claim: the app compares active-substance
sets, and says what is at home.

## Starting Point

The comparison rule already exists and needs no change. `pharmacy/duplicates.py` was
written set-keyed (`classify(a: frozenset[str], b: frozenset[str])`) rather than
item-paired, and its module docstring names *this slice* as the reason. The registry
search stack — `search_presentations` → `/suggestions/` → `autocomplete.js` — is also
complete. What is missing is the aggregation (one candidate against N household items),
a screen, and a picker that can live on a screen with no producer step.

## Desired End State

From the household list, `Sprawdź lek` opens a read-only screen. Type a name, pick a
suggestion, and see a flat, strongest-first list of what the household already holds
that shares the candidate's substances — each row labelled *the same product*, *the same
active substance*, or *a shared substance*, with strength, form and pack count. If the
candidate's substances cannot be established, the screen still confirms whether that
exact product is already at home — identity is a registry fact, not an inference — and
refuses only the substitute question. Nothing is ever written.

## Key Decisions Made

| Decision | Choice | Why (1 sentence) | Source |
| --- | --- | --- | --- |
| Entry point | Own screen at `/check/` | A distinct route is the smallest thing for `S-06`'s audit to relocate later. | Plan |
| Persistence | Purely transient `GET` | Makes "nothing was added" a structural fact rather than a promise in copy — no model, no migration. | Plan |
| Copy licence | State the fact, name no consequence | The roadmap's named risk is that "you already have this" sits one wording away from a substitution claim the app is not licensed to make. | Roadmap §S-05 |
| Unresolved candidate | Answer identity, refuse substitutes | A "no match" for a product we failed to resolve is a buy signal built on a guess — but *is this the same product?* is settled by primary key, so suppressing it would be its own wrong answer. | Plan |
| Producer step | None — compare at presentation level | User decision; the substances used are displayed so the comparison is visible even in the 1.24% of groups whose rows disagree. | Plan |
| Answer content | Name, strength/form, pack count; shared substances only on partial matches | A flag settles a comparison but not a decision; pack count is the field that does. | Plan |
| Result shape | One flat list, each row labelled | User decision; shortest screen, no empty-section logic. | Plan |
| Unresolved household items | Disclosed as a count, not silently dropped | Symmetric with the candidate refusal — a "nothing matches" verdict over unresolved stock overstates what we know. | Plan |
| Picker | Extract a shared search module from `autocomplete.js` | One answer to "how does product search behave" instead of two that drift; sequenced last because CI cannot observe it. | Plan |
| Test depth | Behaviour + query shape + both refusals + no-write | The dangerous failures here are a silent "no match" and a read screen that writes. | Plan |

## Scope

**In scope:** one pure comparison function; a `GET`-only `/check/` view, form and
template; Polish copy held to a substance-set fact; an entry link on the household list;
a shared JS search module with the add screen rewired onto it; unit, integration,
query-shape and script-order tests.

**Out of scope:** any persistence (no `CheckLog`, no session history); expiration dates
(`S-04` parked — but `CandidateMatch.items` is left as the seam); producer
disambiguation on this screen; therapeutic-effect matching; changes to the duplicate
rule; a JS test toolchain; any list-screen redesign (`S-06` owns that).

## Architecture / Approach

```
item_list.html ──link──▶ /check/  ──?product=<id>──▶ product_check (GET, no writes)
                                                          │
                         ProductCheckForm ◀──validates─────┤
                                                          ▼
                          check_candidate(candidate, items)  ← composes the existing
                                   │                            substance_keys + classify
                                   ▼
                          CandidateCheck { candidate_substances, matches[], uncomparable_count }
                                   │
                                   ▼
                          product_check.html  (flat labelled list · two refusal shapes · disclosure)

product-search.js ──used by──▶ autocomplete.js (add: fills hidden fields)
                  └─used by──▶ check.js       (check: navigates on pick)
```

## Phases at a Glance

| Phase | What it delivers | Key risk |
| --- | --- | --- |
| 1. The rule | `check_candidate()` in `pharmacy/duplicates.py` + unit tests | Restating the comparison instead of composing `classify`; letting the identity test depend on substance resolution |
| 2. The check screen | View, form, URL, template, copy, list link + full integration coverage | Copy drifting into a substitution claim; a refusal rendered as a "no match", or a total refusal where a partial one is owed |
| 3. Shared search module | `product-search.js`, add screen rewired, `check.js` | Regressing the north star's add flow — **no automated test in this repo can see it** |

**Prerequisites:** `S-03` (`duplicate-flagging-on-list`) shipped and archived —
satisfied. No new dependencies, no migration, no platform work.

**Estimated effort:** ~2–3 evening sessions across the three phases. Phase 2 is the
largest; Phase 1 is small because the rule it composes already exists.

## Open Risks & Assumptions

- **Presentation-level comparison.** In the 1.24% of presentation groups whose rows
  disagree on substances (measured during `F-01`, recorded in
  `registry/suggestions.py:82`), the comparison runs on the tiebreak default product
  rather than a producer the user confirmed. Accepted deliberately; mitigated by showing
  which substances were compared, not by adding a producer step.
- **Phase 3 has no automated safety net.** `test-plan.md` §4 records `e2e: none yet`, so
  the add-flow regression sweep is a human checklist. This is why Phase 3 runs last and
  is explicitly droppable — Phases 1–2 ship a working screen without it.
- **The framing will be read as advice anyway.** The screen states a fact and names no
  consequence, but a household will draw a purchase conclusion from it. We accept that
  rather than authoring it.
- **`assertNumQueries` constant unstated.** The plan specifies asserting *equality*
  across a 2-item and a 12-item household rather than predicting the absolute number;
  the constant is recorded when the implementation settles.

## Success Criteria (Summary)

- A user can check a prescribed product against the household list and get a correct,
  labelled answer without anything being added.
- A product whose substances cannot be established is still confirmed as already at home
  when it is, and otherwise produces an explicit refusal — never a "no match".
- The add flow behaves exactly as it did before Phase 3 touched its JavaScript.
