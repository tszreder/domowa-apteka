---
date: 2026-08-29T21:15:00+02:00
researcher: Tomasz Szreder
git_commit: 49b64c86c94c7457a58eccd349911ff152d7c36f
branch: feature/test-plan-refresh-2026-08-29
repository: tszreder/domowa-apteka
topic: "Ground the test-plan.md refresh: new risk #7 (duplicate classification), §4 stack/churn, §7 negative-space, §3 sequencing"
tags: [research, codebase, test-plan, duplicates, pharmacy, churn, quality-gates]
status: complete
last_updated: 2026-08-29
last_updated_by: Tomasz Szreder
---

# Research: Grounding the 2026-08-29 test-plan refresh

**Date**: 2026-08-29T21:15:00+02:00
**Researcher**: Tomasz Szreder
**Git Commit**: `49b64c86c94c7457a58eccd349911ff152d7c36f`
**Branch**: `feature/test-plan-refresh-2026-08-29`
**Repository**: tszreder/domowa-apteka

## Research Question

Ground the four edits `change.md` proposes for `context/foundation/test-plan.md`:
new risk #7 (duplicate classification correctness), the §4 stack/churn refresh,
the §7 negative-space re-evaluation, and the §3 sequencing note — supplying the
file:line evidence the plan itself is forbidden to carry.

## Summary

All four edits are warranted, but **one premise behind risk #7 is wrong and must
be corrected before the plan is written**, and the research turned up **one live
display defect** that no committed test can catch.

1. **The review's mutation-checks were not ad hoc — two of them shipped as
   committed regression tests.** `change.md` says the S-03 review's checks were
   "ad hoc, not committed to the regression suite." Measured against the archive
   and the suite: F1 (nondeterministic partner order) and F3 (unpinned cluster
   ordering) each landed a *committed, mutation-checked* test, and the suite grew
   176 → 178 for exactly that reason. Risk #7's "Must challenge" cell cannot rest
   on that claim; the real gap is narrower and sharper (below).

2. **The genuine, verified hole is the multi-partner fan-out.** Every committed
   assertion on `DuplicateGroup.partners` expects a **single-element list**
   (6 assertions, `test_duplicates.py:208-215`). The `.extend()` accumulation
   path — one substance mapping to *two or more* partner product names — is
   asserted nowhere, at any layer. This is precisely the case `change.md` names.

3. **A real defect lives in that untested path.** Empirically measured this
   session: when two *distinct* substance-set groups carry the same product
   display name, the shared-substance line accumulates a duplicated label —
   `partners == {'Paracetamol': ['Apap', 'Apap']}` — while the summary line
   dedupes to `['Apap']`. The badge contradicts itself. Reachable in production
   because same-name/different-product rows are the registry reality that
   risk #1 already exists for.

4. **§4's numbers, churn caveat, and MCP line are all stale, in three different
   directions** — 15 modules / 178 methods (not 14/150), `pharmacy/` now a real
   hot spot (not squash-flattened), and **Playwright MCP is available in this
   session**, contradicting §4's "No Playwright MCP" line.

5. **§7's two S-03-triggered exclusions resolve differently.** "Duplicate-flagging
   correctness" is now void (S-03 is `done` → becomes risk #7). "Template styling
   and layout" **survives** — its re-evaluation trigger did not fire, because S-03
   shipped its meaning in text, not in styling. Verified against the CSS.

## Detailed Findings

### Area 1 — Risk #7: the duplicate classification surface

#### What the module actually is

`pharmacy/duplicates.py` is a pure, set-keyed module with three layers, only the
last of which knows `Item` exists:

- `substance_keys(product) -> frozenset[str]` (`duplicates.py:41-53`) — reads
  `product.substance_links.all()` (prefetch-safe), keyed on `Substance.name_key`,
  not `name`.
- `classify(a, b) -> Overlap` (`duplicates.py:56-68`) — FULL on equality, PARTIAL
  on non-empty intersection, NONE otherwise, with an **empty-set guard checked
  before the equality test** (`frozenset() == frozenset()` is `True`, so without
  it every unresolved item would full-duplicate every other).
- `build_list_view(items) -> ItemListView` (`duplicates.py:110-183`) — partitions
  resolved/unresolved, clusters by identical substance set, then cross-annotates
  partial overlaps **between groups, not between raw items**.

The module docstring (`duplicates.py:1-19`) records *why* it is set-keyed rather
than item-paired: roadmap **S-05** (`prescription-duplicate-check`) must call
`classify(substance_keys(candidate), …)` against a registry `Product` the
household does not own, with no `Item` on either side. **This gives risk #7 a
forward consumer** — a defect in `classify`/fan-out today is inherited by S-05.

