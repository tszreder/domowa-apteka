# Test-Plan Refresh (2026-08-29) — Plan Brief

> Full plan: `context/changes/test-plan-refresh-2026-08-29/plan.md`
> Research: `context/changes/test-plan-refresh-2026-08-29/research.md`

## What & Why

Roadmap slice S-03 (`duplicate-flagging-on-list`) shipped on 2026-08-25, and
`context/foundation/test-plan.md` has not been touched since 2026-08-19. Three
of §8's own refresh triggers fired: a new top risk surfaced from the archive,
two §7 exclusions named S-03 shipping as their re-evaluation trigger, and §4's
churn characterisation inverted. This change brings the project's quality
contract back in line with reality — documentation only, no code.

## Starting Point

The guide carries six risks, a four-phase rollout parked behind S-03, a stack
table claiming 14 modules / 150 test methods, and seven exclusions. Research
measured the truth against each claim: the suite is now 15 modules / 178
methods, `pharmacy/` went from 1 file-touch to roughly 32 over 30 days, and §4's
"No Playwright MCP in this session" line is simply wrong. More importantly, the
newest and least-proven surface in the product — the duplicate classification —
has no risk row at all, despite its implementation review finding 3 real defects
out of 5, every one caught by human reading rather than by the green suite.

## Desired End State

Seven risks, each traceable to a rollout phase. A §3 table whose only remaining
blocker is Phase 4's genuine one (the unrecorded invite-lifetime rule). A §4
that describes the project as measured today. A §7 where each exclusion has
either been re-verified or removed. Every date stamp reading 2026-08-29 — so the
next reader can trust the freshness ledger rather than re-deriving it.

## Key Decisions Made

| Decision | Choice | Why (1 sentence) | Source |
| --- | --- | --- | --- |
| Risk #7's "Must challenge" premise | Rewrite around the verified gap, not `change.md`'s wording | `change.md` claims the S-03 review's mutation-checks were "ad hoc, not committed"; the suite grew 176→178 *because two of them were committed*, so the original claim would put a falsehood into a foundation document | Research |
| What risk #7 actually covers | Wrong relationship **or** correct relationship rendered wrongly | The one measured defect is a presentation bug, and a classification-only wording would exclude it | Research |
| The measured badge defect | Document as evidence; fix belongs to the phase owning risk #7 | Keeps a documentation refresh documentation-only, and hands that phase a concrete defect it must prove it catches | Plan |
| Risk #7's position | Appended as #7 | Ties #3/#4/#5 on impact × likelihood, and appending keeps the numbering §3/§5/§7 all reference stable | Plan |
| Home for risk #7 in §3 | New Phase 5 row | Preserves the table's risk-to-phase invariant and gives the orchestrator a row to advance; Phase 1 is explicitly bounded to auditing *existing* assertions | Plan |
| "Template styling and layout" exclusion | Keep, with a re-verified rationale | Its trigger did not fire — S-03 put every semantic distinction in text, and the CSS is structural only | Research |
| "Duplicate-flagging correctness" exclusion | Delete outright | Its own rationale ("would describe an implementation rather than a defect") is void now that the implementation exists and has a measured defect | Research |
| S-06 / S-07 visual regression | Add as a new exclusion, naming the 390px wrap nuance | No baseline exists to diff against, and the one measured deviation on record was found by eyeballing — which is the argument | Plan |
| §2's copy of the stale churn caveat | Fix it too | `change.md` named only §4; fixing one would leave the document contradicting itself | Plan |
| Roadmap sync | No-op | No roadmap item carries Change ID `test-plan-refresh-2026-08-29` | Plan |

## Scope

**In scope:** §2 (risk #7 + response row + churn note + challenger note), §3
(sequencing note + Phase 5 row), §4 (counts, versions, fan-out fixture note,
Playwright correction, churn paragraph), §7 (one deletion, one sharpening, one
addition), §8 and the header date stamps.

**Out of scope:** the badge dedupe fix and its test; §5 Quality Gates; §6
Cookbook; file:line anchors in §2; risk rows for the proposed S-05/S-06/S-07;
§1 principle #4's pre-existing "three tests"/four-items arithmetic wobble.

## Architecture / Approach

Three phases, each a contiguous region of one file, ordered by dependency: §2
first (risk #7 is what everything else points at), §3/§4 second (the Phase 5 row
needs the risk to exist; the fixture note needs the phase to exist), §7/§8 last
(freshness stamps advance only once the substance has landed). Verification is
grep-based wherever a claim is textual — every stale string is known exactly
from research, so absence is mechanically checkable rather than a matter of
careful reading — with one full test run at the end as a guard that a docs
change stayed a docs change.

## Phases at a Glance

| Phase | What it delivers | Key risk |
| --- | --- | --- |
| 1. §2 Risk Map | Risk #7, its response row, the challenger note, §2's churn fix | An implementer working from `change.md` pastes the disproven "ad hoc" premise; check 1.4 greps for exactly that |
| 2. §3 + §4 | Park condition cleared, Phase 5 row, four stale §4 facts corrected | Clearing the S-03 park condition also deletes Phase 4's separate, still-open blocker |
| 3. §7 + §8 | One exclusion deleted, one sharpened, one added; all dates advanced | Editing five sections independently leaves them contradicting each other — hence the closing consistency read |

**Prerequisites:** none beyond the change folder, which exists with `change.md`
and `research.md` in place. No access, tooling, or upstream work is pending.

**Estimated effort:** one session, roughly 3 phases of 15–25 minutes each; the
78-second test run at the end is the longest single wait.

## Open Risks & Assumptions

- **The premise correction is the thing most likely to be lost.** `change.md`
  reads as authoritative and supplies ready-made prose containing the false
  claim. The plan makes this detectable rather than trusting care alone.
- **The measured defect stays live on screen** until the phase covering risk #7
  runs. That is an accepted, deliberate consequence of keeping this change
  documentation-only — not an oversight.
- **Phase 5 grows the rollout to five phases** against a 2026-09-14 PRD deadline
  under after-hours-only capacity. The row is written as `not started`, so it
  records the obligation without claiming a slot in the schedule.
- **Assumption:** the 178-test suite and the 91-commit churn window are current
  as of 2026-08-29 and will not have moved by the time the phases run. If work
  lands in between, §4's counts need re-measuring, not just re-typing.

## Success Criteria (Summary)

- A reader who has never seen the S-03 review can open §2, understand what could
  fail on the duplicate screen, and know which claim to distrust while testing it.
- Every one of the seven risks traces to a phase, and §3's only remaining blocker
  is the genuine one — the unrecorded invite-lifetime product decision.
- Nothing in the document contradicts anything measured in `research.md`, and no
  string dated 2026-08-19 survives.
