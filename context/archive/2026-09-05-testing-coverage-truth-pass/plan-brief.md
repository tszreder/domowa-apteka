# Coverage Truth Pass — Plan Brief

> Full plan: `context/changes/testing-coverage-truth-pass/plan.md`
> Research: `context/changes/testing-coverage-truth-pass/research.md`

## What & Why

Phase 1 of the test-plan rollout (`test-plan.md` §3, row 1). This project has
already shipped tests that could not fail, so a green suite isn't evidence —
this phase proves which assertions claiming to protect risks #1–#6 actually
go red, writes that down as a durable map, and repairs the small number of
test-quality defects research found along the way.

## Starting Point

Research (`research.md`) ran seven falsification checks against live code.
The three historical "unfalsifiable test" repairs still hold (control
group). The one real gap that matters: risk #1 (wrong product identity
saved) has **zero falsifiable coverage** — all 228 tests stay green even
when the save path is forced to persist a different product than the one
posted. Risk #5 is covered, but by a different file than the one that reads
like its guardian. Two small test-quality defects exist in the parser test
suite. No risk-to-test map or falsification-ledger format exists anywhere
in the repo yet.

## Desired End State

A new `context/foundation/risk-test-map.md` gives an honest, at-a-glance
answer for each of risks #1–#6: is it covered, by what test, and how
strongly. The two sloppy parser tests are fixed. The cross-household test
file's docstring stops overclaiming what it proves. `test-plan.md`'s stale
stack numbers are corrected and its cookbook section points at the new map.

## Key Decisions Made

| Decision | Choice | Why (1 sentence) | Source |
| --- | --- | --- | --- |
| Repair scope | Fix the two cheap local test-quality defects now; leave risk #1/#3/#4's zero-coverage gaps for rollout Phase 2 | Phase 1's charter is verification, not new coverage — those gaps are Phase 2's stated job | Plan |
| Map location | Standalone `context/foundation/risk-test-map.md`, linked from `test-plan.md` §6.5 | The map grows across 5 rollout phases; a standalone file keeps each phase's diff local instead of repeatedly bloating the frozen strategy doc | Plan |
| Map granularity | Per-risk table as the primary artifact, per-mutation ledger kept as supporting evidence | Matches how a future reader actually queries it ("is risk #5 covered?"), without losing the exact measured provenance | Plan |
| `test-plan.md` §4 stale numbers | Correct them now, narrowly (15/178 → 17/228, "seam" → monkeypatch) | Demonstrably wrong today; the project's own lessons register says corrections must be written back, not left for a refresh | Plan |
| `_household_of` duplication | Record the testing consequence in the map only; no new lessons.md entry | Already found and consciously declined as a refactor in the 2026-08-14 review — re-raising it now would be scope creep | Plan |
| Falsification budget | Spend none of the remaining ~4-check budget on independently re-verifying risk #2/#6's flagged weak points | Research already fully explained both; further checks would drift toward risk #7, which is Phase 5's territory | Plan |

## Scope

**In scope:**
- New `risk-test-map.md` with a per-risk table + falsification ledger
- Fresh regression re-run of the three control-group mutations (R1–R3)
- Two test-quality repairs in `registry/tests/test_parser.py`
- One scope-correcting docstring in `households/tests/test_access_control.py`
- `test-plan.md` §4 correction and §6.5 fill-in

**Out of scope:**
- Closing risk #1/#3/#4's zero-coverage gaps (rollout Phase 2)
- Refactoring the `_household_of` duplication
- Independently re-verifying risk #2/#6's already-measured weak points
- Anything touching risk #7 (rollout Phase 5)
- Wiring the "falsification of new risk tests" gate into CI (becomes
  *recommended*, not required, after this phase)

## Architecture / Approach

No production code changes. This is a test-suite audit and documentation
phase: one new foundation-layer markdown file, two small test-file edits,
and one narrow, single-pass edit to the shared `test-plan.md`, sequenced so
the shared file is touched only once, last, after everything it needs to
reference already exists.

## Phases at a Glance

| Phase | What it delivers | Key risk |
| --- | --- | --- |
| 1. Falsification ledger & risk-to-test map | New `risk-test-map.md`, fully populated for risks #1–#6; R1–R3 re-verified red | A mutation left unreverted between checks would dirty the tree — mitigated by the explicit revert-and-verify-clean step between each |
| 2. Test-quality repairs | Two `test_parser.py` fixes, one `test_access_control.py` docstring | None — pure edits, no fixture or assertion-logic changes |
| 3. `test-plan.md` corrections & cookbook | §4 numbers corrected, §6.5 filled in and linked to the map | Touching a shared frozen file other worktrees may also be editing — bounded by naming exactly which two sections change |

**Prerequisites:** None beyond what already exists (research.md, this
worktree). **Estimated effort:** ~1 session across 3 phases — no new
fixtures or production code, mostly documentation and small edits.

## Open Risks & Assumptions

- The map's "knowingly uncovered" entries for risk #2 and #6 are inherited
  from research, not independently re-verified this phase — accepted
  tradeoff per the budget decision above.
- Risk #6's underlying product rule (invite expiry/revocation) is still an
  open roadmap question (S-01 Unknown 2); the map can only record it as
  unresolved, not close it.

## Success Criteria (Summary)

- `risk-test-map.md` exists and gives an honest answer for every risk #1–#6
- The full suite (228 tests) stays green through every phase
- `test-plan.md` §4 and §6.5 are corrected/filled in, and nothing else in
  that file changed
