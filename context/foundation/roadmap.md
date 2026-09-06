---
project: domowa-apteka
version: 2
status: draft
created: 2026-08-03
updated: 2026-09-05
prd_version: 1
main_goal: speed
top_blocker: decisions
---

# Roadmap: domowa-apteka

> Derived from `context/foundation/prd.md` (v1) + auto-researched codebase baseline.
> Edit-in-place; archive when superseded.
> Slices below are listed in dependency order. The "At a glance" table is the index.

## Vision recap

Households buy duplicate medicine because a plain list cannot tell them that "Apap" and
"Paracetamol Hasco" are the same drug — different doctors prescribe different brand names
for the same active substance. This app resolves every product a household enters to its
set of active substances, so two boxes that resolve to the same set are recognised as full
duplicates, and a combination product that shares only some substances with another box is
recognised as a partial duplicate. That resolution step is the whole reason the app exists
rather than a spreadsheet.

## North star

**S-02: user adds a pharmaceutical by name and the app resolves and records its active
substance(s)** — this is the one claim in the PRD that has never been tested against
reality, and every other slice is downstream of it.

> "North star" here means: the smallest end-to-end slice whose successful delivery would
> prove the product's central idea works — placed as early as its Prerequisites allow,
> because everything else only matters if this one succeeds. If a typed product name cannot
> be reliably resolved to a substance set from the official registry, duplicate flagging
> has nothing to compare and the product has no reason to exist.

## At a glance

| ID   | Change ID                          | Outcome (user can …)                                                                        | Prerequisites | PRD refs                     | Status   |
| ---- | ---------------------------------- | ------------------------------------------------------------------------------------------- | ------------- | ---------------------------- | -------- |
| F-01 | `registry-substance-data`          | (foundation) product → active-substance records from the official registry are queryable locally, each traceable to its source row | —             | FR-001, FR-002, NFR (verified sources) | done |
| F-02 | `registry-freshness-refresh`       | (foundation) registry data refreshes on a schedule and the app knows when it last succeeded | F-01          | NFR (registry freshness)     | done     |
| S-01 | `household-accounts-and-invites`   | sign in, create a household, invite another adult by link/code, and have them join with full symmetric access | —             | FR-005, US-02, Access Control | done     |
| S-02 | `add-drug-with-substance-resolution` | add a pharmaceutical by name with registry-backed autocomplete, see its resolved active substance(s) — or a clear lookup-failure message — and have the item appear on the shared household list | F-01, S-01    | FR-001, FR-002, US-01        | done |
| S-03 | `duplicate-flagging-on-list`       | see household list items flagged as full duplicates (identical substance sets) and partial duplicates (overlapping but not identical) | S-02          | FR-003, US-03                | done |
| S-04 | `expiration-date-per-item`         | optionally record an expiration date when adding or editing an item                         | S-02          | FR-004                       | parked   |
| S-05 | `prescription-duplicate-check`      | check a product they are about to buy against the household list **without adding it**, and see whether something already at home is a full or partial substance match | S-03          | FR-003, §Business Logic (see Q4) | done |
| S-06 | `ux-audit-and-flow-fixes`           | reach every core action in fewer, clearer steps, on a layout criticised by walking the running app as a user rather than reading its templates as its author | S-03          | US-01, US-03, NFR (mobile web, 1 s ack) | planning |
| S-07 | `visual-refresh`                    | read the app as a finished product — one deliberate type, colour, spacing and state vocabulary in place of stock Pico defaults | S-06          | NFR (mobile web)             | proposed |

## Streams

Navigation aid — groups items that share a Prerequisites chain. Canonical ordering still
lives in the dependency graph below; this table is the proposed reading order across
parallel tracks.

