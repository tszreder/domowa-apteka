---
project: domowa-apteka
version: 1
status: draft
created: 2026-07-17
context_type: greenfield
product_type: web-app
target_scale:
  users: small
timeline_budget:
  mvp_weeks: 1
  hard_deadline: 2026-09-14
  after_hours_only: true
---

## Vision & Problem Statement

Households lose track of which pharmaceuticals they already have at home, leading to unnecessary duplicate purchases. This is worsened by "zamienniki" — different doctors prescribing different brand names for drugs that share the same active substance — so a household ends up with three boxes under three different names that all do the same thing. The pain shows up when someone needs a medication (or a doctor prescribes one) and isn't sure what's already at home, under what name, or whether it's still in date.

The insight this app is built on: a plain list or spreadsheet can't tell a household that "Apap" and "Paracetamol Hasco" are the same drug — that requires resolving each product to its active substance(s). And because a single product can carry more than one active substance (a combination cold medicine like Gripex is paracetamol + pseudoephedrine), overlap between two products isn't always all-or-nothing — they can be *partial* duplicates that share some active substances but not the full set. Resolving each product to its substance set, and distinguishing full overlap (identical sets) from partial overlap (shared but not identical), is the core value-add over a manual list. The second half of the insight is that manual tracking fails in practice because logging a new box by hand is tedious enough that households give up; fast capture (barcode or photo of the package) is what makes the list realistically stay up to date.

## User & Persona

Any adult member of a household, acting symmetrically — there is no single "household manager" role among adults. Any adult can add a pharmaceutical, check current stock, and see the shared household list. (Child access is a distinct, restricted role — captured in Access Control, not here.)

## Success Criteria

### Primary
- A user can manually enter a pharmaceutical's name, the app resolves and records its active substance, and the item is saved to the shared household list — visible to other household members.

### Secondary
- Basic expiration date tracking: a date can be recorded per item (alerting is deferred, but the field exists).

### Guardrails
- Household data stays private to that household — no cross-household visibility.
- Active-substance lookup failures are surfaced clearly to the user, never silently dropped or guessed.

## User Stories

### US-01: Household member adds a pharmaceutical and it's visible to the household

- **Given** a logged-in adult who belongs to a household
- **When** they manually enter a pharmaceutical's name and save it
- **Then** the app resolves and records its active substance, saves the item to the shared household list, and any other adult member of that household sees it

#### Acceptance Criteria
- If the active substance cannot be resolved, the save is not silent — the user sees a clear message that lookup failed
- The item is immediately visible to other household members without requiring a manual refresh/re-sync action beyond normal navigation
- Items are never visible to members of a different household

### US-02: Adult creates a household and invites another adult, who joins

- **Given** a logged-in adult with no household yet
- **When** they create a household, generate a shareable invite link/code, and send it to another adult through any external channel (text, messaging app, etc.)
- **Then** the invited adult can use the link/code to join the household as a full symmetric member and immediately sees the existing shared pharmaceutical list

#### Acceptance Criteria
- Creating a household requires no other adult to already exist in it (bootstrap case)
- The invite mechanism is a shareable link or code — no in-app email delivery is required for v1
- Joining via the link/code grants full symmetric access immediately; there is no pending/partial-member state
- A newly joined adult sees all existing items on the household list right away, with no separate "starter" view

### US-03: Household member sees full and partial zamienniki flagged on the list

- **Given** a logged-in adult belonging to a household with at least two items whose resolved active-substance sets overlap
- **When** they view the shared household list
- **Then** items with an identical active-substance set are surfaced as full duplicates (true zamienniki), and items that share some but not all of their active substances are surfaced as partial duplicates — each shown distinctly rather than as unrelated flat entries

#### Acceptance Criteria
- Two items are treated as full duplicates only when their active-substance sets are identical; items sharing some-but-not-all substances are flagged as partial duplicates, never merged with full duplicates
- A single product with multiple active substances is stored as one item and may be a partial duplicate of several other items at once
- An item whose active substances could not be resolved (lookup failure) is shown separately, never silently grouped, hidden, or guessed into a duplicate relationship
- Full/partial duplicate flags update automatically as items are added — no manual re-organization step required

## Functional Requirements

