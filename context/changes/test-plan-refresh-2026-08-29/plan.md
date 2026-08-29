# Test-Plan Refresh (2026-08-29) Implementation Plan

## Overview

Refresh `context/foundation/test-plan.md` after roadmap slice S-03
(`duplicate-flagging-on-list`) shipped on 2026-08-25. Three honest refresh
triggers fired: a new top risk surfaced from the archive, two §7 exclusions
named S-03 shipping as their own re-evaluation trigger, and §4's churn
characterisation stopped describing reality.

This is a **documentation-only** change. No application code, no tests, no CI
configuration. The outcome is an updated quality contract that other skills
(`/10x-tdd`, `/10x-research`, future `/10x-test-plan` invocations) read as
authoritative.

## Current State Analysis

`context/foundation/test-plan.md` was last updated 2026-08-19 and carries six
risks, a four-phase rollout, a stack table, ten quality gates, an empty
cookbook, seven exclusions, and a freshness ledger. Since that date the project
shipped S-03 and the guide drifted in four independent directions:

- **§2 has no row for the product's newest and least-proven surface.** The
  duplicate classification shipped on 2026-08-25 and its implementation review
  found 3 real defects out of 5 findings — all caught by human review over a
  green suite, none by the suite itself.
- **§3's park condition is spent.** "Parked until S-03 ships" is now a
  historical note masquerading as a live constraint.
- **§4 is stale in three separate directions** — an undercount of the test base,
  a churn caveat that inverted, and a factually wrong tooling-availability line.
- **§7 carries two exclusions whose stated re-evaluation trigger has fired**,
  and they do not resolve the same way.

Research (`research.md`) grounded all four and, critically, **disproved one
premise `change.md` was built on**. That correction is the single most important
thing this plan carries forward.

## Desired End State

`context/foundation/test-plan.md` carries seven risks; risk #7 traces to a
rollout phase; §4 describes the project as it is today; §7's exclusions each
either survive with a re-verified rationale or are gone; and every date stamp
reads 2026-08-29.

Verifiable by: the grep assertions in each phase's Success Criteria, plus a
green `uv run manage.py test` and a `git diff --stat` confined to `context/`.

### Key Discoveries

- **`change.md`'s stated premise for risk #7 is false and must not be written
  into the guide.** It claims the S-03 review's mutation-checks were "ad hoc,
  not committed to the regression suite." Research measured the opposite:
  findings F1 (nondeterministic partner order) and F3 (unpinned cluster
  ordering) each landed a committed, mutation-checked test, and the suite grew
  176 → 178 for exactly that reason
  (`context/archive/2026-08-24-duplicate-flagging-on-list/reviews/impl-review.md`).
  Writing the original claim into a foundation document would make the project's
  quality contract assert something arithmetic disproves.
- **The real gap is narrower and sharper.** Every committed assertion on
  `DuplicateGroup.partners` expects a **single-element** list — six of them at
  `pharmacy/tests/test_duplicates.py:208-215`. The accumulation path where one
  substance draws two or more partners (`pharmacy/duplicates.py:167-168`) is
  asserted at no layer, and the dedup loop feeding the user-visible summary
  (`pharmacy/duplicates.py:85-93`) has a branch that is dead in the suite.
- **A live, user-visible defect sits in that untested path**, measured this
  research session: `partners == {'Paracetamol': ['Apap', 'Apap']}` while
  `partner_names == ['Apap']`, so the badge's summary line contradicts its own
  detail line. Cause: dedup is applied within a group and across substances, but
  never across partner groups.
- **§7's two triggered exclusions resolve differently.** "Duplicate-flagging
  correctness" is void — S-03 shipped, so the exclusion's own rationale ("a risk
  row would describe an implementation rather than a defect") no longer holds.
  "Template styling and layout" **survives**: its trigger was the list screen
  encoding meaning in styling, and S-03 encoded every semantic distinction in
  text instead, with `static/css/app.css:3-42` purely structural.
