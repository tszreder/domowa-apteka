---
change_id: ux-audit-and-flow-fixes
title: Ux audit and flow fixes
status: preparing
created: 2026-09-05
updated: 2026-09-05
archived_at: null
---

## Notes

Roadmap slice **S-06**. `research.md` is the S-06 audit artifact — the roadmap
calls it `ux-audit.md`; there is one file, named `research.md` because that is
what `/10x-plan` reads.

**Triage complete (2026-09-05).** 33 of 35 findings are in slice; F-28
(list ordering/search/filter) is out as a separate future slice. See
`research.md`'s Triage sheet for the per-finding call.

Two cross-cutting policies the triage rests on, decided with the user:

- **Copy rewriting is in scope.** F-12/F-22/F-30/F-32/F-35 are wording-only
  and cheap; no design-system dependency.
- **S-06/S-07 line for hierarchy findings**: S-06 may *reassign* an element to
  one of Pico's existing semantic button roles (`secondary`/`outline`) or add
  plain-text emphasis to state a fact — that's a structural/informational
  decision. S-06 does **not** invent new visual language (a warning color, an
  icon system, a verdict palette) where none exists yet — that's S-07's own
  open question ("what do full/partial/unresolved look like as one system?")
  and inventing an answer here would pre-empt it. Findings F-08, F-21, F-22,
  F-23, F-29, F-31, F-32 are scoped this way; see their Triage-sheet notes for
  the specific split.
- **F-05 (password reset)**: copy only, acknowledging it doesn't exist yet —
  building the flow itself is out of this slice's size.
- **F-25 (package count)**: in scope — a presentation-only reuse of data
  `/check/` already computes, no schema change.

Planning is no longer blocked; ready for `/10x-plan`.