| Stream | Theme                  | Chain                                              | Note                                                                                                                                                     |
| ------ | ---------------------- | -------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| A      | Path to the north star | `F-01` / `S-01` (parallel) → `S-02` → `S-03` / `S-04` | Two independent heads with no prerequisites — build them in parallel, which is the main lever under a `speed` goal. They converge at `S-02`, which needs both the registry data and a household to publish into; `S-03` and `S-04` then fan out independently of each other. |
| B      | Data freshness         | `F-02`                                             | Side branch off `F-01`, not on the path to the north star. Sequenced after `S-02` ships: the freshness promise only starts costing anything once real users read substance data. |
| C      | Life after the payoff  | `S-03` → `S-05`; `S-03` → `S-06` → `S-07`          | Added 2026-08-29. Everything here sits downstream of the shipped duplicate rule and needs no new foundation. `S-05` and `S-06` are independent of each other and may be built in either order; `S-07` is deliberately behind `S-06` so the same screens are not styled twice. |

## Baseline

What's already in place in the codebase as of `2026-08-03` (auto-researched + user-confirmed).
Foundations below assume these are present and do NOT re-scaffold them.

- **Frontend:** absent — no app modules, `TEMPLATES.DIRS` is `[]`, no CSS/JS tooling in `pyproject.toml`. Load-bearing because an NFR requires the product to be usable from a phone's mobile web browser.
- **Backend / API:** partial — Django 5.2 + gunicorn running; a single `health` view at `domowa_apteka/urls.py:31`; `INSTALLED_APPS` is stock `django.contrib` only, zero project apps.
- **Data:** partial — Postgres provisioned and `DATABASE_URL` wired via `${{Postgres.DATABASE_URL}}`; the `django_migrations` table exists. No domain models of any kind. Driver and connection are present; schema is not.
- **Auth:** partial — `django.contrib.auth` and `AuthenticationMiddleware` are wired, a superuser exists, `/admin/` login verified end-to-end over HTTPS. Missing is the *user-facing* half: no login/registration views, no household model, no invite flow.
- **Deploy / infra:** present — Railway, live at `https://web-production-f61ed.up.railway.app`, config-as-code in git-tracked `railway.json`, secrets wired, EU West region. Deploy is manual `railway up --service web --ci`; there is no CI and no GitHub remote. See `context/deployment/deploy-plan.md`.
- **Observability:** absent — no `LOGGING` block in `settings.py`, no error tracking or metrics libraries in dependencies.

> Note: `context/foundation/tech-stack.md` was corrected on 2026-08-04 — `deployment_target`
> now reads `railway`, matching the verified live deploy. Its `ci_provider: github-actions`
> and `ci_default_flow: auto-deploy-on-merge` deliberately remain as a statement of **intent**:
> there is no CI and no git remote today, and the hand-off schema's `ci_provider` enum has no
> `none` value, so the gap is stated in that file's body paragraph instead. See Open Roadmap
> Question 4.

## Foundations

### F-01: Registry-backed product and active-substance data

- **Outcome:** (foundation) a local, queryable copy of product → active-substance records drawn from the official Polish national medicinal-products registry, loaded by one repeatable command, with every substance value traceable back to the source row it came from.
- **Change ID:** `registry-substance-data`
- **PRD refs:** FR-001, FR-002, NFR (verified sources)
- **Unlocks:** `S-02` (the north star cannot resolve anything without this data); resolves PRD Open Question 3 as a by-product of planning it; establishes the provenance rule that `S-03`'s duplicate comparison depends on being trustworthy.
- **Prerequisites:** —
- **Parallel with:** S-01
- **Blockers:** —
- **Unknowns:**
  - What is the concrete ingestion approach for the registry — bulk file, API, scrape? What update cadence does the registry itself publish on? (PRD Open Question 3) — Owner: user. Block: no. The PRD marks this non-blocking; answering it is the first act of planning this item, not a precondition for planning it.
  - How messy are the source substance fields in practice, and what normalization is permitted without inventing an identity the source does not state? — Owner: user. Block: no.
