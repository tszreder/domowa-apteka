# Test Plan

> Phased test rollout for this project. Strategy is frozen at the top
> (§1–§5); cookbook patterns at the bottom (§6) fill in as phases ship.
> Read before writing any new test.
>
> Refresh: re-run `/10x-test-plan --refresh` when stale (see §8).
>
> Last updated: 2026-08-29

## 1. Strategy

Tests follow four non-negotiable principles for this project:

1. **Cost × signal.** The cheapest test that gives a real signal for the
   risk wins. Do not promote to e2e because e2e "feels safer." Do not put a
   vision model on top of a deterministic check that already catches the
   regression.
2. **User concerns are first-class evidence.** Risks anchored in "the team
   is worried about X, and the failure would surface somewhere in <area>"
   carry the same weight as PRD lines or hot-spot data.
3. **Risks are scenarios, not code locations.** This plan documents *what
   could fail* and *why we believe it's likely* — drawn from documents,
   interview, and codebase *signal* (churn, structure, test base). It does
   NOT claim to know which line owns the failure. That knowledge is
   produced by `/10x-research` during each rollout phase. If the plan and
   research disagree about where the failure lives, research is the
   ground truth.
4. **A test counts only once it has been shown to fail for the right
   reason.** This project has already shipped three tests that could not
   fail — one whose setup guaranteed its own assertion, one mutation-dead
   cross-household check, and two parser rules no test observed. A green
   suite is not evidence; a test that was watched to go red when the
   behaviour it protects was broken is. Every test written for a §2 risk
   carries a recorded falsification: what was changed to break it, and that
   it went red.

Hot-spot scope used for likelihood weighting: `households/`, `registry/`,
`pharmacy/`, `domowa_apteka/`, `templates/`, `static/`, `.github/` —
excluding `.venv/`, `context/`, `docs/`, `staticfiles/`, `__pycache__/`.

## 2. Risk Map

