# Coverage Truth Pass — Implementation Plan

## Overview

This is Phase 1 of the §3 Phased Rollout in `context/foundation/test-plan.md`.
Its job is verification, not new coverage: produce a written risk-to-test map
proving which existing assertions actually protect risks #1–#6, invent the
falsification-ledger format the project has never had, and repair the small
number of test-quality defects research already found — without duplicating
rollout Phase 2's charter of building new coverage for risk #1/#3/#4's gaps.

## Current State Analysis

`context/changes/testing-coverage-truth-pass/research.md` (2026-09-05,
commit `ffa7f2f`) ran seven falsification checks against live code and
measured the following, all still current (this worktree is one commit ahead,
adding only the research doc itself):

- The three tests named in `test-plan.md` §1 principle #4 as "shipped tests
  that could not fail" are **already repaired** (fixed in three prior
  archived changes) and **re-verified red** in this research pass (R1, R2,
  R3). They are a control group, not a discovery.
- **Risk #1 has zero falsifiable coverage** at the save layer (N2): forcing
  `item_add` to save a different product than the one posted leaves all 228
  tests green. Closing this is rollout Phase 2's stated charter
  (`test-plan.md` §3 row 2, "Add-item integrity", risks #1/#3/#4) — not this
  phase's.
- **Risk #5 is covered, but the file that reads like its guardian isn't
  where the guard lives.** `households/tests/test_access_control.py` stays
  green under a live cross-household item leak (N1b); the assertions that
  actually redden are in `pharmacy/tests/test_item_list.py` and
  `test_product_check.py` (N1b′).
- Two test-quality defects exist in `registry/tests/test_parser.py`: a
  tautological assertion on a module constant (line 249) and a test whose
  name overclaims what it checks (lines 251–254, checks the post-filter
  output, not the internal vocabulary its name names).
- No falsification-ledger or risk-to-test-map artifact exists anywhere in
  the repo. The only precedent is ad-hoc `Mutation-checked:` prose inside
  archived `impl-review.md` files.
- `test-plan.md` §4's stack numbers are stale: it records "15 test modules,
  178 test methods" against a measured 17 modules / 228 methods, and
  describes the import command's clock control as an "injected seam" when
  it is monkeypatching (`test_freshness.py:86` patches the module
  attribute directly; `timezone.now()` is not called through an injectable
  wrapper).

### Key Discoveries:

- `registry/tests/test_parser.py:248-249` — the real behavior assertion
  (`product.links == ()`) already exists on line 248; line 249
  (`assertIn('produkt złożony', DENYLISTED_SUBSTANCE_KEYS)`) adds nothing
  falsifiable about parser behavior and can simply be removed.
- `registry/tests/test_parser.py:251-254` — `parser.py:164-171` deliberately
  lets the internal vocabulary accumulate denylisted keys before
  `_resolve_deferred` blocks them at `parser.py:287`; the test's current name
  claims to check "the substance vocabulary" but its assertion is over
  `self.result.substances`, the post-filter output. This is a naming
  mismatch, not a behavioral gap — the deliberate no-op at 164-171 needs no
  test of its own (research: "worth recording as a deliberate no-op, not
  worth a falsification check").
- `households/tests/test_access_control.py:26-32` —
  `test_item_list_only_ever_resolves_own_household` proves household
  *resolution* is scoped to the logged-in user (no `Item` exists for
  `household_a` in `setUp`, so `assertNotContains` cannot observe item-level
  leakage). The real item-leak guard lives in
  `pharmacy/tests/test_item_list.py::test_item_in_household_a_never_appears_for_member_of_household_b`
  and `pharmacy/tests/test_product_check.py`.
- `_household_of` is duplicated verbatim in `households/views.py:21` and
  `pharmacy/views.py:20` (raised as F5 in the 2026-08-14 review, consciously
  declined as a refactor). A falsification of one copy says nothing about
  the other — this phase records that consequence in the map; it does not
  touch the duplication.

## Desired End State

- `context/foundation/risk-test-map.md` exists, giving an honest per-risk
  answer for risks #1–#6 ("is this covered, by what, how strongly") backed
  by a per-mutation falsification ledger, and is linked from `test-plan.md`
  §6.5.
- The two test-quality defects in `registry/tests/test_parser.py` are fixed;
  `households/tests/test_access_control.py` states in a docstring what it
  actually proves.
- `test-plan.md` §4 shows the current, correct stack numbers and an accurate
  description of the clock-control mechanism; §6.5 states the convention for
  recording a falsification and points at the map.
- The full suite is green (228 tests) after every change, and the tree is
  never left mid-mutation.

**Verification**: `uv run manage.py test` reports the same test count as
before this phase started (no test was deleted, one was renamed); a human
reads `risk-test-map.md` against `research.md` and confirms no risk's status
in the map overstates what research measured.

## What We're NOT Doing

- Not closing risk #1's zero-coverage gap with a new collision fixture —
  that is rollout Phase 2's charter (test-plan.md §3 row 2).
- Not closing risk #3's unobserved fallback-spelling gap (N3) or risk #4's
  untested `required`-field branch — both deferred to rollout Phase 2, which
  also covers risks #3 and #4.
- Not refactoring the `_household_of` duplication — declined in the
  2026-08-14 review; this phase only records its testing consequence in the
  map.
- Not independently re-verifying risk #2's `PlausibilityGuardTests` weak
  point (only tested via an artificially-lowered threshold) or risk #6's
  invite login-path gap beyond what research already measured — both are
  recorded in the map as-is, per the agreed falsification-budget decision.
- Not touching risk #7 — that is rollout Phase 5.
- Not wiring the "falsification of new risk tests" gate into CI — `test-plan.md`
  §5 records it becoming *recommended* after this phase, not required.
- Not editing `test-plan.md` §1, §2, §3, §5, §7, or §8 — only §4 and §6.5.

## Implementation Approach

Three phases, ordered so the shared frozen file (`test-plan.md`) is touched
exactly once, last, after the artifact it needs to reference (the map) and
the repairs it needs to describe both already exist.

## Critical Implementation Details

**Falsification check safety.** Phase 1 (this plan's first phase) reapplies
three code mutations from `research.md`'s ledger to get a dated regression
result. Apply one mutation, run its named target module, confirm the exact
failure signature research recorded, revert with `git diff` / `git checkout
-- <file>`, and confirm `git status --porcelain` is empty before starting the
next mutation. Never run the next check while a previous mutation is still
applied, and never end the phase with `git status` non-clean.

**Why `risk-test-map.md` is a foundation file `/10x-plan` doesn't normally
touch.** AGENTS.md reserves `context/foundation/*.md` for the `/10x-*` skill
chain. `test-plan.md` §6.5 already promises this map as its own canonical
deliverable ("becomes the canonical answer to ... where the risk-to-test map
lives"), and the module's own CLAUDE.md states rollout-phase plans are
expected to update `test-plan.md` §6 as they ship. Creating the file this
phase points at, and linking it from §6.5, is that contract being fulfilled
by the rollout chain (`/10x-new` → `/10x-research` → `/10x-plan` →
`/10x-implement`), not a bypass of it.

## Phase 1: Falsification Ledger and Risk-to-Test Map

### Overview

Create the map artifact, get a fresh dated regression result for the three
control-group mutations, and populate the map's per-risk table with an
honest status for each of risks #1–#6 drawn from `research.md`'s measured
findings.

### Changes Required:

#### 1. Regression re-run of the three control-group mutations

**File**: none changed (a run-verify-revert cycle against live code)

**Intent**: Get a dated, this-worktree confirmation that the three historical
"unfalsifiable test" repairs still hold, to record in the ledger as today's
evidence rather than citing research.md's numbers again.

**Contract**: Reapply each of `research.md`'s R1, R2, R3 mutations exactly as
that table specifies (file:line, before → after), run the paired target
module named in the same row, confirm the failure signature matches (same
test name / line, same failure count), then revert and confirm a clean tree
before moving to the next one.

#### 2. New file: the risk-to-test map

**File**: `context/foundation/risk-test-map.md`

**Intent**: The single place a future contributor or `/10x-research` run
checks to answer "is risk N covered, by what, and how strongly?" — replacing
line coverage as this project's coverage metric, per `test-plan.md` §1
principle #4 and §4's "coverage measurement" row.

**Contract**: A markdown file with:

1. A short header stating its purpose and that it is maintained by each
   rollout phase's `/10x-implement` step (mirroring `test-plan.md`'s own
   "last updated" convention).
2. A **per-risk table** — columns: Risk #, Risk (one line), Status (Covered /
   Partially covered / Structurally prevented / Knowingly uncovered), the
   test file(s)::method(s) that actually provide the falsifiable assertion
   (or "none" for risk #1), and a Note column citing anything a reader needs
   to know before trusting the Status cell. Populate all six rows now, using
   the Key Discoveries above and `research.md`'s "Detailed Findings by Risk"
   section as the source — in particular:
   - Risk #1: Status "Not yet covered"; test column "none"; Note points at
     rollout Phase 2 as the owner.
   - Risk #2: Status "Covered, one weak point"; test column names
     `test_import_run.py` and `test_loader.py`'s relevant classes; Note
     flags `PlausibilityGuardTests` as untested against a genuinely short
     well-formed file, per the agreed decision not to close this now.
   - Risk #3: Status "Partially covered"; test column names
     `DroppedRowNumberingTests`; Note flags the unobserved fallback-spelling
     rule at `parser.py:289` (N3) as deferred to rollout Phase 2.
   - Risk #4: Status "Structurally prevented, one branch untested"; test
     column names the schema-level guarantee (`ItemAddForm.product` as a
     required `ModelChoiceField`); Note flags the untested "no product
     posted" branch as deferred to rollout Phase 2.
   - Risk #5: Status "Covered, not where it looks"; test column names both
     the misresolution guard (`test_access_control.py`, post-Phase-2 repair
     docstring) and the real item-leak guard
     (`pharmacy/tests/test_item_list.py`, `test_product_check.py`); Note
     records the `_household_of` duplication consequence.
   - Risk #6: Status "Knowingly uncovered"; test column names
     `test_invites.py`'s session-hygiene coverage; Note states the login
     path is untested by an accepted 2026-08-05 review decision and that the
     underlying product rule (roadmap S-01 Unknown 2) is still unrecorded,
     so there is no oracle to test against yet.
3. A **falsification ledger** (supporting evidence) — the per-mutation table
   from `research.md`'s "The Falsification Ledger" section, reproduced with
   a `Date` column, plus the three freshly re-run rows from step 1 of this
   phase dated today. Future rollout phases append rows here rather than
   duplicating them into the per-risk table.
4. A short **"How to record a falsification"** convention paragraph (the
   content that `test-plan.md` §6.5 will link to): identify the assertion,
   apply the smallest mutation that breaks exactly the behavior it claims to
   protect, run the narrowest containing module, confirm the expected
   failure, revert, confirm a clean tree, then add one row to the ledger. If
   the assertion does not redden, it is not falsifiable — repair it or
   record the gap honestly; never mark the risk "covered."

### Success Criteria:

#### Automated Verification:

- [ ] 1.1 Full suite passes: `uv run manage.py test` (228 tests)
- [ ] 1.2 Each of R1, R2, R3 independently confirmed red when reapplied,
      then reverted: `git status --porcelain` is empty after this step
- [ ] 1.3 `context/foundation/risk-test-map.md` exists and contains a row
      for every risk #1–#6

#### Manual Verification:

- [ ] 1.4 A human reads the per-risk table against `research.md` and
      confirms no Status cell overstates what was measured

---

## Phase 2: Test-Quality Repairs

### Overview

Fix the two defects research found in `registry/tests/test_parser.py`, and
correct `households/tests/test_access_control.py` so it states honestly what
it proves. No fixtures added, no behavior changed — these are edits, not new
coverage.

### Changes Required:

#### 1. Remove the tautological assertion

**File**: `registry/tests/test_parser.py`

**Intent**: `test_denylisted_common_name_blocks_the_fallback` already proves
the fallback is blocked via `self.assertEqual(product.links, ())` on line
248; line 249's `self.assertIn('produkt złożony', DENYLISTED_SUBSTANCE_KEYS)`
checks a static module constant and contributes nothing falsifiable about
parser behavior.

**Contract**: Delete line 249. The test's remaining assertion is unchanged
and still proves the same behavior it always did.

#### 2. Rename the scope-overclaiming test

**File**: `registry/tests/test_parser.py`

**Intent**: `test_denylisted_names_never_reach_the_substance_vocabulary`
(lines 251-254) asserts over `self.result.substances` — the post-filter
output — never the internal `vocabulary` dict its name names. The internal
vocabulary deliberately still accumulates denylisted keys before
`_resolve_deferred` blocks them (`parser.py:164-171`, `:287`); that is a
documented no-op, not a bug, so the test's name should describe what it
actually checks.

**Contract**: Rename the method to
`test_denylisted_names_never_reach_the_resolved_substances`. Add a one-line
comment above the assertion noting that the internal vocabulary intentionally
still holds denylisted keys (`parser.py:164-171`) and that this test checks
the post-resolution output where they're actually blocked
(`parser.py:287`). No assertion logic changes.

#### 3. Scope-correct the cross-household test file

**File**: `households/tests/test_access_control.py`

**Intent**: The file and its `CrossHouseholdIsolationTests` class read as the
general cross-household guardian. Research measured that it stays green
under a live item-level leak (N1b) — it proves household *resolution* is
scoped to the current user, not that household-owned records never leak. A
future reader should not mistake this file's green suite for proof of
item-level isolation.

**Contract**: Add a class docstring to `CrossHouseholdIsolationTests` stating
what it proves (household resolution is scoped to the logged-in user's own
membership) and what it does not (item-level or other household-owned-record
leakage), pointing at
`pharmacy/tests/test_item_list.py::test_item_in_household_a_never_appears_for_member_of_household_b`
and `pharmacy/tests/test_product_check.py` as where that guarantee is
actually proven. No test logic changes.

### Success Criteria:

#### Automated Verification:

- [ ] 2.1 `uv run manage.py test registry.tests.test_parser` passes
- [ ] 2.2 `uv run manage.py test households.tests.test_access_control` passes
- [ ] 2.3 Full suite passes: `uv run manage.py test` (228 tests — same
      count; one test renamed, none added or removed)
- [ ] 2.4 `uv run mypy` still succeeds

#### Manual Verification:

- [ ] 2.5 The renamed test's new name accurately describes its assertion
- [ ] 2.6 `test_access_control.py`'s new docstring accurately scopes what the
      file proves, cross-referencing the files that prove the rest

---

## Phase 3: `test-plan.md` Corrections and Cookbook Fill-In

### Overview

The one deliberate touch to the shared frozen file this phase makes: correct
§4's stale numbers and fill in §6.5 with the falsification convention and a
link to the new map. Done last, after the map exists and the repairs are
complete, so the edit is accurate and singular.

### Changes Required:

#### 1. Correct the §4 stack table

**File**: `context/foundation/test-plan.md`

**Intent**: §4 records "15 test modules, 178 test methods" against a
measured 17 modules / 228 methods (research.md, this worktree), and
describes the import command's clock control as an "injected clock seam"
when `test_freshness.py:86` patches `timezone.now` directly — monkeypatching,
not an injectable seam. Per the project's own lessons register ("A plan can
contradict itself; resolve it in code *and* write the resolution back"), a
demonstrably wrong number in a document three more rollout phases will read
should be corrected, not left for a refresh.

**Contract**: In the `unit + integration` row, change "15 test modules, 178
test methods" to "17 test modules, 228 test methods (measured
2026-09-05)". In the `clock control` row, change "injected clock seam" to
"monkeypatched clock (`timezone.now` patched directly in tests; not an
injectable seam)" and drop the "already established" framing accordingly.
No other §4 content changes.

#### 2. Fill in §6.5

**File**: `context/foundation/test-plan.md`

**Intent**: §6.5 currently reads "TBD — see §3 Phase 1." This phase's
falsification convention and map location are exactly what it promises to
become the canonical answer to.

**Contract**: Replace the `TBD` line with: a link to
`context/foundation/risk-test-map.md` as where the risk-to-test map and
falsification ledger live, and a short restatement of the "How to record a
falsification" convention written into that file in Phase 1 (identify the
assertion → smallest breaking mutation → narrowest module → confirm the
failure → revert → record the ledger row). Keep it to a few lines; the full
convention text lives in the map file, not duplicated here.

### Success Criteria:

#### Automated Verification:

- [ ] 3.1 `git diff context/foundation/test-plan.md` touches only §4 and
      §6.5 (no other section changed)
- [ ] 3.2 Full suite passes one final time: `uv run manage.py test` (228
      tests)

#### Manual Verification:

- [ ] 3.3 A human reads the corrected §4 numbers and confirms they match a
      fresh `uv run manage.py test` count
- [ ] 3.4 A human reads the new §6.5 text and confirms it's enough to follow
      without opening `risk-test-map.md` first

---

## Testing Strategy

### Unit Tests:

- No new unit tests are written this phase (verification and repair only).
- Existing suite (`registry.tests.test_parser`,
  `households.tests.test_access_control`) must stay green through the Phase
  2 edits.

### Integration Tests:

- None added. The three mutation/revert cycles in Phase 1 are the
  integration-level verification this phase performs, not new tests.

### Manual Testing Steps:

1. After Phase 1, read `risk-test-map.md` end to end against
   `research.md` and confirm every Status cell is honest.
2. After Phase 2, read the diff on both test files and confirm no assertion
   logic changed, only names/comments/docstrings.
3. After Phase 3, read the `test-plan.md` diff and confirm it is exactly
   the two sections named above.

## Performance Considerations

None — no production code changes, no new fixtures, no new queries.

## Migration Notes

None — no model or schema changes.

## References

- Research: `context/changes/testing-coverage-truth-pass/research.md`
- Strategy this phase implements: `context/foundation/test-plan.md` §1
  principle #4, §3 row 1, §6.5
- Historical repairs re-verified: `households/tests/test_invites.py:48`,
  `households/tests/test_access_control.py:17-24`,
  `registry/tests/test_parser.py:177` (`DroppedRowNumberingTests`)
- Prior review findings this phase records rather than fixes:
  `context/archive/2026-08-14-add-drug-with-substance-resolution/reviews/impl-review.md`
  (F5, `_household_of` duplication)

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles.

### Phase 1: Falsification Ledger and Risk-to-Test Map

#### Automated

- [ ] 1.1 Full suite passes: `uv run manage.py test` (228 tests)
- [ ] 1.2 R1, R2, R3 each independently confirmed red then reverted; clean tree
- [ ] 1.3 `context/foundation/risk-test-map.md` exists with a row for every risk #1–#6

#### Manual

- [ ] 1.4 Per-risk table checked against research.md for overstatement

### Phase 2: Test-Quality Repairs

#### Automated

- [ ] 2.1 `uv run manage.py test registry.tests.test_parser` passes
- [ ] 2.2 `uv run manage.py test households.tests.test_access_control` passes
- [ ] 2.3 Full suite passes: `uv run manage.py test` (228 tests)
- [ ] 2.4 `uv run mypy` succeeds

#### Manual

- [ ] 2.5 Renamed test's name accurately describes its assertion
- [ ] 2.6 `test_access_control.py` docstring accurately scopes what it proves

### Phase 3: `test-plan.md` Corrections and Cookbook Fill-In

#### Automated

- [ ] 3.1 `git diff context/foundation/test-plan.md` touches only §4 and §6.5
- [ ] 3.2 Full suite passes: `uv run manage.py test` (228 tests)

#### Manual

- [ ] 3.3 Corrected §4 numbers match a fresh test-count run
- [ ] 3.4 New §6.5 text is sufficient without opening risk-test-map.md first