- **§2 carries a copy of the same stale squash-merge caveat as §4.** `change.md`
  named only §4. Fixing one and not the other would leave the document
  contradicting itself.
- **`pharmacy/` is now a genuine hot spot** — roughly 32 file-touches across its
  subdirectories over 30 days, up from 1 at the last refresh, with
  `item_list.html` touched 4 times.
- **Playwright MCP is available in this session**, contradicting §4's explicit
  "No Playwright MCP" line — but it drives a live browser from an agent session
  and is not CI-reproducible, which is the same caveat §4 already applies to
  Claude-in-Chrome.
- **No roadmap sync applies.** No item in `context/foundation/roadmap.md` carries
  Change ID `test-plan-refresh-2026-08-29` (verified by grep over all nine
  `**Change ID:**` lines), so the roadmap is left untouched.

## What We're NOT Doing

- **Not fixing the measured badge defect.** Confirmed decision: the dedupe fix
  and its regression test belong to the rollout phase that owns risk #7, not to
  a documentation refresh. Recording it as evidence is what keeps it from being
  lost.
- **Not touching §5 Quality Gates.** Phase 5 introduces no new gate, and the
  existing "required after §3 Phase 4" markers are unaffected by appending a
  phase.
- **Not touching §6 Cookbook.** Its entries fill in as phases ship; Phase 5 has
  not shipped.
- **Not adding file:line anchors, function names, schema names, or module names
  to §2.** The test-plan is a QA spec, not a code audit — §1 principle #3 and the
  skill's "signal, not knowledge" rule. Directory-level hot-spot references are
  explicitly permitted and are used.
- **Not adding risk rows for S-05, S-06, or S-07.** All three are `proposed` with
  no code; a risk row would describe software that does not exist.
- **Not correcting §1 principle #4's arithmetic.** It says "three tests that
  could not fail" and then enumerates four items. This is a pre-existing wording
  wobble, not staleness, and it is outside the refresh triggers that opened this
  change. Noted here so the omission is deliberate rather than missed.
- **Not migrating to pytest, adding a linter, or wiring e2e.** Those are named by
  §3/§5 as future phase work.

## Implementation Approach

Three phases, each scoped to a contiguous region of the document, in dependency
order: §2 first because risk #7 is the substantive new content everything else
references; §3/§4 second because the Phase 5 row must point at a risk that
already exists and §4's fixture note must point at a phase that already exists;
§7/§8 last because the freshness stamps should not be advanced until every
substantive edit has landed.

Verification leans on grep rather than judgement wherever a claim is textual:
the stale strings are known exactly, so their absence is mechanically checkable,
as is the presence of the replacements. The full test suite runs once at the end
purely as a guard that a documentation change stayed documentation.

## Critical Implementation Details

**The premise correction is load-bearing and easy to lose.** `change.md`'s
Notes section supplies ready-made prose for risk #7's response row, and that
prose contains the disproven "ad hoc, not committed" claim. An implementer
working from `change.md` alone will paste it in. Phase 1 exists partly to make
that failure detectable: automated check 1.4 greps the whole document for the
claim, and the "Must challenge" cell must instead assert the *narrower* verified
gap — that the committed partner assertions all expect exactly one partner.

**Section ordering matters for the §2 note edits.** §2 has prose paragraphs
after the risk table (abuse lens, then likelihood/churn) before the Risk
Response Guidance heading. The stale squash-merge sentence is in the second.
Editing the table and the paragraph are separate edits to the same section; do
both in Phase 1 so §2 is internally consistent when the phase closes.

---

## Phase 1: §2 Risk Map — add risk #7 with a corrected premise

### Overview

Add the seventh risk row, its Risk Response Guidance row, the challenger note
on the proposed slices, and correct §2's own stale churn sentence.

### Changes Required

#### 1. Risk table — new row #7