#### What is already covered — and covered well

`pharmacy/tests/test_duplicates.py` (15 tests) and
`pharmacy/tests/test_item_list.py` (20 tests) between them cover:

| Behaviour | Where | Notes |
|---|---|---|
| FULL / PARTIAL / NONE, containment, crossing | `test_duplicates.py:44-80` | 7 pure `SimpleTestCase` tests |
| Both-empty is NONE, not FULL | `test_duplicates.py:77-80` | the load-bearing guard, explicitly tested |
| Repeated `(product, substance)` at different amounts collapses | `test_duplicates.py:88-99` | 89 real rows do this |
| Reads `name_key`, not `name` | `test_duplicates.py:101-118` | carries a 12-line comment on why the planned variant was unrepresentable |
| Unresolved never grouped with anything | `test_duplicates.py:141-166` | US-03's silent-grouping ban |
| same-product vs zamienniki cluster labelling | `test_duplicates.py:168-190` | |
| Combination product fans out to two **disjoint** singles | `test_duplicates.py:192-215` | one label per substance |
| Shared substances ordered alphabetically, not by set iteration | `test_duplicates.py:217-262` | links created in reverse-alphabetical order so a pass cannot come from insertion order |
| Cluster ordering: older cluster rises above newer single | `test_item_list.py:179-241` | integration; product names chosen so alphabetical ≠ `added_at`, `added_at` written via `.update()` |
| Badge emitted once per cluster, not per member | `test_item_list.py:287` | |
| N+1 guard holds with overlap items present | `test_item_list.py:112, 321, 450` | `assertNumQueries(7)` |

#### The verified gap

**Every** committed assertion on `partners` expects a one-element list:

```
test_duplicates.py:208  assertEqual(combo_group.partners.get('Paracetamol'), ['Apap'])
test_duplicates.py:209  assertEqual(combo_group.partners.get('Pseudoefedryna'), ['Sudafed'])
test_duplicates.py:210  assertEqual(para_group.partners.get('Paracetamol'), ['Combo'])
test_duplicates.py:211  assertEqual(pseudo_group.partners.get('Pseudoefedryna'), ['Combo'])
test_duplicates.py:214  assertNotIn('Sudafed', para_group.partners.get('Paracetamol', []))
test_duplicates.py:215  assertNotIn('Apap', pseudo_group.partners.get('Pseudoefedryna', []))
```

The integration test that *looks* like it covers fan-out
(`test_item_list.py:134-177`) has the combo naming two partners, but under **two
different substances** (`Paracetamol: Apap Extra`, `Pseudoefedryna: Sudafeed`) —
still one label per substance. Consequences:

- `partners[name].extend(...)` accumulating 2+ labels (`duplicates.py:167-168`)
  is **never asserted**.
- `DuplicateGroup.partner_names`' dedup loop (`duplicates.py:85-93`) — which
  feeds the user-visible `<summary>` line
  (`_partial_overlap_badge.html:3`) — has **no direct test**, and its dedup
  branch is dead in the suite, because dedup only fires when a label repeats,
  which requires the untested case.

#### Measured defect (probe run this session, then removed)

Two throwaway `TestCase` probes were run against the real builder and deleted
(`git status` clean; the 178-test suite was re-run green afterwards).

**Probe A — correct but unprotected.** Group `{para, ibu}` "Combo" against two
disjoint single-substance groups "Apap" `{para}` and "Panadol" `{para}`:

```
partners      = {'Paracetamol': ['Apap', 'Panadol']}
partner_names = ['Apap', 'Panadol']
```

Correct. No committed test asserts it.

**Probe B — a real display defect.** Same `{para, ibu}` "Combo", but the two
partner groups share a *display name* across different registry rows: "Apap"
`{para}` and "Apap" `{para, wit}`:

```
partners      = {'Paracetamol': ['Apap', 'Apap']}      <-- duplicated label
partner_names = ['Apap']                                <-- deduped
```

The rendered badge is internally inconsistent: `<summary>` reads
`Wspólna substancja: Apap` while the `<li>` beneath reads
`Paracetamol: Apap, Apap` (`_partial_overlap_badge.html:3-6`).

Cause: `_product_names` (`duplicates.py:103-109`) dedupes **within** a group;
`.extend()` (`duplicates.py:167-168`) does not dedupe **across** partner groups.

**Scope, stated precisely:** `classify` returns the correct `Overlap` in both
probes — this is a wrong *presentation* of a correct relationship, not a
misclassification. It is nonetheless inside risk #7's stated scope (the
multi-partner fan-out), it is user-visible, and no layer of the suite can catch
it. Reachability is not contrived: same-name/different-product rows are exactly
the registry condition risk #1 exists for.