- FR-001: Adult can add a pharmaceutical by entering its name, with autocomplete suggestions drawn from the official Polish national medicinal-products registry (the public drug registry maintained by the Health Ministry). Priority: must-have
  > Socrates: Counter-argument considered: "free-text entry with no strength/form distinction risks two different products colliding under one substance." Resolution: revised — name entry becomes autocomplete-assisted against the Polish pharmaceutical database (needed anyway for FR-002's active-substance lookup), which disambiguates specific products rather than relying on free text.
- FR-002: App resolves and records the active substance(s) for an entered pharmaceutical name — a single product may resolve to more than one active substance — using the same official Polish national medicinal-products registry as FR-001's autocomplete. Priority: must-have
  > Socrates: Counter-argument considered: "a drug database with good Polish market coverage might not be reliable at launch." Resolution: kept as written — the existence of a usable Polish pharmaceutical database was confirmed by the user (see FR-001); the exact database/API integration is a downstream implementation concern, tracked in Open Questions.
- FR-003: Adult can view the shared household pharmaceutical list, with items flagged as full duplicates when their active-substance sets are identical and as partial duplicates when the sets overlap but are not identical. Priority: must-have
  > Socrates: Counter-argument considered: "a flat, unsorted list won't surface the 'zamienniki' duplicates that are the whole point of the app." Resolution: revised — FR-003 now includes grouping/flagging by shared active substance, since surfacing duplicates is the app's core value proposition, not a v2 nicety.
- FR-004: Adult can optionally record an expiration date when adding or editing a pharmaceutical item. Priority: nice-to-have
  > Socrates: Counter-argument considered: "without alerts (deferred), recording a date has no visible payoff in v1 — pure data-entry cost." Resolution: kept, but made explicitly optional at add-time so it doesn't add friction to the core add-flow while still laying groundwork for future alerting.
- FR-005: Adult can create or join a household and invite other adult members. Priority: must-have
  > Socrates: Counter-argument considered: "household invite flow (auth, tokens, join UX) is significant build cost for a 1-week MVP." Resolution: kept as written — sharing across household members is core to the product's value; a single hardcoded household would undercut the MVP's proof of the sharing loop.

## Non-Functional Requirements

- Household medical data is never visible or shared outside the household without explicit consent — no cross-household visibility, no third-party sharing.
- The product is usable directly from a phone's mobile web browser; no app-store install is required.
- A user sees acknowledgement of an add/lookup action within 1 second, and continuous visible feedback during any operation that takes longer.
- Active-substance and product information presented to the user is drawn only from verified sources — the app never guesses or fabricates a match; an unverifiable entry is surfaced as such rather than shown as fact (ties to the Guardrail in Success Criteria). A product's active-substance identity must always trace back to its source record; automated cleanup of messy source data may only normalize how a value is presented (formatting, splitting, trimming) and must never invent or infer a substance identity absent from the source.
- Product and active-substance data reflects the official national medicinal-products registry, current to within about a day of the registry's own updates.

## Business Logic

**The app resolves each pharmaceutical a household enters to its set of canonical active substances, so that products are recognized as full duplicates when their substance sets are identical and as partial duplicates when the sets overlap but differ — regardless of brand name.**

The rule consumes a single user-facing input: the name of a pharmaceutical product as the household member enters it (assisted by autocomplete). Its output is a set of one or more canonical active substances attached to that item — for example, two differently-named boxes that both resolve to exactly {paracetamol} are full duplicates, while a combination product resolving to {paracetamol, pseudoephedrine} is a partial duplicate of a plain paracetamol box, sharing one substance but not the whole set. The user encounters this rule twice in the MVP flow: first at add-time, when the app confirms (or flags failure to confirm) which substance(s) the entered product contains; and again when viewing the household list, where items are flagged as full or partial duplicates by comparing their resolved substance sets, surfacing the "zamienniki" overlaps that motivated the app.

## Access Control

Login-based accounts (email/password or passwordless — mechanism TBD downstream), grouped into a shared household.

For v1, only an **adult** role exists: full manage — add/edit/remove pharmaceuticals, view and edit the full household stock list, create/join a household, invite other adult members. All adult members act symmetrically; no household-manager/admin distinction.

A restricted **child** role (view-only access to medications assigned to them; no login/account needed initially) was discussed but is explicitly deferred — see Non-Goals and Open Questions. It may return in a later version to support older children checking their own assigned medications.

Unauthenticated users have no access — the household list is not publicly visible.

## Non-Goals

- **Barcode/photo scanning for entry** — v1 ships manual name entry with autocomplete only; fast-capture via barcode or photo is deferred to v2.
- **Child/restricted accounts** — v1 ships adult-only, symmetric accounts; the view-only child role is explicitly deferred to a later version.
- **Native mobile app / offline-first** — v1 is mobile-web only, no app-store install and no offline support.

## Open Questions

1. **What auth mechanism backs the login-based accounts — email/password or passwordless?** — Owner: user, resolved downstream during tech-stack selection. The Access Control model commits to login-based household accounts; the concrete mechanism is deliberately deferred. Block: no (does not block PRD; must resolve before build).
2. **When and how does the deferred child role return?** — Owner: user, future version. v1 ships adult-only symmetric accounts (see Non-Goals); the view-only child role (medications assigned to them, no login initially) is out of scope now. Open: whether it returns in v2+ and under what access shape.
3. **What is the exact integration approach for the official Polish medicinal-products registry?** — Owner: user, resolved downstream during tech-stack selection. The registry's existence and suitability as the authoritative source are confirmed; the concrete ingestion/parsing/normalization approach (feed cadence, source-field cleanup) is a downstream implementation concern captured in the shape-notes `## Forward: tech-stack` block. Block: no (does not block PRD; feeds `/10x-tech-stack-selector`).