**File**: `context/foundation/test-plan.md`

**Intent**: Add the duplicate-classification failure scenario as risk #7 at the
end of the §2 risk table, rated Impact High / Likelihood Medium. Position #7 is
deliberate: by impact × likelihood it ties risks #3/#4/#5, and appending keeps
the existing numbering — which §3, §5 and §7 all reference — stable.

**Contract**: One new table row with the five existing columns
(`# | Risk | Impact | Likelihood | Source`). The risk statement must be a user /
business failure scenario and must cover both halves of the surface: a wrong
*relationship* computed, and a correct relationship *rendered* wrongly —
because the measured defect is the second kind and would fall outside a
classification-only wording. The Source cell cites the interview, the archived
S-03 review, the `pharmacy/` hot-spot directory, and the defect measured during
this refresh — as evidence, with no file, function, or module named.

#### 2. Risk Response Guidance — new row #7

**File**: `context/foundation/test-plan.md`

**Intent**: Add the six-cell response row. This is where the corrected premise
lands.

**Contract**: Row with cells `Risk | What would prove protection | Must
challenge | Context /10x-research must ground | Likely cheapest layer |
Anti-pattern to avoid`.

- *What would prove protection* — group membership, partner annotation, and
  render order all derivable from substance-set arithmetic, with tests that go
  red under mutation of classification, accumulation, or ordering.
- *Must challenge* — "the review already fixed it, so it is covered." The
  correction goes here: acknowledge that two of that review's findings **did**
  land committed, mutation-checked tests, then name the narrower real gap —
  every committed partner assertion expects exactly one partner, so the
  multi-partner accumulation path is asserted at no layer, and the dedup feeding
  the summary line has no test that exercises it.
- *Cheapest layer* — unit over classifier and builder with 2+-partner fixtures;
  integration only for the ordering guarantee, since a unit test on the builder
  cannot observe a caller's re-sorting.
- *Anti-pattern* — re-asserting today's clustering output as expected (the
  oracle problem), plus treating the summary line as proof of the detail line
  when the two are produced by different paths and already disagree.

**Do not** name `classify`, `build_list_view`, `partners`, `partner_names`, or
any path in these cells — that is research's output per phase. Describe the
behaviour, not the symbol.

#### 3. §2 churn note — remove the inverted squash-merge claim

**File**: `context/foundation/test-plan.md`

**Intent**: The paragraph beginning "Likelihood is not argued from churn
anywhere in this table" asserts that the newest surfaces landed via squash-merge
so churn understates them. That is no longer true. Keep the principle, replace
the justification.

**Contract**: The sentence retains "Likelihood is not argued from churn anywhere
in this table" and the interview's "uniform" answer, drops the squash-merge
clause, and notes that as of this refresh churn no longer understates the newest
surfaces — `pharmacy/` has become a genuine hot spot, which risk #7 cites as
corroboration rather than as its origin.

#### 4. Challenger note on the proposed slices

**File**: `context/foundation/test-plan.md`

**Intent**: Preserve the challenger pass's conclusion that S-05, S-06 and S-07
license no risk rows yet, so a future reader does not treat their absence as an
oversight.

**Contract**: A short prose note in §2 alongside the existing abuse-lens and
churn notes. Names S-05 as the one to watch, since the duplicate primitive is
built for it as a forward consumer.

### Success Criteria

#### Automated Verification

- Risk #7 row exists in the §2 table with Impact `High` and Likelihood `Medium`
- Risk Response Guidance table has a `#7` row with all six cells non-empty
- No file path, `file:line` anchor, function name, or module name appears in the
  new §2 cells: `grep -n 'duplicates\.py\|test_duplicates\|classify(\|build_list_view\|partner_names' context/foundation/test-plan.md` returns nothing
- The disproven claim is absent: `grep -ni 'ad hoc' context/foundation/test-plan.md` returns nothing
- The stale squash-merge clause is gone from §2
- The §2 table has exactly 7 risk rows