### Area 2 — §4 Stack refresh

#### Test-base census (measured)

**15 test modules, 178 test methods** — confirming `change.md`'s 14→15 / ~150→~178:

| App | Modules | Methods |
|---|---|---|
| `households/tests/` | 4 | 33 (`access_control` 10, `auth` 6, `invites` 11, `models` 6) |
| `pharmacy/tests/` | 6 | 64 (`duplicates` 15, `item_add` 10, `item_delete` 6, `item_list` 20, `models` 5, `suggestions_endpoint` 8) |
| `registry/tests/` | 5 | 81 (`freshness` 12, `import_run` 7, `loader` 27, `parser` 24, `suggestions` 11) |

Full suite: `uv run manage.py test` → **Ran 178 tests … OK** (78.1s).

#### Versions (measured, not read off the manifest)

| Component | Installed | Manifest floor |
|---|---|---|
| Django | **5.2.16** | `>=5.2.16` |
| Python | **3.11.9** | `>=3.11` |
| mypy | **2.3.0** | `>=2.3.0` |
| django-stubs | **6.0.7** | `>=6.0.7` |

§4's existing version cells are all still accurate. Note §4 lists django-stubs
under mypy's "2.3.0" version cell; django-stubs is separately at 6.0.7.

#### Churn — the stale caveat is confirmed stale

30 days to 2026-08-29 over the §1 hot-spot scope: **91 commits** (was 69 to
2026-08-19). File-level:

```
7  households/views.py            4  pharmacy/tests/test_item_list.py
7  .github/workflows/deploy.yml   4  pharmacy/templates/pharmacy/item_list.html
5  templates/base.html            4  households/tests/test_invites.py
5  households/urls.py             3  pharmacy/duplicates.py
5  domowa_apteka/settings.py      3  registry/models.py
4  static/css/app.css             3  registry/management/commands/import_registry.py
```

Directory-level: `households` 23, `registry` 14, `registry/tests` 11,
`pharmacy/tests` 11, `pharmacy` 11, `households/tests` 11,
`households/templates/households` 10, `domowa_apteka` 8,
`pharmacy/templates/pharmacy` 7, `.github/workflows` 7.

`item_list.html` at 4 confirms `change.md` exactly. **`pharmacy/` is now a
genuine hot spot** (~32 file-touches across its subdirectories, from 1 at the
last refresh) — the "squash-merged, single commit" caveat no longer describes
reality and should be replaced rather than softened. The second half of the old
caveat still holds: the hardest-churning directories remain test trees.

#### Session tooling — §4's MCP line is wrong

§4 currently states "No Playwright MCP in this session; checked: 2026-08-19."
**Playwright MCP is available in this session** (`mcp__playwright__browser_*` —
navigate, click, snapshot, evaluate, network, console, tabs). Also available:
Exa MCP (`mcp__exa__web_search_advanced_exa`), Claude-in-Chrome MCP
(`mcp__claude-in-chrome__*`), Context7 via the `ctx7` CLI, and the `gh` /
Railway CLIs (neither exposed as an MCP).

**Do not read this as an e2e answer.** Playwright MCP drives a live browser from
an agent session; it is not a CI-reproducible layer, which is the same caveat §4
already applies to Claude-in-Chrome. `StaticLiveServerTestCase` remains the
Phase 4 recommendation. The honest edit is to correct the availability fact and
keep the CI-reproducibility distinction.

#### Rows that are still accurate

- **lint + format: none.** Confirmed — the `dev` dependency group is
  `django-stubs`, `jsonschema`, `mypy`, `types-requests` only; no ruff/black, and
  no lint step in `deploy.yml`.
- **HTTP boundary mocking: none.** `requests.get(...)` is called as a bare
  module-level function inside `_download`
  (`registry/management/commands/import_registry.py:205`), with no injected
  session or transport. Phase 3's seam does not exist yet. (`_reject_older_snapshot`
  at `:255` shows the older-snapshot guard for risk #2 *is* implemented.)
- **e2e: none.** No `StaticLiveServerTestCase` or browser test anywhere.
- **CI gates**: `uv sync --locked`, `manage.py check`, `mypy`, `manage.py test`,
  plus advisory `check --deploy` (`deploy.yml`). No lint, no migration-drift, no
  e2e — matching §5's "required after Phase 4" markers.

### Area 3 — §7 negative-space re-evaluation