- **Risk:** Scoped deliberately to a one-shot load, not a pipeline — enough to prove resolution works, nothing more. The real hazard is scope creep into "ingest and normalize the entire registry cleanly", which would consume the whole MVP budget before a single user-visible screen exists. The NFR's ban on guessing means normalization has a hard edge: reformatting a value is allowed, inferring one is not.
- **Status:** done

### F-02: Scheduled registry refresh with a trustworthy freshness signal

- **Outcome:** (foundation) registry data refreshes on a schedule, and the app records and surfaces its own last-successful-run timestamp rather than inferring freshness from the scheduler.
- **Change ID:** `registry-freshness-refresh`
- **PRD refs:** NFR (registry freshness)
- **Unlocks:** the verification path for the freshness NFR that `S-02` and `S-03` both rely on — without an app-side timestamp there is no way to check whether the substance data a user is looking at is current.
- **Prerequisites:** F-01
- **Parallel with:** S-01, S-02, S-03, S-04
- **Blockers:** —
- **Unknowns:**
  - What signal distinguishes "the scheduler fired" from "the data is current", given that a skipped run leaves no error behind? — Owner: user. Block: no.
- **Risk:** `context/foundation/infrastructure.md` records that the platform's cron silently *drops* a scheduled run when the previous execution is still active — it does not queue it, and it does not error. So the naive design ("the cron is scheduled, therefore the data is fresh") is documented to be wrong here. This is why the outcome is an app-side timestamp, not a cron configuration. Sequenced after the north star because the freshness promise only starts costing anything once real users are reading substance data.
- **Status:** done

## Slices

### S-01: Household accounts and invites

- **Outcome:** an adult can sign in, create a household, generate a shareable invite link or code, and the invited adult can join through it and immediately see the household's shared list with full symmetric access.
- **Change ID:** `household-accounts-and-invites`
- **PRD refs:** FR-005, US-02, Access Control
- **Prerequisites:** —
- **Parallel with:** F-01, F-02
- **Blockers:** —
- **Unknowns:**
  - Email/password or passwordless? (PRD Open Question 1) — Owner: user. Block: no. `django.contrib.auth` is already wired and the admin login works, so email/password is the zero-cost default; passwordless would be a deliberate deviation.
  - Do invite links expire, and can they be revoked? The PRD specifies no pending/partial-member state but says nothing about invite lifetime. — Owner: user. Block: no.
- **Risk:** Sequenced first among slices despite not being the north star, because it has no prerequisites at all and the north star cannot publish an item to a "shared household list" that does not exist. The minimal user-facing login surface is folded into this slice rather than split into its own foundation — the baseline shows auth is half-wired already, and a standalone auth item would trace to no PRD user story. Main hazard is the invite flow quietly growing into account management the PRD never asked for.
- **Status:** done

### S-02: Add a drug and see its active substance(s) resolved

- **Outcome:** an adult can add a pharmaceutical by typing its name with registry-backed autocomplete, see which active substance(s) the app resolved for it — or a clear message that lookup failed — and have the item appear on the shared household list where other members see it without a manual refresh step.
- **Change ID:** `add-drug-with-substance-resolution`
- **PRD refs:** FR-001, FR-002, US-01
- **Prerequisites:** F-01, S-01
- **Parallel with:** F-02
- **Blockers:** —
- **Unknowns:**
  - When the registry holds several products under the same name but different strength or form, what does autocomplete show so the user picks the right one? FR-001's revision says autocomplete "disambiguates specific products" but does not say how. — Owner: user. Block: no.
  - When lookup fails, is the item still saved (with an unresolved marker) or is the save rejected? US-01 requires the failure be visible; US-03 requires unresolved items be shown separately — which implies saved, but the PRD never states it. — Owner: user. Block: no.
- **Risk:** The north star. Everything unproven in this project lives here: whether the registry can be queried fast enough to feel like autocomplete, and whether a real product name resolves to a substance set a household would recognise. The NFR requiring acknowledgement within one second bites in this slice specifically. Sequenced as early as its Prerequisites permit — it cannot come before F-01 (no data) or S-01 (nowhere shared to publish into).
- **Status:** done