#### Manual Verification

- The "Must challenge" cell reads as a genuine challenge grounded in the
  verified gap, not a restatement of the risk in other words
- Risk #7's Source cell can be traced by a reader without opening any source file
- The challenger note reads as a live constraint on future refreshes, not as
  history

**Implementation Note**: After this phase and its automated verification passes,
pause here for manual confirmation before proceeding to the next phase.

---

## Phase 2: §3 rollout and §4 stack

### Overview

Clear the spent park condition, give risk #7 a phase to live in, and bring §4's
three stale facts into line with what was measured.

### Changes Required

#### 1. §3 sequencing note

**File**: `context/foundation/test-plan.md`

**Intent**: Replace the 2026-08-19 park decision. Phases 3, 4 and 5 are `not
started` because nobody has started them — not because they are blocked.

**Contract**: The paragraph is re-dated 2026-08-29 and states that S-03 shipped
2026-08-25, clearing the condition. It must **not** delete or weaken the
separate "Open decision blocking Phase 4" paragraph that follows — the invite
lifetime rule is still unrecorded (verified: `roadmap.md:127` still carries S-01
Unknown 2 verbatim, and the PRD specifies no lifetime). Two blockers existed;
one cleared.

#### 2. §3 table — new Phase 5 row

**File**: `context/foundation/test-plan.md`

**Intent**: Give risk #7 a rollout home so the table's risk-to-phase invariant
holds and the orchestrator has a row to advance.

**Contract**: One row appended with the seven existing columns
(`# | Phase name | Goal | Risks covered | Test types | Status | Change folder`).
`Risks covered` is `#7`. `Status` is `not started`. `Change folder` is `—`,
matching phases 3 and 4 which have no folder yet. The goal line stays one line
and matches the voice of rows 1–4.

#### 3. §4 test-base counts

**File**: `context/foundation/test-plan.md`

**Intent**: Correct the undercount in the unit+integration row.

**Contract**: `14 test modules, 150 test methods` becomes `15 test modules, 178
test methods`. The rest of that cell — the deliberate no-pytest rationale —
stays.

#### 4. §4 typecheck row

**File**: `context/foundation/test-plan.md`

**Intent**: The row lists mypy and django-stubs under a single version cell
reading `2.3.0`, which is mypy's version only.

**Contract**: Version cell distinguishes the two: mypy 2.3.0, django-stubs 6.0.7.

#### 5. §4 test-data row — fan-out fixtures

**File**: `context/foundation/test-plan.md`

**Intent**: Record the fixture shape risk #7 needs, mirroring how risk #1's
collision fixtures are already flagged as not-yet-existing.

**Contract**: The existing `test data` row's Notes cell gains a second clause:
fan-out fixtures — where one substance draws two or more partners — do not
exist either, see Phase 5. Extending the existing row rather than adding a
parallel one is deliberate: the Layer and Tool cells would be identical
(in-test object creation), so a second row would duplicate rather than inform.

#### 6. §4 stack-grounding tools — the Playwright correction

**File**: `context/foundation/test-plan.md`

**Intent**: The line "No Playwright MCP in this session" is factually wrong.
Correct the availability fact **without** converting it into an e2e
recommendation.

**Contract**: Playwright MCP is recorded as available, carrying the same
CI-reproducibility caveat §4 already applies to Claude-in-Chrome: it drives a
live browser from an agent session, not a CI-reproducible layer, so
`StaticLiveServerTestCase` remains the Phase 4 recommendation. Every
`checked:` date in this block advances to 2026-08-29.

#### 7. §4 churn paragraph

**File**: `context/foundation/test-plan.md`

**Intent**: Replace, not soften. The caveat asserted the opposite of what is now
true.

