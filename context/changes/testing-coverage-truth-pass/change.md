---
change_id: testing-coverage-truth-pass
title: "Coverage truth pass: prove the tests claiming to protect risks #1-#6 can fail"
status: planned
created: 2026-09-05
updated: 2026-09-05
archived_at: null
---

## Notes

based on c:\Users\tszre\Code\domowa-apteka\context\foundation\test-plan.md - build it on a separate worktree

Grounding — this is **Phase 1** of the §3 Phased Rollout in
`context/foundation/test-plan.md`:

- **Goal:** produce a written risk-to-test map and prove the assertions
  claiming to protect risks #1–#6 can fail — bounded to those assertions,
  ceiling of roughly twelve falsification checks, **not** a sweep of the
  whole suite.
- **Risks covered:** #1–#6 (verification, not new coverage).
- **Test types:** suite audit, falsification checks, repair of unfalsifiable
  tests.
- **Why it exists:** §1 principle #4 — this project has already shipped tests
  that could not fail (a setup that guaranteed its own assertion, a
  mutation-dead cross-household check, two parser rules no test observed).
  A green suite is not evidence; a test watched to go red is.
- **Deliverable later phases depend on:** the risk-to-test map is the metric
  this plan uses in place of line coverage (§4 "coverage measurement", §6.5).
- **Gate it unlocks:** §5 "falsification of new risk tests" becomes
  *recommended* after this phase lands.
- **Out of scope:** risk #7 — that is Phase 5, not this one.

Built on worktree `.claude/worktrees/feature+testing-coverage-truth-pass`,
branch `feature/testing-coverage-truth-pass`, cut from `origin/main`.