The top failure scenarios this project must protect against, ordered by
risk = impact × likelihood. Risks are failure scenarios in user / business
terms, not test names. The Source column cites the *evidence that surfaced
this risk* — never a specific file as "where the failure lives" (that is
research's job, see §1 principle #3).

| # | Risk (failure scenario) | Impact | Likelihood | Source (evidence — not anchor) |
|---|---|---|---|---|
| 1 | A user picks a product from autocomplete that is not the box in their hand — same name, different strength, form, or manufacturer — so the item is saved under a wrong identity and every substance claim the app later makes about it is confidently wrong | High | High | interview Q1; PRD FR-001 Socrates note (strength/form collision is the counter-argument that forced autocomplete to exist); roadmap S-02 Unknown 1, which records the disambiguation question as unresolved |
| 2 | A registry import fails, lands truncated, or rewinds to an older snapshot, and the app keeps serving the previous substance data as though it were current | High | High | interview Q1; PRD NFR (registry data current to within about a day); roadmap F-02 Risk (the platform's cron silently drops a run that overlaps the previous one — no queue, no error); archive `2026-08-07-registry-substance-data` review findings on a truncated snapshot escaping the guard, and on an older snapshot rewinding freshness while deactivating live products |
| 3 | A product resolves to the wrong active-substance set — a substance the box does not contain, or a missing one in a combination product | High | Medium | interview Q1; PRD Business Logic and NFR (the app never guesses or fabricates; a substance identity must trace back to its source record); `context/foundation/lessons.md` "a plan can contradict itself" (a source placeholder value nearly became a permanent substance record with no links); archive `2026-08-07-registry-substance-data` review finding that two parser rules are implemented and unobservable by any test |
| 4 | A lookup failure is swallowed — the item is saved as though it resolved, or disappears — so the user believes the app knows what is in the box when it does not | High | Medium | PRD Success Criteria Guardrail (lookup failures surfaced clearly, never silently dropped or guessed); PRD US-01 AC (the save is not silent); PRD US-03 AC (an unresolved item is shown separately, never grouped, hidden, or guessed into a duplicate relationship) |
| 5 | A household member reads another household's medicine list — the request is authenticated, but ownership of the resource is never checked | High | Medium | interview Q1; PRD NFR (household medical data never visible outside the household) and US-01 AC (items never visible to members of a different household); archive `2026-08-05-household-accounts-and-invites` review finding that the cross-household assertion in the suite today is mutation-dead — the guardrail is asserted but not proven |
| 6 | An invite artifact keeps granting full symmetric access to household medical data after it should have stopped — forwarded, leaked, or reused by someone who has left the household | Medium-High | Medium | PRD Access Control (joining grants immediate full symmetric access with no pending state); roadmap S-01 Unknown 2, which records invite expiry and revocation as unresolved; archive `2026-08-05-household-accounts-and-invites` review finding that the invite token is not consumed on the login path |
| 7 | Two correctly-resolved medicines are placed in the wrong relationship to each other — flagged as the same when they are not, or shown as unrelated when they share an active substance — or a correct relationship is presented wrongly, with the shared-substance summary contradicting the detail line beneath it. The household then acts on a flag that is not true: keeps a real duplicate, or discards a box that was never one. The case where one medicine partially overlaps several others at once is where both failures are most likely, and nothing but a human implementation review catches either before merge | High | Medium | interview Q1 (the top production worry) and Q3 (the least-confident area); archive `2026-08-24-duplicate-flagging-on-list` review, where 3 of its 5 findings were real defects surfaced by human reading over a green suite; the `pharmacy/` hot-spot directory (§4 churn), which corroborates rather than originates this risk; and a self-contradicting rendering measured during the 2026-08-29 refresh in exactly the several-partners-at-once case |

Abuse lens applied. Risk #5 is the authorization/ownership case (IDOR) and
risk #6 the lifetime of a credential-equivalent artifact. Resource abuse
(flooding the suggestion endpoint) and secret leakage were both considered
and deliberately excluded — at household scale there is no rate-limiting
surface worth a rollout phase, and no third-party credential sits in the
request path. See §7 rather than a padded risk map.

Likelihood is not argued from churn anywhere in this table. The Phase 2
interview answered "uniform" to the question of where change feels least
confident, and that answer still governs. As of the 2026-08-29 refresh churn
no longer understates the newest surfaces — `pharmacy/` has grown into a
genuine hot spot — but the rule is unchanged: risk #7 cites that churn as
corroboration, never as its origin. Churn is recorded in §4 as context only.

**Challenger note (2026-08-29).** Roadmap slices S-05, S-06 and S-07 are
proposed, not built, and none licenses a risk row yet — a row would describe
software that does not exist. Their absence from this table is a decision, not
an oversight, and it binds the next refresh too: add a row when a slice ships,
not when it is scheduled. S-05 (`prescription-duplicate-check`) is the one to
watch, because it is built to consume the same duplicate primitive risk #7
covers — a defect left there today is inherited by S-05 rather than
re-introduced.

### Risk Response Guidance

| Risk | What would prove protection | Must challenge | Context `/10x-research` must ground | Likely cheapest layer | Anti-pattern to avoid |
|---|---|---|---|---|---|
| #1 | Given two registry entries that share a name but differ in strength, form, or manufacturer, the user is shown enough to tell them apart, and the item that gets saved is the one that was chosen — not the first match | "The name matched, therefore the right product was selected." A correct substance resolution for the *wrong product* is indistinguishable from success at every layer below the UI | What the suggestion payload carries, what the save path persists out of it, and whether product identity travels as a stable registry key or is re-derived from the typed string | Integration over the suggestion and save path, driven by fixture rows deliberately built as name collisions | A fixture set with one product per name — it makes the risk unrepresentable, and the test then passes by construction |
| #2 | A truncated, malformed, or older-than-current snapshot is refused, the previous good data survives intact, and the freshness signal does not advance; a stale state is visible to the app as stale rather than indistinguishable from fresh | "The scheduled run completed, therefore the data is current." And its sibling: "the import raised nothing, therefore it succeeded" | Which exception types the import boundary actually catches, where the freshness record is written relative to the import transaction, and what the app reports when the last success is old | Integration over the import command with truncated, malformed, and older-snapshot fixture variants; freshness assertions driven by an injected clock | Asserting the happy path over a broad `except` that swallows; and testing the scheduler's configuration instead of the app-side signal |
| #3 | For a product whose source row is known, the resolved substance set equals what that source row states — including the multi-substance case — and placeholder values never become substances | "Whatever the parser returns is correct." The oracle comes from the source registry row, never from what the parser currently produces | Which source field is authoritative, how a multi-substance row is represented, and which values are placeholders rather than substance identities | Unit tests over parse and resolve, with fixture rows whose expected sets are read off the source data | Snapshotting current parser output as the expectation — that certifies today's bugs and can never fail for the right reason |
| #4 | A product that cannot be resolved produces a visible, specific failure state for the user, and the item is persisted in a state that keeps it out of any duplicate relationship | "An empty result means the product has no substances." An unresolved item and a genuinely substance-free item must not be the same stored state | What the save path does when resolution misses, and how an unresolved item is represented so later duplicate logic cannot group it | Integration over the add flow with an input that cannot resolve | Asserting an HTTP 200 and nothing about what the user actually sees or what was persisted |
| #5 | A member of household A issuing a well-formed request for a household B resource is refused — and the test goes red when the ownership check is deleted | "The user is logged in, therefore the object is theirs." Ownership is a per-object check, not a session check | Which views take an identifier from the request, and whether the queryset is scoped by membership or filtered after the fetch | Integration per identifier-taking view, each one falsified | Repeating the pattern already found in this suite — asserting a status code without proving which branch produced it |
| #6 | An invite artifact stops working once the condition the product intends has occurred, and presenting a spent or revoked one refuses cleanly rather than erroring or silently re-joining | "One person joined, therefore the link is done." The product has not decided expiry or revocation, so the rule must be stated before it can be tested | The intended lifetime rule — a product decision, currently unrecorded — and every path that consumes a token, including login and signup, not only join | Integration over the token paths, once the rule is stated | Testing whatever the code happens to do today and calling it the requirement; that test has no oracle |
| #7 | Which medicines are grouped together, which shared substances are named against each one, and the order the groups appear in are all derivable from the substance sets the boxes carry — and the tests protecting them go red when the grouping, the accumulation of a second overlapping medicine, or the display order is mutated. Two shapes must be representable: one medicine overlapping two or more others at once, and two different registry products that share a display name | "The review already caught this, so it is covered." Two of that review's findings did land committed, mutation-checked regression tests — the suite grew 176 → 178 for exactly that reason — so the challenge is not that the review was shallow. It is narrower and verified: every committed assertion about a medicine's overlapping partners expects exactly one partner, so the path that accumulates a second one is asserted at no layer, and the de-duplication that feeds the user-visible summary line has no test that reaches it. A green suite here means the easy shape is covered | Which layer owns grouping, which owns the shared-substance annotation, and which owns display order; where de-duplication is applied and where it is not, since a summary and its detail line are produced by different paths; and whether the review's falsification technique already exists as a repeatable committed test or was run by hand | Unit over the classification and the group assembly, with fixtures where one substance draws two or more partners and where two distinct products share a display name; integration only for the ordering guarantee, since a unit test on the assembler cannot observe a caller re-sorting its output | Re-asserting today's grouping output as the expected value — the oracle problem; expected groups must be derived from substance-set arithmetic. And treating the summary line as evidence for the detail line when the two are produced by different paths and have already been measured disagreeing |

## 3. Phased Rollout

Each row is a discrete rollout phase that will open its own change folder
via `/10x-new`. Status moves left-to-right through the values below; the
orchestrator updates Status as artifacts appear on disk.

| # | Phase name | Goal (one line) | Risks covered | Test types | Status | Change folder |
|---|---|---|---|---|---|---|
| 1 | Coverage truth pass | Produce a written risk-to-test map and prove the assertions claiming to protect risks #1–#6 can fail — bounded to those assertions, ceiling of roughly twelve falsification checks, not a sweep of the whole suite | #1–#6 (verification, not new coverage) | suite audit, falsification checks, repair of unfalsifiable tests | not started | `testing-coverage-truth-pass` (proposed id — folder not yet created) |
| 2 | Add-item integrity | Prove the chosen product is the saved product, that its substances match the source row, and that a resolution failure is visible — including one query-shape assertion for the one-second acknowledgement requirement | #1, #3, #4 | integration, unit, collision fixtures, query-count assertion | not started | — |
| 3 | Ingestion and freshness without a deploy | Make the scheduled import path exercisable in-process, and prove a bad or stale snapshot is refused rather than served as current | #2 | integration, clock-injected assertions | not started | — |
| 4 | Access boundaries and gate wiring | Prove ownership is checked per object and that invite artifacts stop working when intended, then wire the missing CI gates | #5, #6 | integration, falsification checks, gates | not started | — |
| 5 | Duplicate relationship correctness | Prove group membership, shared-substance annotation, and display order are each derived from substance sets rather than from today's output — including one medicine overlapping several others at once | #7 | unit, integration, fan-out fixtures, falsification checks | not started | — |

**Sequencing decision (2026-08-29).** Phases 1 and 2 run now. The previous
refresh held phases 3 and 4 behind roadmap slice S-03
(`duplicate-flagging-on-list`), yielding the evenings before the PRD's
2026-09-14 deadline to the product's payoff. S-03 shipped on 2026-08-25, so that
condition is spent and no longer constrains the rollout. Phases 3, 4 and 5 are
`not started` because nobody has started them — not because anything blocks
them, with the single exception recorded immediately below. Re-run
`/10x-test-plan` to pick up the next one.

**Open decision blocking Phase 4.** The invite lifetime rule — whether links
expire, whether they can be revoked, and on what condition — is unrecorded in
the PRD and open in the roadmap. It is a product decision, not a research
question. It must be answered before Phase 4 is planned, or the resulting test
takes its oracle from the implementation (see risk #6's response row).

## 4. Stack

The classic test base for this project. AI-native tools carry a `checked:`
date so future readers can see which lines need re-verification.

| Layer | Tool | Version | Notes |
|---|---|---|---|
| unit + integration | Django test runner (`manage.py test`) | Django 5.2.16 / Python 3.11.9 | 15 test modules, 178 test methods across the three apps. No pytest and no pytest-django — deliberately, the built-in runner covers every layer this plan needs |
| typecheck | mypy + django-stubs | mypy 2.3.0 / django-stubs 6.0.7 | Wired in CI; scoped by `pyproject.toml` to the three app packages |
| test data | XML fixtures under the registry app's test tree, plus in-test object creation | n/a | Collision fixtures for risk #1 do not exist yet — see Phase 2. Fan-out fixtures for risk #7 — one substance drawing two or more partner products, and two distinct products sharing a display name — do not exist either; see Phase 5 |
| query shape | `assertNumQueries` (Django built-in) | Django 5.2.16 | The chosen instrument for the one-second acknowledgement requirement — see §7 on why not wall-clock |
| clock control | injected clock seam | n/a | Already established by the freshness work; reused rather than reinvented in Phase 3 |
| HTTP boundary mocking | none yet — see Phase 3 | — | The registry download goes out over `requests`; the import path has no seam for a truncated or failed response yet |
| e2e | none yet — see Phase 4 | — | `StaticLiveServerTestCase` is Django's native host for a browser-driven test and needs no pytest migration |
| lint + format | none yet — see Phase 4 | — | No ruff, black, or equivalent anywhere in the repo (verified by grep over `pyproject.toml` and the workflow) |
| coverage measurement | none, and not planned | — | Line coverage is not the metric; the risk-to-test map from Phase 1 is (see §6.5) |
| (optional) AI-native | agent-driven test-quality audit — checked: 2026-08-29 | n/a | An agent reads an assertion and judges whether it can fail, feeding Phase 1's falsification checks. **When NOT to use:** as a substitute for actually running the falsification — an agent's opinion that a test looks strong is not evidence that it goes red |
| (rejected) AI-native | LLM-as-judge over resolved substance sets — checked: 2026-08-29 | n/a | Rejected on this product. The PRD's NFR requires substance identity to trace to the source registry row and never to be inferred; a model judging whether a resolution "looks right" supplies the oracle from a model instead of the registry. The deterministic comparison against the source row is both cheaper and the only correct one. **When NOT to use:** always, here |
| (deferred) AI-native | selective multimodal review of the household list screen — checked: 2026-08-29 | n/a | The roadmap notes S-03 is the slice most likely to be judged on feel rather than correctness, which is where a visual judgement adds signal a DOM assertion cannot. The screen now exists — S-03 shipped 2026-08-25 — but the deferral stands on a different ground than before: it shipped its semantics in text rather than in styling (verified, see §7), so a DOM assertion settles what a visual judgement would. **When NOT to use:** on any screen whose correctness a DOM assertion already settles |

**Stack grounding tools (current session):**
- Docs: Context7 via the `ctx7` CLI — confirmed that `StaticLiveServerTestCase` is Django's native browser-test host and `assertNumQueries` its native query-count assertion, both usable from the existing runner with no pytest migration; checked: 2026-08-29
- Search: Exa MCP available, not used — every tool question resolved against primary framework docs; checked: 2026-08-29
- Runtime/browser: Claude-in-Chrome MCP and Playwright MCP are both available (the previous entry recorded no Playwright MCP; that is corrected). Either is usable for one-off manual verification of a rendered screen. Neither is proposed as the automated e2e layer: both drive a live browser out of an agent session rather than a CI-reproducible one, so `StaticLiveServerTestCase` remains the Phase 4 recommendation; checked: 2026-08-29
- Provider/platform: GitHub through the `gh` CLI and Railway through its CLI, neither exposed as an MCP; checked: 2026-08-29

**Churn context (not used as likelihood evidence).** Over the 30 days to
2026-08-29 the scoped history holds 91 commits. Directory-level churn:
`households` 23, `registry` 14, `pharmacy` 11 — plus 11 more in the pharmacy
test tree and 7 in its templates — `domowa_apteka` 8, and `.github/workflows` 7;
the pharmacy list template alone was touched 4 times. `pharmacy/` is therefore a
genuine hot spot now, at roughly 32 file-touches across its subdirectories
against 1 at the previous refresh, which retires that refresh's caveat that the
newest surfaces landed as one flattened commit each and so looked untouched. One
caveat still caps what this is worth: the hardest-churning directories remain
the test trees themselves, which is weak evidence for a product failure.

## 5. Quality Gates

The full set of gates that must pass before a change reaches production.
"Required after §3 Phase N" means the gate is enforced once that rollout
phase lands; before that, the gate is planned.

| Gate | Where | Required? | Catches |
|---|---|---|---|
| dependency lock sync | CI | required (wired) | a lockfile out of step with the manifest, which fails the platform build too |
| framework system checks | CI | required (wired) | misconfiguration that would fail at boot |
| typecheck | local + CI | required (wired) | type drift across the three app packages |
| unit + integration | local + CI | required (wired) | logic regressions |
| falsification of new risk tests | local, at authoring time | recommended after §3 Phase 1 | tests that cannot fail — this project's documented failure mode |
| migration drift check | CI | required after §3 Phase 4 | a model change shipped without its migration, which breaks the deploy rather than the build |
| lint + format | local + CI | required after §3 Phase 4 | style and syntax drift; no such tool exists in the repo today |
| e2e on the critical flow | CI on pull request | required after §3 Phase 4 | a broken add-a-drug-and-see-it-on-the-shared-list path |
| deployment checks | CI | advisory by design | transport-security settings deliberately left off; kept visible, not gating |
| pre-production smoke | between merge and production | optional | environment-specific failures the suite cannot see |

## 6. Cookbook Patterns

How to add new tests in this project. Each sub-section is filled in once
the relevant rollout phase ships; before that, the sub-section reads
"TBD — see §3 Phase N."

### 6.1 Adding a unit test

- For a substance-resolution claim, assert against the **source data**, not
  against whatever the code under test currently outputs.
  `registry/tests/test_parser.py` is the canonical example: every expected
  substance set is read off `fixtures/sample-products.xml` (and documented in
  `fixtures/README.md`), never off a prior run of the parser. This is what
  makes a test able to fail when the parser regresses — an assertion derived
  from the parser's own output can never catch the parser being wrong.

### 6.2 Adding an integration test

- For a persistence claim that has an upstream "what should happen" function
  (a suggestions layer, a resolver, a computed default), derive the expected
  value from that same function, then drive the real save path and assert on
  what was actually persisted — never hardcode the id the fixture "should"
  produce. `pharmacy/tests/test_item_add.py`'s
  `test_collision_persists_default_product_and_its_own_substances` is the
  pattern: it calls `search_presentations` the same way the client does, and
  the second row of a collision-fixture built as `registry/tests/test_suggestions.py`
  pins it (`test_default_is_lowest_registry_id_when_rows_disagree_on_substances`),
  then POSTs `presentation.default_product_id` through `pharmacy:item_add` and
  asserts the persisted `Item.product_id` and its substances against
  `presentation`'s own fields — so a future change to the tiebreak rule moves
  both sides of the assertion together instead of silently drifting.

### 6.3 Adding an e2e test

- TBD — see §3 Phase 4.

### 6.4 Adding a test for a new view or endpoint

- TBD — see §3 Phase 4, for the ownership pattern: how a view that takes an
  identifier from the request is tested for the cross-household refusal, and
  how that test is falsified by removing the guard.

### 6.5 Proving a test can fail, and the risk-coverage map

- TBD — see §3 Phase 1. This entry becomes the canonical answer to two
  questions: how to record that a test was watched to go red for the right
  reason, and where the risk-to-test map lives so "what is actually tested?"
  has a written answer rather than a feeling.

### 6.6 Per-rollout-phase notes

(Filled in as phases land — two or three lines per phase capturing anything
surprising the rollout taught.)

**§3 Phase 2 (add-item-integrity)**:

- A `ModelChoiceField`-resolved FK read more than once downstream (here,
  `item.product.substance_links` read three times across `views.py` and
  `duplicates.py`) needs its `prefetch_related` at the **form's** queryset,
  not the view — `ModelForm.save()` keeps the exact prefetch-cached instance
  `ModelChoiceField.clean()` returned, so the form-level fix requires no
  view-level restructuring. `ProductCheckForm` already established this
  pattern; `ItemAddForm` now follows it too.
- The two-size query-count comparison `test_product_check.py` established
  (`ProductCheckQueryShapeTests`) generalizes beyond `product_check` — it
  proved out again for `item_add`'s substance-count axis
  (`ItemAddQueryShapeTests`), holding household size at zero across both
  measurements so substance count was the only variable moving.
- Risk #4 (a resolution failure treated as success or silently dropped)
  required **no new test**. Existing coverage — `test_duplicates.py`'s unit
  layer and `test_item_list.py`'s real-view layer — was already complete at
  the start of this phase. The derived `unresolved` property plus
  `classify()`'s empty-set guard is confirmed as the final, permanent design;
  no stored `resolution_status` field will be added — matching the precedent
  set by an earlier archived plan that explicitly rejected a stored boolean
  here on drift-risk grounds (re-import could leave it stale). See
  `context/changes/add-item-integrity/plan.md`, "What We're NOT Doing".

## 7. What We Deliberately Don't Test

Exclusions agreed during the rollout. Future contributors should respect
these unless the underlying assumption changes.

- **The Django admin** — an inspection tool for the maintainer, not a user
  surface. Re-evaluate if it is ever exposed to household members.
  (Source: Phase 2 interview Q5.)
- **Further XML parser edge cases** — the parser already carries 24 tests and
  the registry's format is stable. Re-evaluate if the registry changes its
  schema or its publication format. (Source: Phase 2 interview Q5.)
- **Template styling and layout** — a broken layout is visible and cheap to
  fix; a wrong substance is neither. Re-checked 2026-08-29 against its own
  trigger, which did not fire: S-03 shipped and did *not* start encoding
  meaning in styling. Cluster kind, unresolved state, and shared substances are
  each stated in words, and the duplicate styling is structural only — spacing,
  borders, weight — with no colour-coded semantics, so no meaning is lost to a
  DOM assertion and the existing tests already assert on that text.
  Re-evaluate if a screen ever encodes a distinction that only a rendered view
  can see.
- **Wall-clock latency for the one-second acknowledgement requirement** —
  asserted through query shape instead. This project's own lessons register
  already records the difference between query shape and measured latency.
  Re-evaluate if a query-shape assertion ever passes while the screen is slow.
- **Rate limiting and suggestion-endpoint flooding** — no such surface exists
  at household scale. Re-evaluate if the app is ever opened beyond invited
  members.
- **Pixel-level visual-regression testing for the proposed S-06 (UX audit) and
  S-07 (visual refresh) slices** — on two grounds. Appearance changes are cheap
  to eyeball, and there is no baseline worth diffing against: S-07 exists
  precisely to replace stock framework defaults, and S-06's own roadmap note
  requires the audit be produced by driving the running app at phone width,
  which is a human or agent judgement rather than a diff. The one appearance
  deviation on record — the collapsed shared-substance summary wrapping to two
  lines at 390px when three long partner names are present — was found exactly
  that way, which is the argument for the cheaper method rather than against it.
  Re-evaluate if either slice ships a screen whose correctness depends on
  layout rather than on text. (Source: Phase 2 interview Q5; challenger pass,
  2026-08-29.)
- **PRD non-goals** — barcode and photo capture, the child role, native and
  offline support, and expiration alerting are all out of scope for v1.

## 8. Freshness Ledger

- Strategy (§1–§5) last reviewed: 2026-08-29
- Stack versions last verified: 2026-08-29
- AI-native tool references last verified: 2026-08-29

Refresh (`/10x-test-plan --refresh`) when:

- a new top-3 risk surfaces from the roadmap or archive,
- a recommended tool's `checked:` date is older than three months,
- the project's tech stack changes (new framework, new test runner),
- §7 negative-space no longer matches what the team believes.