**Contract**: 30 days to 2026-08-29, 91 commits (was 69). Directory-level churn
with `households` 23, `registry` 14, `pharmacy` 11 plus its subdirectories.
States plainly that `pharmacy/` is now a genuine hot spot, replacing the
squash-merge caveat. The second caveat — that the hardest-churning directories
are the test trees, which is weak evidence for a product failure — was verified
as still true and is kept.

### Success Criteria

#### Automated Verification

- The park condition is gone: `grep -n 'parked until' context/foundation/test-plan.md` returns nothing
- The Phase 4 blocker survives: `grep -n 'Open decision blocking Phase 4' context/foundation/test-plan.md` returns a match
- §3 table has a Phase 5 row whose `Risks covered` cell contains `#7`
- `grep -n '14 test modules\|150 test methods' context/foundation/test-plan.md` returns nothing
- `grep -n '15 test modules' context/foundation/test-plan.md` returns a match
- `grep -n 'No Playwright MCP' context/foundation/test-plan.md` returns nothing
- `grep -n 'squash-merge' context/foundation/test-plan.md` returns nothing anywhere in the file
- `grep -n '69 commits' context/foundation/test-plan.md` returns nothing; `91 commits` returns a match
- §4's test-data Notes cell mentions Phase 5

#### Manual Verification

- The Phase 5 goal line reads as one line and matches rows 1–4 in voice and grain
- The corrected Playwright line cannot be misread as endorsing Playwright MCP as
  the e2e layer
- The new churn paragraph reads as evidence-for-context, consistent with §2's
  standing rule that likelihood is not argued from churn

**Implementation Note**: After this phase and its automated verification passes,
pause here for manual confirmation before proceeding to the next phase.

---

## Phase 3: §7 negative space, freshness stamps, and whole-document consistency

### Overview

Resolve the three §7 verdicts, advance every date stamp, and read the document
end to end for self-contradiction.

### Changes Required

#### 1. Remove the void exclusion

**File**: `context/foundation/test-plan.md`

**Intent**: "Duplicate-flagging correctness" is excluded on the grounds that
S-03 is not built. S-03 is built, and the surface now carries a measured defect.
The exclusion is void and its subject is now risk #7.

**Contract**: The bullet is deleted outright rather than annotated. §7 is a list
of what the project deliberately does not test; a void entry kept for
bookkeeping would misinform a skim-reader. Lineage lives in risk #7's Source
cell and this change folder.

#### 2. Retain and sharpen "Template styling and layout"

**File**: `context/foundation/test-plan.md`

**Intent**: Its trigger — the list screen encoding meaning in styling — was
checked and did **not** fire. Record the check so the next refresh does not
re-litigate it from scratch.

**Contract**: The bullet keeps its subject and its cost argument, and replaces
the forward-looking "which S-03's duplicate flags may do" with the verified
outcome: S-03 shipped and distinguishes cluster kind, unresolved state, and
shared substances in words, with duplicate styling structural only — no
colour-coded semantics — so no meaning is lost to a DOM assertion, and the
existing tests already assert on that text. Re-checked 2026-08-29.

#### 3. New exclusion — pixel-level visual regression for S-06 / S-07

**File**: `context/foundation/test-plan.md`

**Intent**: Pre-empt the reflex to add visual-regression tooling when the two
appearance-focused slices come up.

**Contract**: A new bullet excluding pixel-level visual-regression testing for
the proposed S-06 (UX audit) and S-07 (visual refresh) slices. Two grounds:
appearance changes are cheap to eyeball, and there is no baseline worth diffing
against — S-07 exists to replace stock framework defaults, and S-06's own
roadmap note requires the audit be produced by driving the running app at
phone width, which is a human/agent judgement rather than a diff. Names the one
measured appearance deviation on record — the collapsed partial-overlap summary
wrapping to two lines at 390px with three long partner names — as the exception
that demonstrates eyeballing already works. Carries a re-evaluation trigger:
either slice shipping a screen whose correctness depends on layout rather than
text. Sourced to Phase 2 interview Q5 and the 2026-08-29 challenger pass.