### S-03: Full and partial duplicates flagged on the household list

- **Outcome:** an adult viewing the shared household list sees items whose active-substance sets are identical flagged as full duplicates, items whose sets overlap but differ flagged as partial duplicates, and items whose substances could not be resolved shown separately rather than grouped or guessed into a relationship.
- **Change ID:** `duplicate-flagging-on-list`
- **PRD refs:** FR-003, US-03
- **Prerequisites:** S-02
- **Parallel with:** S-04, F-02
- **Blockers:** —
- **Unknowns:**
  - A combination product can be a partial duplicate of several other items at once — how is that presented without the list becoming unreadable? The PRD states the requirement but not the display shape. — Owner: user. Block: no.
  - Do flags recompute on read, or on write when an item is added? US-03 requires them to update automatically with no manual step, which both satisfy. — Owner: user. Block: no.
- **Risk:** This is the payoff the whole product is built around, and it is also the slice most likely to be judged on feel rather than correctness — a technically correct partial-duplicate flag that reads as noise fails the user story. Deliberately sequenced after S-02 rather than merged into it: merging would put four of the five must-have requirements in one slice, and duplicate flagging cannot be exercised at all until at least two items with resolved substances exist.
- **Status:** done

### S-04: Optional expiration date per item

- **Outcome:** an adult can optionally record an expiration date when adding or editing a pharmaceutical item, without that field adding friction to the core add flow.
- **Change ID:** `expiration-date-per-item`
- **PRD refs:** FR-004
- **Prerequisites:** S-02
- **Parallel with:** S-03, F-02
- **Blockers:** —
- **Unknowns:** —
- **Risk:** The only `nice-to-have` requirement in the PRD, and under this roadmap's `speed` goal it was named at generation time as the first item to park if evenings run short. **On 2026-08-29 that call was made** — see §Parked. Nothing downstream depended on it: no slice lists `S-04` as a prerequisite, and the duplicate rule reads substance sets, not dates. What parking costs is stated plainly so it is not rediscovered as a surprise — FR-004 and the PRD's Secondary Success Criterion now have no active roadmap item, and a future expiration-alerting feature will start from an empty column rather than a year of collected dates.
- **Status:** parked (2026-08-29)

### S-05: Check a product against the household list without adding it

- **Outcome:** an adult standing in a doctor's office can type or pick a product the household does *not* own — the one just prescribed, or a proposed alternative — and see straight away whether something already at home is a full substance match (identical set) or a partial one (overlapping but not identical), with nothing written to the household list as a side effect.
- **Change ID:** `prescription-duplicate-check`
- **PRD refs:** FR-003, §Business Logic — no new FR; see Open Roadmap Question 4
- **Prerequisites:** S-03
- **Parallel with:** S-06, S-07
- **Blockers:** —
- **Unknowns:**
  - What does the answer have to carry beyond the flag, to be usable in the two minutes the appointment allows — strength and form, how many packs are held, who added it, when? A flag settles a comparison; it does not settle a decision. — Owner: user. Block: no.
  - Is the check purely transient, or does it leave a trace ("checked 2026-09-02, bought anyway")? Anything durable turns a read-only screen into a write and pulls in a model change; transient keeps the slice at one view and one template. — Owner: user. Block: no.
  - Where is the entry point — its own screen, or a field at the top of the existing list? `S-06`'s audit will have an opinion about this too, so whichever slice lands second should defer to the first. — Owner: user. Block: no.
- **Risk:** Cheap by construction, and that was on purpose: `pharmacy/duplicates.py` was written set-keyed (`classify(a: frozenset[str], b: frozenset[str])`) rather than closed over a list of `Item`s, specifically so a candidate product that is not an item could be compared through the same rule. So the comparison is not where the risk lives. The framing is. A screen that says "you already have this" sits one wording away from saying "so you do not need that prescription" — a substitution claim the app is not licensed to make, and one the household will make anyway on the strength of the flag. The NFR that bans guessing applies to the sentence on the screen, not only to the data behind it. Scope is a substance-set fact, presented as a fact, next to the doctor rather than instead of them.
- **Status:** done

