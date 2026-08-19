# Test Plan

> Phased test rollout for this project. Strategy is frozen at the top
> (§1–§5); cookbook patterns at the bottom (§6) fill in as phases ship.
> Read before writing any new test.
>
> Refresh: re-run `/10x-test-plan --refresh` when stale (see §8).
>
> Last updated: 2026-08-19

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

Abuse lens applied. Risk #5 is the authorization/ownership case (IDOR) and
risk #6 the lifetime of a credential-equivalent artifact. Resource abuse
(flooding the suggestion endpoint) and secret leakage were both considered
and deliberately excluded — at household scale there is no rate-limiting
surface worth a rollout phase, and no third-party credential sits in the
request path. See §7 rather than a padded risk map.

Likelihood is not argued from churn anywhere in this table. The Phase 2
interview answered "uniform" to the question of where change feels least
confident, and the two newest surfaces landed through a squash-merge, so
churn counts understate them. Churn is recorded in §4 as context only.

### Risk Response Guidance

| Risk | What would prove protection | Must challenge | Context `/10x-research` must ground | Likely cheapest layer | Anti-pattern to avoid |
|---|---|---|---|---|---|
| #1 | Given two registry entries that share a name but differ in strength, form, or manufacturer, the user is shown enough to tell them apart, and the item that gets saved is the one that was chosen — not the first match | "The name matched, therefore the right product was selected." A correct substance resolution for the *wrong product* is indistinguishable from success at every layer below the UI | What the suggestion payload carries, what the save path persists out of it, and whether product identity travels as a stable registry key or is re-derived from the typed string | Integration over the suggestion and save path, driven by fixture rows deliberately built as name collisions | A fixture set with one product per name — it makes the risk unrepresentable, and the test then passes by construction |
| #2 | A truncated, malformed, or older-than-current snapshot is refused, the previous good data survives intact, and the freshness signal does not advance; a stale state is visible to the app as stale rather than indistinguishable from fresh | "The scheduled run completed, therefore the data is current." And its sibling: "the import raised nothing, therefore it succeeded" | Which exception types the import boundary actually catches, where the freshness record is written relative to the import transaction, and what the app reports when the last success is old | Integration over the import command with truncated, malformed, and older-snapshot fixture variants; freshness assertions driven by an injected clock | Asserting the happy path over a broad `except` that swallows; and testing the scheduler's configuration instead of the app-side signal |
| #3 | For a product whose source row is known, the resolved substance set equals what that source row states — including the multi-substance case — and placeholder values never become substances | "Whatever the parser returns is correct." The oracle comes from the source registry row, never from what the parser currently produces | Which source field is authoritative, how a multi-substance row is represented, and which values are placeholders rather than substance identities | Unit tests over parse and resolve, with fixture rows whose expected sets are read off the source data | Snapshotting current parser output as the expectation — that certifies today's bugs and can never fail for the right reason |
| #4 | A product that cannot be resolved produces a visible, specific failure state for the user, and the item is persisted in a state that keeps it out of any duplicate relationship | "An empty result means the product has no substances." An unresolved item and a genuinely substance-free item must not be the same stored state | What the save path does when resolution misses, and how an unresolved item is represented so later duplicate logic cannot group it | Integration over the add flow with an input that cannot resolve | Asserting an HTTP 200 and nothing about what the user actually sees or what was persisted |
| #5 | A member of household A issuing a well-formed request for a household B resource is refused — and the test goes red when the ownership check is deleted | "The user is logged in, therefore the object is theirs." Ownership is a per-object check, not a session check | Which views take an identifier from the request, and whether the queryset is scoped by membership or filtered after the fetch | Integration per identifier-taking view, each one falsified | Repeating the pattern already found in this suite — asserting a status code without proving which branch produced it |
| #6 | An invite artifact stops working once the condition the product intends has occurred, and presenting a spent or revoked one refuses cleanly rather than erroring or silently re-joining | "One person joined, therefore the link is done." The product has not decided expiry or revocation, so the rule must be stated before it can be tested | The intended lifetime rule — a product decision, currently unrecorded — and every path that consumes a token, including login and signup, not only join | Integration over the token paths, once the rule is stated | Testing whatever the code happens to do today and calling it the requirement; that test has no oracle |

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