#### 4. Freshness stamps

**File**: `context/foundation/test-plan.md`

**Intent**: Advance the header date and all three §8 ledger lines.

**Contract**: Header `Last updated:` and §8's three review lines all read
2026-08-29. §8's refresh-trigger list is unchanged — all four triggers are still
the right ones, and three of them are what opened this change.

#### 5. Whole-document consistency read

**File**: `context/foundation/test-plan.md`

**Intent**: Catch cross-section contradictions introduced by editing five
sections independently.

**Contract**: No content change of its own. Confirm: §2's seven risks are each
named by some §3 row; §3's Phase 5 references a risk that exists; §4's fixture
note references a phase that exists; §5's "required after §3 Phase 4" markers
still make sense with a Phase 5 appended; §7 contains no exclusion whose subject
is now a §2 risk.

### Success Criteria

#### Automated Verification

- `grep -n 'Duplicate-flagging correctness' context/foundation/test-plan.md` returns nothing
- `grep -n 'Template styling and layout' context/foundation/test-plan.md` returns a match
- `grep -n '390px' context/foundation/test-plan.md` returns a match in §7
- `grep -c '2026-08-19' context/foundation/test-plan.md` returns 0
- `grep -n 'Last updated: 2026-08-29' context/foundation/test-plan.md` returns a match
- Every `checked:` occurrence reads 2026-08-29:
  `grep -o 'checked: [0-9-]*' context/foundation/test-plan.md | sort -u` yields one value
- Suite still green: `uv run manage.py test` reports `Ran 178 tests` and `OK`
- Django system checks pass: `uv run manage.py check`
- Change stayed documentation-only: `git diff --stat` lists only paths under `context/`

#### Manual Verification

- The document reads end to end without a section contradicting another
- The retained styling exclusion reads as re-verified, not as untouched
- The new S-06/S-07 exclusion would actually stop a future contributor from
  reaching for a visual-diff tool
- §7 no longer excludes anything §2 now claims as a risk

**Implementation Note**: Final phase — confirm the full document reads correctly
before closing the change.

---

## Testing Strategy

This change ships no code, so the "tests" are assertions about document content
plus a regression guard that the change stayed in its lane.

### Unit Tests

- None. No code changes.

### Integration Tests

- None. No code changes.

### Content assertions (the real verification)

- Presence and absence greps, enumerated per phase above. Every stale string is
  known exactly from research, so absence is mechanically checkable rather than
  a matter of reading carefully.
- Structural counts: 7 risk rows in §2, 7 response rows in the guidance table,
  5 rows in §3.

### Regression guard

- `uv run manage.py test` — expected `Ran 178 tests … OK` (~78s). A documentation
  change cannot alter this; running it proves nothing leaked.
- `git diff --stat` confined to `context/` — the structural guarantee that this
  was documentation-only.

### Manual Testing Steps

1. Read §2 risk #7 and its response row cold; ask whether a reader who has never
   seen the S-03 review would know what to build and what to distrust.
