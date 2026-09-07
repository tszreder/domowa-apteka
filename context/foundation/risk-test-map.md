---
title: Risk-to-Test Map
last_updated: 2026-09-05
last_updated_by: testing-coverage-truth-pass (Phase 1)
---

# Risk-to-Test Map

This file is the canonical answer to "is risk N covered, by what, and how strongly?" for
this project. It replaces line coverage as this project's coverage metric, per
`test-plan.md` §1 principle #4 and §4's "coverage measurement" row.

**Maintained by**: each rollout phase's `/10x-implement` step appends rows to the
falsification ledger (§ below) and updates the per-risk table when a phase changes a
risk's status.

**Source of truth**: `context/foundation/test-plan.md` §1–§3 define the risks.
`context/changes/testing-coverage-truth-pass/research.md` is the measurement basis for
this initial version.

---

## Per-Risk Coverage Table

| Risk # | Risk (one line) | Status | Falsifiable test(s) | Note |
|--------|-----------------|--------|---------------------|------|
| #1 | Wrong product identity saved when two products share a name | **Not yet covered** | none | No test exercises the save path with two distinct active products present. Measured: forcing `item_add` to ignore the POSTed `product_id` and save a different product leaves all 228 tests green (N2). Owner of closing this gap: rollout Phase 2 ("Add-item integrity"). |
| #2 | Stale or bad registry data served as current | **Covered, one weak point** | `registry/tests/test_import_run.py` (`ImportRunStatusTests`, `TransactionIsolationTests`), `registry/tests/test_loader.py` (`SnapshotOrderTests`, `TruncationHandlingTests`) | `PlausibilityGuardTests` (`test_loader.py:271–294`) proves the `MIN_EXPECTED_PRODUCTS` rollback mechanism only by artificially lowering `--min-products` against the full 14-product fixture — never against a genuinely short but well-formed file. Accepted as-is; gap is known. |
| #3 | Wrong active-substance set parsed from the XML | **Partially covered** | `registry/tests/test_parser.py::DroppedRowNumberingTests` | The fallback display-name spelling rule at `parser.py:289` is unobserved by all 51 registry tests (N3): swapping the vocabulary-lookup source leaves 51 tests green. Closing this gap is deferred to rollout Phase 2. |
| #4 | A swallowed lookup failure lets a product-less item save | **Structurally prevented, one branch untested** | `pharmacy/forms.py::ItemAddForm.product` (schema-level `ModelChoiceField` with `required=True`) | The "saved as though it resolved" mode is closed by the form contract, not by convention — a missing or invalid `product` value fails Django validation before `Item.save()` is called. Gap: no test posts *without* a `product` value; the branch falls back to Django's untranslated English "This field is required." (risk: `error_messages` overrides only `invalid_choice`). Deferred to rollout Phase 2. |
| #5 | Cross-household read (IDOR) | **Covered, not where it looks** | Item-leak guard: `pharmacy/tests/test_item_list.py::test_item_in_household_a_never_appears_for_member_of_household_b`, `pharmacy/tests/test_product_check.py`. Misresolution guard: `households/tests/test_access_control.py::CrossHouseholdIsolationTests` | `test_access_control.py` stays 10/10 green under a live item-level leak (N1b) — it proves household *resolution* is scoped to the logged-in user, not that household-owned records never leak. Real item-leak guard lives in `pharmacy/`. Additional note: `_household_of` is duplicated verbatim in `households/views.py:21` and `pharmacy/views.py:20`; a falsification of one copy says nothing about the other. |
| #6 | Invite artifact outliving its purpose | **Knowingly uncovered** | `households/tests/test_invites.py` (session-hygiene coverage only) | The login path (`/login/`) never reads or clears the session-stashed invite token; a user who clicks an invite link, then logs in directly, never joins the household. No test covers this path. Explicitly triaged and SKIPPED in the 2026-08-05 review (affected population narrow; escape hatch: re-click the link). Additionally, the underlying product rule (roadmap S-01 Unknown 2: do invite links expire?) is still unrecorded — there is no oracle to test against. |

