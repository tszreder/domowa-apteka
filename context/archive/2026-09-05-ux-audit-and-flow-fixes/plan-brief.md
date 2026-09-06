# S-06 UX Audit Flow Fixes — Plan Brief

> Full plan: `context/changes/ux-audit-and-flow-fixes/plan.md`
> Research: `context/changes/ux-audit-and-flow-fixes/research.md`

## What & Why

Fix 33 triaged-in audit findings plus 2 user-requested additions across 7 screens. The audit walked the running app at phone width and found two broken flows (invited existing user never joins; add form shows wrong error and wipes input), hierarchy inversions (delete buttons dominate the list while duplicate signals hide), layout bugs, missing affordances (no copy button for invite, no confirmation on delete), and copy that names the wrong thing. This slice makes every core action complete in fewer, clearer steps.

## Starting Point

All 5 slices that build the app's functionality (S-01 through S-05) are shipped and deployed. The UI was written by the same agent that now audits it — the audit was produced by driving the deployed app as a user on a phone, not by reading templates. The data layer already carries information the UI throws away: substances in suggestion responses, package counts on `/check/`, holders per producer. Several findings are presentation-only.

## Desired End State

Every core action — add, check, invite, view list — completes on a phone without a broken hand-off. An invited existing user joins. The add form never shows a wrong error. Delete requires confirmation. Identical items aggregate with a count. The list's hierarchy reflects what the app values.

## Key Decisions Made

| Decision | Choice | Why (1 sentence) | Source |
| --- | --- | --- | --- |
| F-11 fix approach | `user_logged_in` signal handler | Decoupled from LoginView — works with any auth backend | Plan |
| F-14 fix approach | Client gate + server error | Belt and suspenders: prevent the mis-tap AND give a clear message if JS fails | Plan |
| Suggestion positioning | Absolute overlay | Standard autocomplete pattern; submit button stays visible | Plan |
| Producer selection | Native `<select>` | No keyboard needed; all options visible on mobile picker | Plan |
| Identical items | Aggregate with count | Shorter list; delete targets one instance | Plan |
| Delete confirmation | JS `confirm()` | Minimal change; styled confirm is S-07 territory | Plan |
| Check → add bridge | "Wróć do listy" only | Check is for the doctor's office — prompting add would invite wrong data | Plan |
| Invite sharing | Copy button only | Simple, universal; `navigator.share()` deferred | Plan |
| Household naming on signup | Redirect to existing `/household/create/` | Form already exists; pre-fill with email prefix | Plan |
| S-06/S-07 boundary | Structure and information only | No new colors, icons, or verdict palette — that's S-07 | Research triage |

## Scope

**In scope:** 33 audit findings (F-01–F-27, F-29–F-35), household naming on signup, `/household/` nav access. Copy rewriting included. Hierarchy findings get structural/informational fixes using Pico's existing roles.

**Out of scope:** F-28 (ordering/search/filter — future slice). Password reset flow (copy only). New visual language (S-07). `navigator.share()`. Undo on delete. Add-from-check.

## Architecture / Approach

Template-first changes organized by screen. Two pieces of new backend logic: a `user_logged_in` signal handler (`households/signals.py`) for F-11, and an `ItemStack` aggregation dataclass in `pharmacy/duplicates.py` for F-25. JS changes in `autocomplete.js` (gate, preview, `<select>`) and `product-search.js` (holder in label). CSS changes in `app.css` (sticky header, overlay suggestions, demoted buttons). One new test file for the signal handler; existing test files extended.

## Phases at a Glance

| Phase | What it delivers | Key risk |
| --- | --- | --- |
| 1. Base template & landing | Flash messages, sticky header, brand link, nav entries, landing CTA, list heading | Cross-cutting — touches every screen's chrome |
| 2. Auth screens | Password rules placement, autocomplete attrs, login copy | Small; risk is manual field rendering breaking form validation |
| 3. Join + household | F-11 must-fix, copy button, regenerate confirm, join acknowledgement, household naming | Heaviest phase (9 findings); signal handler must be idempotent |
| 4. Add medicine form | F-14 must-fix, overlay suggestions, substance preview, `<select>` producer, sort fix, holder, trim | Significant JS refactoring in autocomplete.js |
| 5. List screen | Demoted delete, expanded partials, aggregated items, confirm dialog, duplicate flash | F-25 aggregation adds new dataclass + template change |
| 6. Check screen | Verdict sentence, back link, query persistence | Lightest phase; template-only |

**Prerequisites:** S-01 through S-05 shipped (they are).
**Estimated effort:** ~6 sessions across 6 phases.

## Open Risks & Assumptions

- F-25 aggregation changes `DuplicateGroup`'s template contract — any test that iterates `group.items` directly may need updating to use `group.stacks`
- F-11 signal handler runs on every login, not just invite-driven ones — must be cheap (one session key check, usually no-op)
- F-13+ removes auto-create: any integration test that assumes signup creates a household will break — tests must be updated in Phase 3

## Success Criteria (Summary)

- An invited existing user who logs in joins the household (F-11 — currently broken)
- Adding without picking a suggestion shows "Wybierz lek z listy podpowiedzi", not "To pole jest wymagane" (F-14 — currently broken)
- The list screen's hierarchy is inverted: duplicate signals prominent, delete subordinate
