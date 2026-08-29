---
change_id: test-plan-refresh-2026-08-29
title: Refresh test-plan.md after duplicate-flagging ships
status: implemented
created: 2026-08-29
updated: 2026-08-30
archived_at: null
---

## Notes

Refresh `context/foundation/test-plan.md` (last updated 2026-08-19). This is a
`/10x-test-plan --refresh` cycle — three honest triggers fired: S-03
(`duplicate-flagging-on-list`) shipped 2026-08-25, clearing the §3 Phase 3/4
park condition; two §7 exclusions named S-03 shipping as their own
re-evaluation trigger; and §4's pharmacy churn note is stale (no longer
squash-merge-flattened).

**Stale content to correct:**
- §3: clear the "parked until S-03 ships" sequencing note; Phases 3 and 4 are
  simply not-started now, no longer blocked by that condition (Phase 4 keeps
  its separate, still-open blocker: the invite lifetime rule is unrecorded).
- §4: replace the "pharmacy squash-merged, single commit" caveat — `pharmacy/`
  now shows real 30-day churn (`item_list.html` touched 4x). Update test-base
  counts (14→15 modules, ~150→~178 methods) and refresh MCP-grounding
  `checked:` dates.
- §7: "Duplicate-flagging correctness" and "Template styling and layout" both
  named S-03 shipping as their re-evaluation trigger — re-evaluate both now
  that it has shipped.

**New risk to add (§2, position #7, with full Risk Response Guidance row):**
"The full/partial duplicate classification itself computes the wrong
relationship for correctly-resolved substance sets — including the
multi-substance fan-out case where one item partially overlaps several others
at once — and nothing but a human implementation review catches it before
merge." Impact High, Likelihood Medium. Source: interview Q1 (top production
worry, independent of docs) + Q3 (least-confident area, corroborated by
hot-spot dir `pharmacy/`) + archive `2026-08-24-duplicate-flagging-on-list`
review (3 of 5 findings were real defects — nondeterministic partner order,
an unpinned cluster-ordering guarantee, a plan/code drift — caught only by
manual review, not by the existing green suite).

Response guidance: prove group/partial-overlap/multi-partner rendering
correctness with tests that go red on classification or ordering mutation;
must challenge "the review already fixed it, so it's covered" (the review's
mutation-checks were ad hoc, not committed to the regression suite); ground
`classify()`/`build_list_view`'s current partitioning and whether the
review's falsification technique is already a repeatable test; likely
cheapest layer is unit tests over `classify()`/clustering with
2+-overlapping-partner fixtures, promoted to integration only for the
rendering-order guarantee; anti-pattern to avoid is re-asserting today's
clustering output as expected (oracle problem) instead of deriving expected
groups from substance-set math.

**§7 addition:** exclude pixel-level visual-regression testing for the
proposed S-06 (UX audit) and S-07 (visual refresh) roadmap slices —
appearance changes are cheap to eyeball and no screen exists yet to test
against (interview Q5).

**Challenger note to preserve:** S-05/S-06/S-07 are proposed, not built —
none license a new risk row yet (would describe code that doesn't exist);
revisit each when it ships.

This change's outcome is an updated `context/foundation/test-plan.md` — §1/§2
Source/Risk-Response cells, §3 sequencing note, §4 stack/churn notes, and §7
negative-space only. It does not touch §5 Quality Gates or add file:line
anchors (research supplies those; the plan carries evidence and response
intent, per the test-plan skill's "signal, not knowledge" principle).