---

## Falsification Ledger

Each row represents one mutation applied, its target module run, the observed result, and
whether the repair (or assertion) still holds. Rows are append-only; never remove a row.

**Convention for adding a row**: use the "How to record a falsification" procedure in
`§ How to record a falsification` below.

| Date | # | Risk | Mutation applied | Target module | Result | Verdict |
|------|---|------|-----------------|--------------|--------|---------|
| 2026-08-05 | R1 (original) | #6 | `households/views.py:43` `session.pop(...)` → `session.get(...)` | `households.tests.test_invites` | RED — 1 failure at line 48 | Repair holds |
| 2026-08-05 | R2 (original) | #5 | `households/views.py:29` `return membership.household` → `Household.objects.first()` | `households.tests.test_access_control` | RED — 1 failure at line 22 (`Kowalscy != Nowakowie`) | Repair holds |
| 2026-08-07 | R3 (original) | #3 | `registry/parser.py:189` `enumerate(kept)` → `enumerate(rows)` | `registry.tests.test_parser` | RED — 4 failures | Repair holds firmly |
| 2026-09-05 | R1 (re-run) | #6 | Same as R1 original | `households.tests.test_invites` | RED — 1 failure, `test_session_key_cleared_after_signup_so_later_signup_does_not_rejoin` line 48: `AssertionError: 'invite_token' unexpectedly found in session` | Repair still holds |
| 2026-09-05 | R2 (re-run) | #5 | Same as R2 original | `households.tests.test_access_control` | RED — 1 failure at line 22, `Kowalscy != Nowakowie` | Repair still holds |
| 2026-09-05 | R3 (re-run) | #3 | Same as R3 original | `registry.tests.test_parser` | RED — 4 failures | Repair still holds |
| 2026-09-05 | N1b | #5 | `pharmacy/views.py:30` + `:137` `Item.objects.filter(household=household)` → `Item.objects.all()` | `households.tests.test_access_control` | GREEN — 10/10 OK | `test_access_control.py` cannot see a live item-level leak |
| 2026-09-05 | N1b′ | #5 | Same mutation as N1b | `pharmacy.tests.test_item_list`, `test_product_check` | RED — 1 failure each | Real item-leak guard lives in `pharmacy/` |
| 2026-09-05 | N2 | #1 | `pharmacy/views.py:71` force `item.product = Product.objects.filter(is_active=True).order_by('registry_id').first()` | full suite (228 tests) | GREEN — 228/228 OK | No coverage at all for risk #1 at the save layer |
| 2026-09-05 | N3 | #3 | `registry/parser.py:289` `name = vocabulary.get(name_key)` → `product.common_name.strip()` | `registry.tests.test_parser` + `test_loader` (51 tests) | GREEN — 51/51 OK | Fallback-spelling rule unobserved |

---

## How to Record a Falsification

1. **Identify the assertion** — pick the test method and the exact line that claims to
   protect the behaviour you want to verify.
2. **Apply the smallest breaking mutation** — change exactly the production-code line
   whose deletion or corruption should make the assertion fail. Do not change the test.
3. **Run the narrowest containing module** — use `uv run manage.py test <app>.<module>`
   rather than the full suite unless the question is "does *anything* catch this?".
4. **Confirm the expected failure** — the test must go red with a failure that names the
   assertion you targeted. A different test going red (or no test going red) is evidence
   of a gap, not proof of coverage.
5. **Revert** — `git checkout -- <file>`. Confirm `git status --porcelain` is empty
   before moving on. Never leave a mutation applied.
6. **Append one row to the ledger** above, using today's date, and update the per-risk
   table if the risk's Status cell changes.

**If the assertion does not redden**: it is not falsifiable — repair it or record the gap
honestly in the per-risk table. Never mark the risk "covered" if the mutation passes.