**Sequencing decision (2026-08-19).** Phases 1 and 2 run now. Phases 3 and 4
are deliberately parked until roadmap slice S-03 (`duplicate-flagging-on-list`)
ships. S-03 is a must-have (FR-003, US-03), is not built, and the PRD's hard
deadline is 2026-09-14 under after-hours-only capacity — so the rollout yields
the remaining evenings to the product's payoff after phase 2. Phases 3 and 4
keep their rows and stay `not started`; re-run `/10x-test-plan` to resume them.

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
| unit + integration | Django test runner (`manage.py test`) | Django 5.2.16 / Python 3.11.9 | 14 test modules, 150 test methods across the three apps. No pytest and no pytest-django — deliberately, the built-in runner covers every layer this plan needs |
| typecheck | mypy + django-stubs | 2.3.0 | Wired in CI; scoped by `pyproject.toml` to the three app packages |
| test data | XML fixtures under the registry app's test tree, plus in-test object creation | n/a | Collision fixtures for risk #1 do not exist yet — see Phase 2 |
| query shape | `assertNumQueries` (Django built-in) | Django 5.2.16 | The chosen instrument for the one-second acknowledgement requirement — see §7 on why not wall-clock |
| clock control | injected clock seam | n/a | Already established by the freshness work; reused rather than reinvented in Phase 3 |
| HTTP boundary mocking | none yet — see Phase 3 | — | The registry download goes out over `requests`; the import path has no seam for a truncated or failed response yet |
| e2e | none yet — see Phase 4 | — | `StaticLiveServerTestCase` is Django's native host for a browser-driven test and needs no pytest migration |
| lint + format | none yet — see Phase 4 | — | No ruff, black, or equivalent anywhere in the repo (verified by grep over `pyproject.toml` and the workflow) |
| coverage measurement | none, and not planned | — | Line coverage is not the metric; the risk-to-test map from Phase 1 is (see §6.5) |
| (optional) AI-native | agent-driven test-quality audit — checked: 2026-08-19 | n/a | An agent reads an assertion and judges whether it can fail, feeding Phase 1's falsification checks. **When NOT to use:** as a substitute for actually running the falsification — an agent's opinion that a test looks strong is not evidence that it goes red |
| (rejected) AI-native | LLM-as-judge over resolved substance sets — checked: 2026-08-19 | n/a | Rejected on this product. The PRD's NFR requires substance identity to trace to the source registry row and never to be inferred; a model judging whether a resolution "looks right" supplies the oracle from a model instead of the registry. The deterministic comparison against the source row is both cheaper and the only correct one. **When NOT to use:** always, here |
| (deferred) AI-native | selective multimodal review of the household list screen — checked: 2026-08-19 | n/a | The roadmap notes S-03 is the slice most likely to be judged on feel rather than correctness, which is where a visual judgement adds signal a DOM assertion cannot. Deferred because the screen does not exist yet. **When NOT to use:** on any screen whose correctness a DOM assertion already settles |

**Stack grounding tools (current session):**
- Docs: Context7 via the `ctx7` CLI — confirmed that `StaticLiveServerTestCase` is Django's native browser-test host and `assertNumQueries` its native query-count assertion, both usable from the existing runner with no pytest migration; checked: 2026-08-19
- Search: Exa MCP available, not used — every tool question resolved against primary framework docs; checked: 2026-08-19
- Runtime/browser: Claude-in-Chrome MCP available. Usable for one-off manual verification of a rendered screen; not proposed as the automated e2e layer, since it drives a real browser session rather than a CI-reproducible one; checked: 2026-08-19
- Provider/platform: GitHub through the `gh` CLI and Railway through its CLI, neither exposed as an MCP. No Playwright MCP in this session; checked: 2026-08-19

**Churn context (not used as likelihood evidence).** Over the 30 days to
2026-08-19 the scoped history holds 69 commits. Source-directory churn:
`households/views.py` 7, `registry/management/` 6, `domowa_apteka/settings.py` 6,
`households/urls.py` 5, `registry/models.py` 3, `registry/migrations/` 3. Two
caveats cap what this is worth: the newest surfaces (the pharmacy app and the
suggestion module) show a single commit each because their pull request was
squash-merged, so churn understates the least-exercised code in the product;
and the hardest-churning directories are the test trees themselves, which is
weak evidence for a product failure.

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

- TBD — see §3 Phase 2, for the pattern that asserts a resolved substance
  set against its source registry row rather than against parser output.

### 6.2 Adding an integration test

- TBD — see §3 Phase 2, for the pattern that drives the suggestion and save
  path with name-collision fixtures and asserts which product was persisted.

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
  fix; a wrong substance is neither. Re-evaluate if the list screen starts
  encoding meaning in styling, which S-03's duplicate flags may do.
- **Wall-clock latency for the one-second acknowledgement requirement** —
  asserted through query shape instead. This project's own lessons register
  already records the difference between query shape and measured latency.
  Re-evaluate if a query-shape assertion ever passes while the screen is slow.
- **Rate limiting and suggestion-endpoint flooding** — no such surface exists
  at household scale. Re-evaluate if the app is ever opened beyond invited
  members.
- **Duplicate-flagging correctness** — S-03 is not built, so a risk row for it
  would describe an implementation rather than a defect. Phase 2 protects the
  substance-set inputs that S-03 will compare. Re-evaluate the moment S-03
  ships. (Source: challenger pass, 2026-08-19.)
- **PRD non-goals** — barcode and photo capture, the child role, native and
  offline support, and expiration alerting are all out of scope for v1.

## 8. Freshness Ledger

- Strategy (§1–§5) last reviewed: 2026-08-19
- Stack versions last verified: 2026-08-19
- AI-native tool references last verified: 2026-08-19

Refresh (`/10x-test-plan --refresh`) when:

- a new top-3 risk surfaces from the roadmap or archive,
- a recommended tool's `checked:` date is older than three months,
- the project's tech stack changes (new framework, new test runner),
- §7 negative-space no longer matches what the team believes.