### S-06: UX audit and the flow fixes it earns

- **Outcome:** an adult can reach each core action — add an item, scan the list for duplicates, invite a member — in fewer and more obvious steps, with ordering, labels, and affordances chosen from a written audit of the running app instead of from whatever the templates grew into over five slices.
- **Change ID:** `ux-audit-and-flow-fixes`
- **PRD refs:** US-01, US-03, NFR (usable from a phone's mobile browser), NFR (acknowledgement within one second)
- **Prerequisites:** S-03
- **Parallel with:** S-05
- **Blockers:** —
- **Unknowns:**
  - Which findings are in scope? The audit will surface more than one slice can carry. The triage is a product decision and belongs to the user, not to whoever wrote the audit. — Owner: user. **Block: yes, at plan time** — `/10x-plan` cannot start against an unranked findings list without silently choosing scope for itself.
  - Is Polish the only UI language, and is copy rewriting inside this slice or outside it? Wording is usually half of any findings list, and it is the half that changes what the screens *mean*. — Owner: user. Block: no.
- **Risk:** The audit is what makes this slice honest, and it lands as this change's research artifact (`context/changes/ux-audit-and-flow-fixes/ux-audit.md`), not as a roadmap item of its own — a findings list is not a user-visible outcome, so by this roadmap's own rule it is not a slice. Two hazards. First, an audit written by the same agent that wrote the templates grades its own homework: it must be produced by driving the deployed app as a user, on a phone-width viewport, naming screen and observed behaviour per finding, without reading the template source first. Second, an unbounded findings list becomes an unbounded slice, which is why the triage above blocks planning rather than merely informing it. Sequenced after `S-03` because the duplicate presentation is the app's payoff and the thing most worth auditing — auditing before it shipped would have audited the wrong app.
- **Status:** planning

### S-07: Visual refresh

- **Outcome:** an adult reads the app as a finished product rather than a scaffold — one deliberate type scale, colour, spacing, and state vocabulary applied consistently across every screen, including the duplicate badges that carry the whole point of the product.
- **Change ID:** `visual-refresh`
- **PRD refs:** NFR (usable from a phone's mobile browser)
- **Prerequisites:** S-06
- **Parallel with:** S-05
- **Blockers:** —
- **Unknowns:**
  - Stay on Pico with a theme layer over it, or leave it? `context/foundation/tech-stack.md` chose classless Pico deliberately; leaving it is a stack decision with its own cost, not a styling preference. — Owner: user. Block: no.
  - What do *full duplicate*, *partial duplicate*, and *unresolved* look like as one system? Three states that must separate at a glance, on a phone, in daylight, without leaning on colour alone. This is the only visual decision the product's core claim depends on. — Owner: user. Block: no.
- **Risk:** Behind `S-06` on purpose — styling a layout that `S-06` is about to rearrange pays for the same screens twice, and the audit is what says which screens deserve the investment at all. Kept separate from `S-06` rather than merged, for two reasons: the two rest on different evidence (observed behaviour versus appearance), and they have different park value — under the `speed` goal, flow fixes ship and a visual refresh is the last thing to cut, which is only possible if it is its own row. The hazard is a redesign that quietly re-litigates `S-06`'s decisions, or that introduces a component system this project has no evenings to maintain.
- **Status:** proposed

## Backlog Handoff

| Roadmap ID | Change ID                            | Suggested issue title                                          | Ready for `/10x-plan` | Notes                                             |
| ---------- | ------------------------------------ | -------------------------------------------------------------- | --------------------- | ------------------------------------------------- |
| F-01       | `registry-substance-data`            | Load product → active-substance data from the official registry | yes                   | Run `/10x-plan registry-substance-data`           |
| F-02       | `registry-freshness-refresh`         | Scheduled registry refresh with app-side freshness timestamp    | no                    | Needs F-01 first                                  |
| S-01       | `household-accounts-and-invites`     | Household creation, invite link, and join flow                  | yes                   | Run `/10x-plan household-accounts-and-invites`    |
| S-02       | `add-drug-with-substance-resolution` | Add a drug by name and resolve its active substances            | no                    | Needs F-01 and S-01 first — this is the north star |
| S-03       | `duplicate-flagging-on-list`         | Flag full and partial duplicates on the household list          | no                    | Needs S-02 first                                  |
| S-04       | `expiration-date-per-item`           | Optional expiration date field on an item                       | no                    | **Parked 2026-08-29** — out of MVP scope; see §Parked |
| S-05       | `prescription-duplicate-check`       | Check a product against the household list without adding it    | yes                   | Run `/10x-new prescription-duplicate-check`       |
| S-06       | `ux-audit-and-flow-fixes`            | Audit the running app, then fix the flows the audit earns       | yes                   | Audit → user triages findings → `/10x-plan`. Planning is blocked until the triage exists |
| S-07       | `visual-refresh`                     | One visual vocabulary across every screen                       | no                    | Needs S-06 first                                  |

## Open Roadmap Questions

1. **What auth mechanism backs the login-based accounts — email/password or passwordless?** — Owner: user. Block: `S-01` (non-blocking; `django.contrib.auth` is already wired, so email/password is the default unless overridden).
2. **When and how does the deferred child role return?** — Owner: user. Block: roadmap-wide, future version. v1 ships adult-only symmetric accounts; nothing in this roadmap depends on the answer.
3. **What is the exact integration approach for the official Polish medicinal-products registry?** — Owner: user. Block: `F-01`, and transitively `S-02`, `S-03`, `F-02` (non-blocking for planning; this is the decision that `/10x-plan registry-substance-data` exists to resolve). ~~This is the roadmap's top blocker.~~ Resolved by `F-01`, archived 2026-08-14.
4. **Does `S-05` deserve a PRD amendment, or does it ride on FR-003?** — Owner: user. Block: no. `S-05` was added straight to the roadmap on 2026-08-29 without a new FR, on the argument that it is a third surface for a rule the PRD already states in §Business Logic — which currently reads "the user encounters this rule twice in the MVP flow". That sentence is now one short of true. The cheap fix is a one-line PRD correction the next time `prd.md` is touched; the expensive fix is regenerating the PRD. Recorded here so the discrepancy is deliberate rather than drift.
5. **What claim is the app allowed to make when two products share a therapeutic effect but not a substance?** — Owner: user. Block: the parked *therapeutic-effect matching* item below, and nothing else. This is a definition question before it is a build question, which is why it is parked pending `/10x-shape` rather than sequenced as a slice.

## Parked

- **Barcode / photo scanning for entry** — Why parked: PRD §Non-Goals. v1 ships manual name entry with autocomplete only; fast capture is v2. Noted in the Vision as what makes manual tracking fail in practice, so this is a known deferred cost, not an oversight.
- **Child / restricted accounts** — Why parked: PRD §Non-Goals. v1 is adult-only and symmetric; the view-only child role may return later (Open Roadmap Question 2).
- **Native mobile app / offline-first** — Why parked: PRD §Non-Goals. v1 is mobile-web only.
- **Expiration alerting and notifications** — Why parked: PRD §Success Criteria explicitly defers alerting. It used to be true that `S-04` would at least record the date for a future alerting feature to read; since 2026-08-29 `S-04` is parked too, so this one now sits behind two parked items rather than one.
- **S-04: optional expiration date per item** — Why parked: user decision, 2026-08-29. FR-004 is the PRD's only `nice-to-have`, and its payoff — alerting — is already a Non-Goal, so shipping the field before the 2026-09-14 deadline buys data entry that nothing reads. Cost of the park, stated so it is not rediscovered later: FR-004 and the PRD's Secondary Success Criterion now trace to no active roadmap item, and future alerting starts from an empty column instead of a history of collected dates. Unparking is cheap and self-contained — one optional field on `pharmacy.Item`, one form field, no dependents.
- **Therapeutic-effect matching (Nurofen and Paracetamol both flagged as painkillers)** — Why parked: **user decision, 2026-08-29 — explicitly out of scope for this MVP**, not merely unsequenced. It is not a bigger version of `S-03`, it is a different claim, and it needs `/10x-shape` before it can become a slice at all. Three things are unresolved, none of them technical. (1) *Definition:* "same therapeutic effect" has no single meaning — same symptom relieved, same pharmacological class, and clinically interchangeable are three different sets, and the third is the only one a household actually wants. (2) *Source:* the registry export does carry ATC codes — 21,679 products have one, measured during `F-01` — but `F-01` deliberately did not ingest them (`context/archive/2026-08-07-registry-substance-data/plan.md:102`), because an ATC code cannot decompose a combination product into a substance set. Reusing ATC here means adding a field and re-importing a snapshot, which is cheap, but it also means adopting ATC's grouping as the app's answer to (1) — a decision, not a lookup. Ibuprofen (`M01AE01`) and paracetamol (`N02BE01`) do not share an ATC prefix at any level, so ATC would *not* group the user's own example. (3) *Licence:* the PRD's strongest NFR says the app never guesses a match and never infers an identity absent from the source. "These two do the same job" is exactly such an inference, and it is medical rather than clerical. Whatever ships here needs a sentence in the PRD that permits it, and probably a visible separation from the substance-set flags so a suggestion is never mistaken for an identity.
- **`SECURE_SSL_REDIRECT` and HSTS** — Why parked: both currently off and flagged by `check --deploy`; deferred during deploy because a redirect can turn the healthcheck's 200 into a 301, and HSTS is browser-cached and semi-irreversible. Safe to revisit, but not required to reach the north star.

## Done

(Empty on first generation. `/10x-archive` appends entries here when a change whose
`Change ID` matches a roadmap item is archived.)

- **S-01: an adult can sign in, create a household, generate a shareable invite link or code, and the invited adult can join through it and immediately see the household's shared list with full symmetric access.** — Archived 2026-08-07 → `context/archive/2026-08-05-household-accounts-and-invites/`. Lesson: —.
- **F-01: (foundation) a local, queryable copy of product → active-substance records drawn from the official Polish national medicinal-products registry, loaded by one repeatable command, with every substance value traceable back to the source row it came from.** — Archived 2026-08-14 → `context/archive/2026-08-07-registry-substance-data/`. Lesson: A plan can contradict itself; resolve it in code *and* write the resolution back.
- **S-02: an adult can add a pharmaceutical by typing its name with registry-backed autocomplete, see which active substance(s) the app resolved for it — or a clear message that lookup failed — and have the item appear on the shared household list where other members see it without a manual refresh step.** — Archived 2026-08-19 → `context/archive/2026-08-14-add-drug-with-substance-resolution/`. Lesson: —.
- **F-02: (foundation) registry data refreshes on a schedule, and the app records and surfaces its own last-successful-run timestamp rather than inferring freshness from the scheduler.** — Archived 2026-08-20 → `context/archive/2026-08-14-registry-freshness-refresh/`. Lesson: —.
- **S-03: an adult viewing the shared household list sees items whose active-substance sets are identical flagged as full duplicates, items whose sets overlap but differ flagged as partial duplicates, and items whose substances could not be resolved shown separately rather than grouped or guessed into a relationship.** — Archived 2026-08-25 → `context/archive/2026-08-24-duplicate-flagging-on-list/`. Lesson: —.
- **S-05: an adult standing in a doctor's office can type or pick a product the household does *not* own — the one just prescribed, or a proposed alternative — and see straight away whether something already at home is a full substance match (identical set) or a partial one (overlapping but not identical), with nothing written to the household list as a side effect.** — Archived 2026-09-05 → `context/archive/2026-08-29-prescription-duplicate-check/`. Lesson: —.