**"Duplicate-flagging correctness" — void.** S-03 is `roadmap.md:48` status
`done`, archived at `context/archive/2026-08-24-duplicate-flagging-on-list/`.
The exclusion's own stated trigger ("Re-evaluate the moment S-03 ships") has
fired. Its rationale ("a risk row would describe an implementation rather than a
defect") no longer holds — there is now a shipped implementation with a measured
defect in it (Area 1).

**"Template styling and layout" — survives, with a sharper rationale.** Its
trigger was "if the list screen starts encoding meaning in styling, which S-03's
duplicate flags may do." It did not fire. S-03 encodes every semantic
distinction in **text**, not styling:

- cluster kind → the words `Ten sam produkt dodany wielokrotnie` vs
  `Zamienniki — ta sama substancja czynna` (`item_list.html:22-26`)
- unresolved → an `<h2>Nie udało się ustalić substancji</h2>` section
  (`item_list.html:45-46`)
- partial overlap → `Wspólna substancja: …` summary text
  (`_partial_overlap_badge.html:3`)

And `static/css/app.css:3-42` is purely structural — border, radius, padding,
margin, `font-weight: bold`, and a muted colour token. **No colour-coded
semantics**, so no meaning is lost to a DOM assertion. The existing tests already
assert on that text. The exclusion should be kept and its rationale updated from
"S-03 may change this" to "S-03 shipped and did not — meaning is in text."

**New exclusion for S-06/S-07 — supported.** Both are `proposed`
(`roadmap.md:51-52`), neither is built. S-06's own roadmap risk note
(`roadmap.md:198`) already requires the audit be produced *by driving the running
app on a phone-width viewport*, i.e. by human/agent judgement — which is an
argument for eyeballing over pixel diffing, from the roadmap itself. There is
also no baseline to diff against: S-07 exists to *replace* stock Pico defaults.

**Challenger note holds.** S-05, S-06, S-07 are all `proposed`
(`roadmap.md:50-52`); none has code, so none licenses a risk row. Worth carrying
forward that S-05 is the one to watch: `duplicates.py`'s docstring names it as
the direct consumer of `classify`.

### Area 4 — §3 sequencing

**Park condition cleared.** S-03 `done` (`roadmap.md:48`). Phases 3 and 4 are
`not started` and no longer blocked by it.

**Phase 4's separate blocker is still open — verified, not assumed.** The invite
lifetime rule remains unrecorded. `roadmap.md:127` still carries S-01 Unknown 2
verbatim: *"Do invite links expire, and can they be revoked? The PRD specifies no
pending/partial-member state but says nothing about invite lifetime."* A grep of
`prd.md` for expiry/revocation returns only FR-004 (item expiration dates, an
unrelated feature) and US-02's invite mechanism, which specifies a shareable
link/code and says nothing about lifetime. Risk #6's "Must challenge" cell —
that the rule must be stated before it can be tested — stands unchanged.

## Code References

- `pharmacy/duplicates.py:1-19` — module docstring; why set-keyed, and S-05 as forward consumer
- `pharmacy/duplicates.py:41-53` — `substance_keys`, prefetch-safe, `name_key`-keyed
- `pharmacy/duplicates.py:56-68` — `classify`, empty-set guard before equality
- `pharmacy/duplicates.py:85-93` — `partner_names` dedup loop, untested, renders into `<summary>`
- `pharmacy/duplicates.py:103-109` — `_product_names`, dedupes *within* a group only
- `pharmacy/duplicates.py:159-168` — the sorted intersection (F1's fix) and the non-deduping `.extend()` (the defect)
- `pharmacy/duplicates.py:170-183` — group assembly, `same_product`, first-appearance order
- `pharmacy/views.py:24-38` — `item_list`; prefetch + `build_list_view`, no `.order_by()` (relies on `Item.Meta.ordering`)
- `pharmacy/models.py:47-48` — `Meta.ordering = ['-added_at']`, the other half of the ordering guarantee
- `pharmacy/templates/pharmacy/_partial_overlap_badge.html:3-6` — summary uses `partner_names`, detail uses raw `partners`
- `pharmacy/templates/pharmacy/item_list.html:16-47` — cluster/unresolved structure; F4's `{% if list_view.groups %}` guard
- `static/css/app.css:3-42` — structural-only duplicate styling
- `pharmacy/tests/test_duplicates.py:208-215` — the six single-element `partners` assertions
- `pharmacy/tests/test_duplicates.py:217-262` — F1's committed regression test
- `pharmacy/tests/test_item_list.py:179-241` — F3's committed regression test
- `registry/management/commands/import_registry.py:205` — bare `requests.get`, no seam (Phase 3)
- `registry/management/commands/import_registry.py:255` — `_reject_older_snapshot` (risk #2, implemented)
- `.github/workflows/deploy.yml` — the four wired gates plus advisory `check --deploy`

## Architecture Insights

- **The set-keyed boundary is real and load-bearing.** `substance_keys` and
  `classify` never reference `Item`; only `build_list_view` does. This is what
  makes risk #7 cheap to test at the unit layer — the cheapest-layer answer is
  genuinely unit tests over `classify` and the builder, promoted to integration
  only for the ordering half.
- **The ordering guarantee is deliberately split across two owners.**
  `build_list_view` disclaims re-sorting and takes display order from its caller;
  `Item.Meta.ordering` supplies it. F3's fix correctly chose an *integration*
  test because a unit test on the builder cannot see a future `.order_by()` on
  the view's queryset. This split is worth preserving in §6.2's cookbook entry.
- **Dedup is applied inconsistently by layer.** Within-group dedup
  (`_product_names`), across-substance dedup (`partner_names`), no across-partner
  dedup (`.extend()`). The middle one masks the missing one at the summary level
  while the detail level exposes it — which is why the badge can contradict
  itself.
- **The suite's own conventions are strong.** `test_duplicates.py`'s docstring
  explicitly cites test-plan §2 risk #3's anti-pattern ("Every expected value
  here is derived from how the fixture was built, never snapshotted"). The
  test-plan is already being read and obeyed by test authors — an argument for
  keeping §2's response rows concrete.

## Historical Context (from prior changes)

- `context/archive/2026-08-24-duplicate-flagging-on-list/reviews/impl-review.md`
  — the decisive source for correcting risk #7's premise. Verdict NEEDS ATTENTION
  → APPROVED after triage; 5 findings, all fixed:
  - **F1** nondeterministic badge order → fixed *and* pinned by a committed test;
    mutation-checked under `PYTHONHASHSEED` 1–6.
  - **F2** plan/code drift on an unrepresentable test case → plan text corrected;
    correctly no new test (the substitute test already existed). This is the
    `lessons.md` "a plan can contradict itself" rule being applied.
  - **F3** unpinned cluster ordering → fixed *and* pinned by a committed
    integration test; mutation-checked against two different `.order_by()` calls.
  - **F4** stray empty `<ul>` → fixed and pinned by an `assertContains(count=1)`.
  - **F5** a `[x]` box containing its own exception → verified live at a 390px
    viewport with before/after rects. Recorded nuance: with three long partner
    names the collapsed summary wraps to 2 lines at 390px.
  - Post-triage: **178 tests (was 176; +2 from F1 and F3)** — the arithmetic that
    disproves "not committed to the regression suite."
- `context/foundation/lessons.md` — three accepted rules, two of which bear
  directly here: *verify a capability/behaviour claim empirically before writing
  it into a foundation contract*. That is why the fan-out claim in this document
  was measured rather than reasoned. The third rule (write plan resolutions back)
  is what F2 applied.
- `context/archive/2026-08-07-registry-substance-data/` — origin of risks #2/#3.
- `context/archive/2026-08-05-household-accounts-and-invites/` — origin of risks
  #5/#6, including the mutation-dead cross-household assertion.

## Related Research

- `context/archive/2026-08-24-duplicate-flagging-on-list/plan.md` — Critical
  Implementation Details, where the ordering rule and the "screen does not
  reorder unpredictably" goal are stated.
- `context/archive/2026-08-24-duplicate-flagging-on-list/plan-brief.md`
- `context/foundation/roadmap.md:50-52, 172-208` — S-05/S-06/S-07 definitions.

## Open Questions

1. **Is the duplicated partner label a defect to fix now, or only a test to
   write?** It is cosmetic and user-visible; the fix is a dedupe in the
   `.extend()` path. The test-plan refresh's own scope is documentation-only, so
   the fix belongs to the rollout phase that covers risk #7, not to this change.
   Flagging it so the plan can decide deliberately rather than by omission.
2. **Should the S-06/S-07 visual-regression exclusion name the wrap nuance?**
   F5 recorded that the collapsed summary wraps to 2 lines at 390px with long
   partner names. That is the one appearance detail with a known, measured
   deviation — arguably the exception that proves eyeballing is sufficient.
3. **Does risk #7 belong at position #7?** By impact × likelihood (High ×
   Medium) it ties risks #3/#4/#5. Position is the plan's call; the evidence
   supports High × Medium.
4. **Does the §4 stack table want a row for the fan-out fixture shape**, the way
   it already carries one for risk #1's collision fixtures ("do not exist yet —
   see Phase 2")? Symmetry suggests yes.
