---
date: 2026-09-05T18:35:05+02:00
researcher: Tomasz Szreder
git_commit: ffa7f2f4a12ce99664a8ff7dbc1cde3307f0d879
branch: feature/testing-coverage-truth-pass
repository: domowa-apteka
topic: "Coverage truth pass: can the assertions claiming to protect risks #1-#6 actually fail?"
tags: [research, codebase, testing, falsification, mutation-checking, risk-coverage]
status: complete
last_updated: 2026-09-05
last_updated_by: Tomasz Szreder
---

# Research: Coverage truth pass for risks #1–#6

**Date**: 2026-09-05T18:35:05+02:00
**Researcher**: Tomasz Szreder
**Git Commit**: `ffa7f2f4a12ce99664a8ff7dbc1cde3307f0d879`
**Branch**: `feature/testing-coverage-truth-pass`
**Repository**: domowa-apteka

## Research Question

Phase 1 of the §3 rollout in `context/foundation/test-plan.md`: produce the
grounding for a written risk-to-test map, and establish which assertions
claiming to protect risks #1–#6 can actually fail. Bounded to those
assertions; ceiling of roughly twelve falsification checks; risk #7 is
Phase 5 and out of scope beyond a stub.

## Summary

Seven falsification checks were run against live code (all mutations
reverted; tree verified clean). Four results matter:

1. **The three historical "tests that could not fail" were all repaired
   already**, and all three repairs still hold — each was re-mutated during
   this research and each went red. The plan's §1 principle #4 is
   historically accurate but describes *caught* defects, not standing ones.
   Phase 1 should not spend its budget re-proving them.

2. **Risk #1 has no falsifiable coverage at the save layer.** Making
   `item_add` discard the user's chosen product and save a different one
   instead leaves **all 228 tests green**. This is the single most important
   finding in this document, and it is exactly the anti-pattern the plan
   predicted for risk #1 ("a fixture set with one product per name ... the
   test then passes by construction").

3. **Risk #5 is genuinely covered — but not where the risk map implies.**
   `households/tests/test_access_control.py` reads like the cross-household
   guardian; the assertions that actually go red on an item leak live in
   `pharmacy/tests/test_item_list.py` and `test_product_check.py`. The
   access-control file catches *misresolution*, never *leakage*.

4. **A previously unrecorded structural fact drives several of these**:
   `_household_of` is duplicated verbatim in two apps
   (`households/views.py:21` and `pharmacy/views.py:20`). Mutating one does
   not exercise the other. This was raised as F5 in the 2026-08-14 review
   and consciously skipped; it now has a testing consequence.

Two further gaps were measured: one parser rule is unobserved by all 51
registry tests, and the risk #6 login path has no test at all (by an
accepted, documented review decision).

There is no falsification-recording artifact anywhere in the repo. The only
precedent is ad-hoc `Mutation-checked:` prose inside `impl-review.md`
Decision lines. **Phase 1 must invent the ledger format** — that is a real
deliverable, not a formality.

## Measured Baseline (this worktree, commit `ffa7f2f`)

| Measurement | Value |
|---|---|
| Full suite | **228 tests, OK, 88.8 s** |
| Test modules | **17** across three apps |
| `uv run mypy` | Success, **63 source files**, 6.3 s |
| Single module run | ~11 s (`households.tests.test_access_control`, 10 tests) |
| Small module run | ~2.3 s (`households.tests.test_models`, 6 tests) |