2. Read §3 top to bottom; confirm exactly one blocker remains (Phase 4's) and it
   is the invite lifetime rule.
3. Read §4 against the measured numbers in `research.md`; confirm no third
   direction of staleness was introduced.
4. Read §7 and ask, for each bullet, whether its re-evaluation trigger is still
   the right one.

## Performance Considerations

None. Documentation-only.

## Migration Notes

None. The file is edited in place; the phased-rollout table's existing row
numbering is preserved by appending rather than inserting, so §5's "required
after §3 Phase 4" markers and any external reference to phases 1–4 remain valid.

## References

- Change identity: `context/changes/test-plan-refresh-2026-08-29/change.md`
- Research: `context/changes/test-plan-refresh-2026-08-29/research.md`
- Target artifact: `context/foundation/test-plan.md`
- Premise correction source:
  `context/archive/2026-08-24-duplicate-flagging-on-list/reviews/impl-review.md`
- Verified gap: `pharmacy/tests/test_duplicates.py:208-215` (six single-partner
  assertions); `pharmacy/duplicates.py:85-93, 167-168` (dedup asymmetry)
- S-05/S-06/S-07 definitions: `context/foundation/roadmap.md:50-52, 172-208`
- Phase 4 blocker still open: `context/foundation/roadmap.md:127`

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles. See `references/progress-format.md`.

### Phase 1: §2 Risk Map — add risk #7 with a corrected premise

#### Automated

- [x] 1.1 Risk #7 row exists in §2 table with Impact High and Likelihood Medium — 4111993
- [x] 1.2 Risk Response Guidance has a #7 row with all six cells non-empty — 4111993
- [x] 1.3 No file path, anchor, function, or module name appears in the new §2 cells — 4111993
- [x] 1.4 The disproven "ad hoc" claim is absent from the document — 4111993
- [x] 1.5 The stale squash-merge clause is gone from §2 — 4111993
- [x] 1.6 The §2 table has exactly 7 risk rows — 4111993

#### Manual

- [x] 1.7 "Must challenge" reads as a genuine challenge grounded in the verified gap — 4111993
- [x] 1.8 Risk #7's Source cell is traceable without opening any source file — 4111993
- [x] 1.9 The challenger note reads as a live constraint, not as history — 4111993

### Phase 2: §3 rollout and §4 stack

#### Automated

- [x] 2.1 The park condition is gone from §3 — 0c2d12c
- [x] 2.2 The Phase 4 invite-lifetime blocker survives — 0c2d12c
- [x] 2.3 §3 table has a Phase 5 row whose Risks covered cell contains #7 — 0c2d12c
- [x] 2.4 The 14-modules / 150-methods counts are gone and 15 modules is present — 0c2d12c
- [x] 2.5 The "No Playwright MCP" line is gone — 0c2d12c
- [x] 2.6 No occurrence of squash-merge remains anywhere in the file — 0c2d12c
- [x] 2.7 The 69-commit figure is gone and 91 commits is present — 0c2d12c
- [x] 2.8 §4's test-data Notes cell mentions Phase 5 — 0c2d12c

#### Manual

- [x] 2.9 The Phase 5 goal line matches rows 1–4 in voice and grain — 0c2d12c
- [x] 2.10 The corrected Playwright line cannot be misread as an e2e endorsement — 0c2d12c
- [x] 2.11 The new churn paragraph stays consistent with §2's no-churn-for-likelihood rule — 0c2d12c

### Phase 3: §7 negative space, freshness stamps, and whole-document consistency

#### Automated

- [x] 3.1 The "Duplicate-flagging correctness" exclusion is removed — 1df1cff
- [x] 3.2 The "Template styling and layout" exclusion is retained — 1df1cff
- [x] 3.3 The new S-06/S-07 exclusion is present and names the 390px wrap nuance — 1df1cff
- [x] 3.4 No occurrence of 2026-08-19 remains in the file — 1df1cff
- [x] 3.5 The header reads Last updated: 2026-08-29 — 1df1cff
- [x] 3.6 Every checked: date resolves to the single value 2026-08-29 — 1df1cff
- [x] 3.7 Suite green: uv run manage.py test reports Ran 178 tests OK — 1df1cff
- [x] 3.8 Django system checks pass — 1df1cff
- [x] 3.9 git diff --stat lists only paths under context/ — 1df1cff

#### Manual

- [x] 3.10 The document reads end to end without a section contradicting another — 1df1cff
- [x] 3.11 The retained styling exclusion reads as re-verified, not untouched — 1df1cff
- [x] 3.12 The new exclusion would stop a contributor reaching for a visual-diff tool — 1df1cff
- [x] 3.13 §7 no longer excludes anything §2 now claims as a risk — 1df1cff