**The plan's §4 stack table is stale**: it records "15 test modules, 178 test
methods". Actual is 17 modules / 228 methods. The 50-test delta is entirely
S-05 `prescription-duplicate-check` (risk #7 territory), landed 2026-08-30
through 2026-09-05.

**Cost note for planning**: a falsification cycle costs ~11 s if it runs the
target module and ~89 s if it runs the full suite. Twelve checks is ~2 min of
test time targeted, ~18 min untargeted. Run the target module for the red
result; reserve a full-suite run for the cases where the question is
"does *anything* catch this?".

## The Falsification Ledger (measured, not inferred)

Every row below was executed against live code on this worktree. Each
mutation was reverted immediately; `git status --porcelain` is clean and no
`MUTATION` marker remains.

| # | Risk | Mutation applied | Target | Result | Verdict |
|---|---|---|---|---|---|
| R1 | #6 | `households/views.py:43` `session.pop(...)` → `session.get(...)` | `households.tests.test_invites` | **RED** — 1 failure, `test_session_key_cleared_after_signup...` line 48 | Repair holds |
| R2 | #5 | `households/views.py:29` `return membership.household` → `Household.objects.first()` | `households.tests.test_access_control` | **RED** — 1 failure, line 22, `Kowalscy != Nowakowie` | Repair holds |
| R3 | #3 | `registry/parser.py:189` `enumerate(kept)` → `enumerate(rows)` | `registry.tests.test_parser` | **RED** — **4 failures** | Repair holds firmly |
| N1 | #5 | `pharmacy/views.py:23` `return membership.household` → `Household.objects.first()` | `households.tests.test_access_control` | **RED** — 1 failure, line 31 | Catches misresolution |
| N1b | #5 | `pharmacy/views.py:30` + `:137` `Item.objects.filter(household=household)` → `Item.objects.all()` | `households.tests.test_access_control` | **GREEN — 10/10 OK** | **Cannot see a live leak** |
| N1b′ | #5 | same mutation | `pharmacy.tests.test_item_list`, `test_product_check` | **RED** — 1 failure each | Real guard lives here |
| N2 | #1 | `pharmacy/views.py:71` force `item.product = Product.objects.filter(is_active=True).order_by('registry_id').first()` | **full suite** | **GREEN — 228/228 OK** | **No coverage at all** |
| N3 | #3 | `registry/parser.py:289` `name = vocabulary.get(name_key)` → `product.common_name.strip()` | `registry.tests.test_parser` + `test_loader` (51 tests) | **GREEN — 51/51 OK** | Rule unobserved |

### What R1–R3 establish

The three defects named in the plan's §1 principle #4 were all found by human
review and fixed, each with a mutation check recorded at fix time:

- **(a) Setup guaranteed its own assertion** — F2 in
  `context/archive/2026-08-05-household-accounts-and-invites/reviews/impl-review.md`.
  The old test logged out before asserting, and logout flushes the session,
  so the assertion held regardless of whether the view used `pop` or `get`.
  Fixed by adding `assertNotIn(INVITE_TOKEN_SESSION_KEY, self.client.session)`
  *before* the logout (`households/tests/test_invites.py:48`). **Re-verified
  red here (R1).**
- **(b) Mutation-dead cross-household check** — F3, same file. `setUp`
  created `household_a` first and the test logged in `member_a`, so a
  global-resolve bug returned the expected value by coincidence. Fixed by
  logging in `member_b` and asserting `household_b`
  (`households/tests/test_access_control.py:17-24`). **Re-verified red here
  (R2).**
- **(c) Two parser rules no test observed** — F5 in
  `context/archive/2026-08-07-registry-substance-data/reviews/impl-review-phases-2-4.md`.
  Fixed by adding `DroppedRowNumberingTests`
  (`registry/tests/test_parser.py:177`) and the blank-name test at
  `test_parser.py:225`. **Re-verified red here (R3), with 4 failures where
  the original defect produced 0.**

**Planning consequence**: do not budget falsification checks against these
three. They are the *control group* — they prove the technique works and that
the repairs have not regressed. One cheap re-run of R1–R3 belongs in the
phase as a regression guard, not as discovery.

## Detailed Findings by Risk

### Risk #1 — wrong product identity saved (the top finding)

**Identity travels correctly in the code.** The path is a stable registry
primary key end to end, with no re-derivation from the typed string
anywhere:

- `registry/suggestions.py:107-111` — presentations are grouped by
  `(name, strength, pharmaceutical_form)`, so strength/form collisions split
  into separate suggestions; a same-name/strength/form product from a
  different manufacturer collapses into one presentation carrying a
  `producers` list.
- `pharmacy/views.py:48-58` — the JSON payload carries `name`, `strength`,
  `form`, `substances`, `default_product_id`, and
  `producers: [{holder, product_id}]`.
- `pharmacy/static/pharmacy/js/autocomplete.js:65` — picking a presentation
  writes `presentation.default_product_id` into the hidden field; picking a
  specific producer overwrites it with `producer.product_id` (line 45).
- `pharmacy/forms.py:12-18` — `ItemAddForm.product` is a
  `ModelChoiceField(queryset=Product.objects.filter(is_active=True))`
  rendered as `HiddenInput`; Django resolves it by **primary-key lookup**.
- `pharmacy/models.py:29-33` — `Item.product` is a real
  `ForeignKey(Product, on_delete=PROTECT)`. Display fields are read live
  through the FK (`pharmacy/templates/pharmacy/_item_row.html:63-67`), never
  denormalised.

**But nothing tests it.** Every method in `pharmacy/tests/test_item_add.py`
creates exactly **one** `Product` and posts its id. No test asserts that the
saved `Item.product_id` equals the specific id posted *while a second,
different product also exists*. Measured (N2): forcing the view to ignore the
POSTed product entirely and save the lowest-`registry_id` active product
instead leaves **all 228 tests green**.

The collision fixtures that would make this representable exist one layer
down and are never driven through the save path:

- `registry/tests/test_suggestions.py:40` — rows sharing name/strength/form
  collapse to one presentation with N producers (the `Concor Cor 2,5` shape)
- `registry/tests/test_suggestions.py:99` — same name, different strengths
  are separate presentations (the Xanax shape)
- `registry/tests/test_suggestions.py:80` — the producer representative row
  asserts both `assertEqual(..., with_links.id)` **and**
  `assertNotEqual(..., without_links.id)` — a genuine two-candidate
  falsification, and the model to copy

**Residual product risk worth stating** (mechanism, not defect): when a
presentation has a single holder the producer picker auto-confirms
(`autocomplete.js:75-81`), and the row chosen among registry-id ties is
decided by `_default_product` (`registry/suggestions.py:35-47`,
lowest `registry_id` among rows tied on substance-link presence). The user
cannot see or override that tiebreak. `registry/tests/test_suggestions.py:151`
is honest that this proves determinism, not medical correctness.

### Risk #4 — a swallowed lookup failure

**Structurally prevented, with one untested branch.** A typed name matching
no registry product cannot become a saved `Item`: `ItemAddForm.product` is a
required `ModelChoiceField` (`pharmacy/forms.py:12-18`), so an empty or
non-numeric hidden field fails validation and `item_add`
(`pharmacy/views.py:65-91`) re-renders the bound form without ever calling
`Item.save()`. The "saved as though it resolved" mode is closed by the schema
and form contract, not by convention.

`Item.unresolved` (`pharmacy/models.py:53-60`) is a **computed property**,
not a stored column: `return not self.product.substance_links.all()` — note
the deliberate non-`.exists()` spelling the 2026-08-14 review flagged twice.
`pharmacy/duplicates.py:130-136` partitions on the same live signal, so
unresolved items never enter `members_by_key`/`groups`. Confirmed excluded
from grouping and covered in both `test_duplicates.py` and `test_item_list.py`.

**Gap**: no test in `test_item_add.py` posts *without* a `product` value. That
branch falls back to Django's untranslated default `"This field is required."`
— an English string in an otherwise-Polish UI — on the exact boundary risk #4
names. `error_messages` at `pharmacy/forms.py:15-17` overrides only
`invalid_choice`, not `required`.

**Open product question, still unresolved**: roadmap S-02 Unknown 2 asks
whether a failed lookup saves an unresolved item or rejects the save. The
implementation answered "reject" (form invalid). The roadmap still records it
as open, owner: user.

### Risk #3 — wrong active-substance set

`registry/parser.py` implements ~18 distinct rules. Most are observed. Two
are not, and one test overclaims in its name:

- **Unobserved (measured, N3)**: `parser.py:289` — a fallback link's display
  name comes from the vocabulary's *first-seen* spelling
  (`vocabulary.get(name_key)`), never from the product's own
  `nazwaPowszechnieStosowana`. Every fallback case in the suite has the two
  spellings byte-identical, so swapping the source leaves 51 registry tests
  green. Making this observable needs a fixture where a product's own
  common-name casing differs from the vocabulary's stored spelling for the
  same `name_key`.
- **Unobserved but functionally inert**: `parser.py:164-171` — vocabulary
  accumulation deliberately does *not* apply the denylist
  (`registry/denylist.py:11-14` documents this). It changes nothing
  observable, because `_resolve_deferred` blocks on
  `name_key in DENYLISTED_SUBSTANCE_KEYS` at `parser.py:287` *before*
  reading the vocabulary. Worth recording as a deliberate no-op, not worth a
  falsification check.
- **Name overclaims scope**:
  `test_denylisted_names_never_reach_the_substance_vocabulary`
  (`registry/tests/test_parser.py:251-254`) checks the post-filter
  `result.substances`, never the internal `vocabulary` dict its name
  describes.
- **Tautological line**: `registry/tests/test_parser.py:249` asserts
  `'produkt złożony' in DENYLISTED_SUBSTANCE_KEYS` — a static module
  constant, proving no parser behaviour.
- **One-directional**: `parser.py:326-330`, the
  `ulotka or ulotkaImportRownolegly` fallback. Only the fallback branch is
  exercised; no fixture carries both attributes, so deleting the primary half
  fails nothing.

**Oracle health is good.** No pure "snapshot today's output" test was found.
`test_counts_match_the_documented_fixture` (`test_parser.py:50-56`) looks like
one but its expected numbers are hand-derived in
`registry/tests/fixtures/README.md` from a real export excerpt.

### Risk #2 — stale or bad registry data served as current

Better covered than the risk map's wording suggests. Specifically:

- **No swallowing `except`.** The one broad `except Exception`
  (`import_registry.py:117-123`) logs to the `ImportRun` row and **re-raises**;
  `registry/tests/test_import_run.py:108-121` tests exactly that.
- **Freshness record sits outside the transaction** — created at
  `import_registry.py:110-113` before any work, terminal status written at
  `:118-135`, both outside `_import`'s `transaction.atomic()`
  (`:238`) and `load_parse_result`'s own (`loader.py:89`).
  `test_import_run.py:61-78` names this "the single most likely defect" and
  tests it by forcing the guard to fire mid-transaction.
- **Older-snapshot rewind** is guarded by `_reject_older_snapshot`
  (`import_registry.py:255-275`), checked before any write, and covered by
  `SnapshotOrderTests` (`test_loader.py:310-343`) including `--allow-older`
  and the same-date edge.
- **Truncation** is caught by re-raising `ET.ParseError` as
  `RegistryParseError` (`parser.py:219-231`), tested with a byte-sliced
  fixture at `test_loader.py:432-443`.
- **Load-bearing ordering worth knowing**: `_download` catches
  `requests.RequestException` before `OSError`
  (`import_registry.py:211-221`). Because `RequestException` subclasses
  `OSError`, reversing those two clauses routes network errors into the
  non-retried disk branch. Both branches are separately covered
  (`test_loader.py:368-392`, `394-404`).
- **Seams**: `_sleep = time.sleep` (`import_registry.py:51`) is a deliberate,
  documented seam. The clock is *not* injectable — `timezone.now()` is called
  directly and tests patch the module attribute
  (`test_freshness.py:86`). HTTP is mocked by patching
  `...import_registry.requests.get`. The plan's §4 claim of an "injected clock
  seam ... already established" overstates it: it is monkeypatching, which
  works but is not a seam.
- **Weakest point**: `PlausibilityGuardTests` (`test_loader.py:271-294`)
  proves the `MIN_EXPECTED_PRODUCTS` rollback mechanism only by artificially
  lowering `--min-products` against the full 14-product fixture — never
  against a genuinely short but well-formed file.

### Risk #5 — cross-household read

**The IDOR surface is much smaller than the risk map assumes.** `registry/`
has no views at all. Of every identifier-taking endpoint, exactly one takes a
foreign key into *household-owned* data:

- `pharmacy.views.item_delete` (`pharmacy/views.py:100`) —
  `get_object_or_404(Item, pk=pk, household=household)`, scope-before-fetch
  in a single query, so a foreign `pk` 404s without confirming the row
  exists. Correct, and genuinely tested (`test_item_delete.py:79-87`).
- `households.views.household_detail` / `regenerate_invite` /
  `household_create` accept **no identifier at all** — they resolve from
  `request.user.membership`. There is no ownership check to delete, so this
  endpoint structurally cannot host an IDOR.
- `households.views.join` (`views.py:68`) is capability-based by design: the
  token *is* the credential. The `membership.household_id == household.id`
  compare at `views.py:90` is **not** a gate — both branches render the same
  `join_refused.html`; it only selects copy.
- `pharmacy.views.item_add` / `product_check` / `product_suggestions` take
  `Product` ids, which are global reference data, correctly unscoped. The
  comparison sets are scoped (`views.py:137`).

**The structural guard is the schema**: `Membership.user` is a
`OneToOneField` (`households/models.py:40-44`), DB-enforced UNIQUE, so "own
household" is unambiguous and every view derives it from the user.
`households/tests/test_models.py:47` is the backbone test for that.

**Where the assertions actually are.** Measured (N1b): with a live
cross-household leak in both `item_list` and `product_check`,
`households/tests/test_access_control.py` stays **10/10 green**. Its
`assertNotContains(response, household_a.name)` cannot see item leakage —
no `Item` is ever created for `household_a` in that `setUp`
(`test_access_control.py:9-15`), and the template only ever echoes the
current household's name. The tests that go red are
`pharmacy/tests/test_item_list.py::test_item_in_household_a_never_appears_for_member_of_household_b`
and one in `test_product_check.py`.

So risk #5 **is** covered — the map just points at the wrong file. The
access-control file's contribution is proving *misresolution* (N1), which is
a different and also-real guarantee.

**The duplication that makes this subtle**: `_household_of` exists twice,
verbatim — `households/views.py:21` (serving 2 views) and
`pharmacy/views.py:20` (serving 4 views, i.e. the entire medical-data
surface). Raised as F5 in
`context/archive/2026-08-14-add-drug-with-substance-resolution/reviews/impl-review.md`
and consciously **skipped**. Consequence for this phase: a falsification of
one copy says nothing about the other, and any risk-to-test map must name
which copy an assertion covers.

### Risk #6 — invite artifact outliving its purpose

**The product rule is genuinely undecided**, which the plan already flags as
blocking Phase 4. Roadmap S-01 Unknown 2: "Do invite links expire, and can
they be revoked? ... — Owner: user. Block: no." Still unrecorded.

What the code does today:

- `Household.invite_token` (`households/models.py:12`) —
  `secrets.token_urlsafe(32)` on save (`:22-23`), regenerable via
  `regenerate_invite_token()` (`:31-33`).
- `INVITE_TOKEN_SESSION_KEY` is touched in exactly two places: stashed at
  `households/views.py:71` (join, anonymous branch) and popped at
  `views.py:43` (signup). The pop consumes the **session** key, not the
  household's token — the link stays valid for anyone else holding it.
- **The login path never reads it.** `households/urls.py:12-19` uses stock
  `LoginView` with only `template_name`/`authentication_form` overridden, and
  `EmailAuthenticationForm` (`households/forms.py:36-43`) has no `form_valid`.
  Django's `cycle_key()` preserves session data across login, so a token
  stashed by an anonymous invite click survives a direct `/login/` unconsumed
  and unacted-on — the user never joins.
- The only thing that reduces a token's standing validity is the
  owner-triggered `regenerate_invite` (`views.py:112-118`), covered by
  `test_invites.py:133`.

**No test covers the login path.** This was explicitly triaged and
**accepted/SKIPPED** in the 2026-08-05 review on the grounds that the affected
population is narrow and an escape hatch exists (re-click the link after
login). Phase 1 should record it in the map as *knowingly uncovered*, not
discover it as a defect.

### Risk #7 — stub only (Phase 5)

Duplicate grouping is touched by three modules:
`pharmacy/tests/test_duplicates.py` (~27 methods, unit-level, most thorough),
`pharmacy/tests/test_item_list.py` (~12 of its 20 methods, through HTTP), and
`pharmacy/tests/test_product_check.py` (26 methods, exercising
`check_candidate` through the check screen). Not audited per scope. Note for
Phase 5: all 50 tests added since the 178-test baseline are here, and the
2026-09-05 review of S-05 already mutation-checked several of them.

## Test-Quality Patterns Found (for §6.5 of the cookbook)

**Reference-quality examples already in the repo** — these are what the
cookbook should point at:

- `pharmacy/tests/test_product_check.py:340`
  `test_uncomparable_count_is_not_wired_into_an_active_template_tag` reads the
  raw template source and strips `{% comment %}` blocks before asserting
  absence, specifically to avoid the false negative a rendered-HTML
  `assertNotContains` would give. This is the antidote to the F2 finding in
  the 2026-09-05 review, where `assertNotContains(response, UNCOMPARABLE)`
  passed unconditionally because the string appears nowhere in the codebase.
- `registry/tests/test_suggestions.py:80` asserts both `assertEqual(...)` and
  `assertNotEqual(...)` against two candidates — the two-candidate shape that
  makes an identity claim falsifiable.
- `pharmacy/tests/test_item_add.py:125`
  `test_posting_producer_confirmed_false_stores_false` documents in a comment
  that it passes only because `BooleanField.to_python` special-cases
  `'false'`/`'0'` — an untested framework dependency made explicit.
- Twin-paired assertions throughout `test_product_check.py` (e.g. L271-274,
  L289-291): assert the expected state *and* the absence of each adjacent
  state.

**Anti-patterns found in this suite** (the catalogue Phase 1 should write up):

1. *Single-object fixture* — one row exists, so "the right one was chosen"
   passes by construction (`test_item_add.py`, whole file).
2. *Assertion whose subject was never created* — `assertNotContains` for an
   object that no `setUp` ever built (`test_access_control.py:32`).
3. *Assertion on a module constant* — proves the constant, not the behaviour
   (`test_parser.py:249`).
4. *Name overclaims scope* — the test name describes an internal structure the
   assertion never reaches (`test_parser.py:251-254`).
5. *One-directional OR* — only the fallback branch of `a or b` is fixtured
   (`parser.py:326-330`).

## Code References

- `pharmacy/views.py:20` — the `pharmacy` copy of `_household_of`, guarding four views
- `households/views.py:21` — the `households` copy, guarding two views
- `pharmacy/views.py:30`, `:137` — household-scoped querysets for list and check
- `pharmacy/views.py:100` — `get_object_or_404(Item, pk=pk, household=household)`, the one real IDOR guard
- `pharmacy/views.py:70-73` — save path; `form.save(commit=False)` then household/added_by stamping
- `pharmacy/forms.py:12-18` — `ItemAddForm.product` as hidden `ModelChoiceField`; `required` message not overridden
- `pharmacy/models.py:53-60` — `Item.unresolved` computed property, deliberate non-`.exists()` spelling
- `pharmacy/duplicates.py:130-136` — unresolved items partitioned out of grouping
- `registry/suggestions.py:35-47` — `_default_product` tiebreak
- `registry/suggestions.py:107-111` — presentation grouping key
- `registry/parser.py:174` — denylist filter on explicit rows
- `registry/parser.py:189` — `enumerate(kept)`, the repaired numbering rule
- `registry/parser.py:287-289` — denylist re-check and the unobserved spelling source
- `registry/parser.py:219-231` — `ET.ParseError` → `RegistryParseError`
- `registry/management/commands/import_registry.py:51` — the `_sleep` seam
- `registry/management/commands/import_registry.py:110-135` — ImportRun written outside the transaction
- `registry/management/commands/import_registry.py:211-221` — ordering-sensitive except clauses
- `registry/management/commands/import_registry.py:255-275` — `_reject_older_snapshot`
- `households/models.py:40-44` — `Membership.user` OneToOneField, the structural guard
- `households/views.py:43`, `:71` — the only two touches of the invite session key
- `households/decorators.py:10-26` — `household_required`; guards household-less, never cross-household

## Architecture Insights

- **The app's real access-control guarantee is schema-shaped, not
  check-shaped.** Because `Membership.user` is one-to-one and almost no view
  accepts a household identifier, there is very little ownership-checking
  code to delete — which is why risk #5's "falsify by deleting the guard"
  framing only applies at `item_delete` and at the two queryset filters.
- **Identity is correct by construction in the code and unproven in the
  tests.** Risk #1 is the mirror image of risk #5: the code is stronger than
  the risk map fears, and the tests are far weaker than the green suite
  suggests.
- **The loader is deliberately dumb** (`loader.py:1-6`): a product's substance
  set is exactly the parser's `ProductRecord.links`, with no independent
  re-derivation. So risk #3's oracle must come from the source XML row, and
  the parser is the only place it can be enforced.
- **`last_seen_as_of` uniqueness per import is an unguarded assumption**
  (`loader.py:23-26`) that the whole idempotency/withdrawal design rests on.

## Historical Context (from prior changes)

- `context/archive/2026-08-05-household-accounts-and-invites/reviews/impl-review.md`
  — F2 (self-guaranteeing setup) and F3 (mutation-dead cross-household), both
  fixed and mutation-verified; also the accepted SKIP of the login-path invite gap.
- `context/archive/2026-08-07-registry-substance-data/reviews/impl-review-phases-2-4.md`
  — F5, the two unobserved parser rules, fixed via `DroppedRowNumberingTests`.
- `context/archive/2026-08-14-add-drug-with-substance-resolution/reviews/impl-review.md`
  — F3 (the `producer_confirmed` wire value), F5 (`_household_of` duplication,
  **skipped**), and a recorded mutation check on `_default_product`.
- `context/archive/2026-08-24-duplicate-flagging-on-list/reviews/impl-review.md`
  — the 176 → 178 growth the plan cites; **verified accurate**, F1 and F3 each
  added a mutation-checked regression test.
- `context/archive/2026-08-29-prescription-duplicate-check/reviews/impl-review.md`
  — dated 2026-09-05, the newest review; F2 is a textbook vacuous
  `assertNotContains`, F4 an untested documented ordering. One finding (F6)
  left **PENDING**: whether an out-of-range id 500s on Postgres.

**Convention for recording a falsification**: exists only as prose. The
phrasing drifted from "Mutation-verified:" (2026-08-05) to "Mutation-checked"
(2026-08-07 onward). No standalone artifact, no ledger, no risk-to-test map
exists anywhere in the repo — confirmed by search.

## Open Questions

1. **Where does the risk-to-test map live?** §6.5 of `test-plan.md` promises
   to answer this but is itself `TBD`. A map inside `test-plan.md` keeps one
   contract; a map in `context/foundation/` as its own file survives plan
   refreshes better. This is a plan decision, not a research one.
2. **Does the ledger record per-test or per-risk?** The measured data here is
   naturally per-mutation (one mutation can redden several tests, as R3 did
   with 4). A per-risk map with a mutation column may fit the evidence better
   than a per-test list.
3. **Is the `_household_of` duplication in scope for Phase 1?** It is a
   refactor the 2026-08-14 review already declined. Phase 1 can record its
   testing consequence in the map without touching the code — recommended,
   since Phase 1's charter is verification, not repair of production code.
4. **Risk #6's oracle is still missing.** The invite lifetime rule remains an
   unanswered product question (roadmap S-01 Unknown 2). Phase 1 can only
   record risk #6 as "knowingly uncovered pending a product decision".
5. **Should the plan's §4 stack row be corrected in this phase?** It reads
   15 modules / 178 tests against a measured 17 / 228, and describes the clock
   as an "injected seam" when it is monkeypatching. Both are small factual
   drifts in a frozen section — per the lessons register's "a plan can
   contradict itself" rule, the correction should be written back rather than
   left for the next reader.
