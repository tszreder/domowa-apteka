<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: Household Accounts and Invites

- **Plan**: `context/changes/household-accounts-and-invites/plan.md`
- **Scope**: Phases 1–5 of 5 (full plan)
- **Date**: 2026-08-07
- **Verdict**: NEEDS ATTENTION
- **Findings**: 0 critical, 3 warnings, 6 observations

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| Plan Adherence | WARNING |
| Scope Discipline | PASS |
| Safety & Quality | WARNING |
| Architecture | WARNING |
| Pattern Consistency | PASS |
| Success Criteria | WARNING |

> **Post-review correction (2026-08-07).** Two findings were re-verified against the source
> after the first draft. **F1 was downgraded** from WARNING/HIGH to OBSERVATION/MEDIUM — its
> affected population is far smaller than first stated, and an escape hatch exists (see the
> finding). **F9 was withdrawn** — the learning doc's claim is scoped to
> `households/templates/*.html`, which genuinely carries no classes; the sub-agent paraphrased
> it as "no CSS classes in any template", which the doc does not say. Counts and the Pattern
> Consistency verdict above reflect both corrections. The overall verdict is unchanged.

## Triage outcome (2026-08-07)

All 9 findings triaged. 7 fixed, 1 recorded as a recurring rule (and fixed), 1 skipped.

| | Findings |
|---|---|
| Fixed | F2, F3 (Fix A), F4, F6, F7, F8, F10 |
| Rule + fixed | F5 → `lessons.md`, "Verify a database-engine behaviour difference before designing around it" |
| Skipped | F1 |

Post-triage gate, run locally: `uv sync --locked` in sync · `manage.py check` no issues ·
`uv run mypy` clean (20 files) · `makemigrations --check --dry-run` no changes ·
`manage.py test` 33 tests OK (was 32 — F4 added a double-submit test).

**Carried forward:** Phase 4 manual item **4.5** (two-browser live-URL join test) was verified
against the pre-split join flow and has been **re-opened to `[ ]`** in the plan's `## Progress`
section — it must be re-run on the live URL before this ships. 4.6–4.8 are unaffected: they
exercise the refusal and token-revocation branches, which F4 did not change.

Also corrected during triage: the F4 decision note originally claimed the new test covered the
double-submit race. Mutation-checked and withdrawn — see the note under F4.

## Automated verification (re-run 2026-08-07)

The plan's 23 automated checkboxes dedupe to seven commands. All pass:

| Command | Result |
|---|---|
| `uv sync --locked` | Resolved 22 packages, checked 20 — in sync |
| `uv run python manage.py check` | No issues (0 silenced) |
| `uv run mypy .` | Success — no issues in 21 source files |
| `uv run python manage.py test` | 32 tests, OK |
| `uv run python manage.py collectstatic --noinput` | 2 copied, 127 unmodified, 128 post-processed |
| `uv run python manage.py makemigrations --check --dry-run` | No changes detected |
| `uv run python manage.py migrate` | No migrations to apply |

Manual checkboxes 1.7–5.9 are all `[x]`. They are live-URL checks that leave no diff evidence by construction, and each phase carries a corroborating production-confirmation commit (`909e3d9`, `21f26e5`, `ed25402`, `714d7f6`) plus the note in `change.md`. Not flagged as rubber-stamping — this is the project's established evidence pattern.

## Scope notes

- `AGENTS.md` (44930cd) and `CLAUDE.md` (98172e0) appear in the naive commit range but belong to unrelated commits. Excluded from review.
- `CLAUDE.md` is modified in the working tree but uncommitted — out of scope for a review of what shipped.
- Scope guardrails ("What We're NOT Doing") verified clean by grep across `*.py`/`*.html`/`*.toml`/`*.yml`: no mail flow, no member removal, no household rename or delete, no profile editing, no household switcher, no invite expiry or audit log, no rate limiting, no pharma model, no `SECURE_SSL_REDIRECT`/HSTS. Nothing to flag as EXTRA.
- `join_refused.html` and `docs/learning/_glossary.md` are not in the plan's explicit file list but are implied by the Phase 4 and Phase 5.4 contracts. Treated as expected.

## Findings

### F1 — Invite token is not consumed on the login path

- **Severity**: 👁️ OBSERVATION
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality
- **Location**: households/views.py:59-61
- **Detail**: The anonymous branch of `join` stashes the token and redirects to `/signup/` only. `auth_login` calls `cycle_key()`, which preserves session data, so the token survives a login — but `INVITE_TOKEN_SESSION_KEY` is read in exactly one place: `views.py:32`, inside `signup`. Nothing on the login path, in `household_create`, or in `item_list` consumes it.

  **Affected population is small.** Reaching a bad state requires a user who has an account but *no* membership. Every account created through `/signup/` gets one — both branches at `views.py:34-43` create a household, and `form.save()` is **inside** the `transaction.atomic()` block (verified at `views.py:35`), so there is no partial-signup path that commits a `User` without a `Membership`. That leaves the pre-existing superuser (which the plan's Migration Notes call out by name) and anything an admin hand-deleted. An ordinary existing user who clicks an invite link and logs in already has a household, hits `hasattr(user, 'membership') == True`, and gets `join_refused.html` — the designed Phase 4 case (c), working correctly.

  **An escape hatch exists.** Even for the superuser, simply clicking the invite link again after logging in hits case (b) and joins correctly. The bad state needs a specific sequence: click link → log in → get bounced `/list/` → `/household/create/` → *fill in that form* instead of re-clicking the link. Only then does the invite link start refusing. And that user is the admin, so `/admin/` is a recovery path.

  Still worth a decision, because there is no leave/remove-membership view anywhere in the app (`Membership` deletion exists only via `MembershipAdmin`), and no test covers the login-then-join sequence at all. The implementation faithfully follows the plan — Phase 4's contract lists only three arrival cases and omits the already-registered invitee. This is a plan gap, not code drift.
- **Fix A ⭐ Recommended**: Consume the stashed token on the login path too — subclass `LoginView` (already explicitly wired at `urls.py:12-19` with a custom `authentication_form`) and pop the token in `form_valid`, creating the membership when the user has none; also make `join`'s anonymous branch offer login alongside signup.
  - Strength: Puts consumption on the one other path that creates an authenticated session, so both entry points behave identically. The mechanism is the same `session.pop()` already proven at `views.py:32`.
  - Tradeoff: Duplicates signup's join-or-create branch unless extracted to a shared helper; two places then touch the session key.
  - Confidence: HIGH — `cycle_key()` preserving session data across login is verified Django behavior, and `LoginView` is already subclass-ready here.
  - Blind spot: A user logging in with a stale/revoked stashed token needs the same `filter().first()` fallback that 122cc16 added to signup — not yet checked.
- **Fix B**: Leave the join flow as-is and add a recovery path instead — a "leave household" action so a mis-placed user can fix themselves.
  - Strength: Fixes the unrecoverability, which is what makes the bug bite, rather than the narrower trigger.
  - Tradeoff: "Leaving a household" is explicitly on the plan's What-We're-NOT-Doing list. This expands the slice into account management — the exact hazard the roadmap named for S-01.
  - Confidence: MEDIUM — solves the symptom class but contradicts a stated scope boundary.
  - Blind spot: Does not stop the wrong-household state from being created in the first place.
- **Decision**: SKIPPED — accepted as a known gap. The affected population is the pre-existing superuser plus any hand-deleted membership, the escape hatch (re-click the invite link) works, and `/admin/` is a recovery path for the one user who can hit it. Fix B was rejected on scope: "leaving a household" is on the plan's What-We're-NOT-Doing list.

### F2 — `test_session_key_cleared_after_signup...` cannot fail

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Success Criteria
- **Location**: households/tests/test_invites.py:36-61
- **Detail**: Phase 4.4's contract requires proving "the session key is cleared afterwards so a later signup does not silently rejoin". Line 48 calls `self.client.post(reverse('households:logout'))` before carol's signup, and logout flushes the session — so the token is gone regardless of whether the view used `pop` or `get`. Measured: mutating `views.py:32` from `session.pop(...)` to `session.get(...)` leaves all 32 tests green. No assertion anywhere checks the key is absent after signup (line 21 only checks it is *present* before). The implementation is correct; the test guarding it is toothless. Since the plan calls this out as the mechanism that stops a shared browser from silently joining an uninvited household, the guard matters.
- **Fix**: Add `self.assertNotIn(INVITE_TOKEN_SESSION_KEY, self.client.session)` after the bob signup POST (line 47), before the logout.
- **Decision**: FIXED — assertion added at `test_invites.py:48`. Mutation-verified: with `views.py:32` changed back to `session.get(...)` the test now fails (`'invite_token' unexpectedly found in ... SessionStore`); mutation reverted.

### F3 — Cross-household detail assertion is mutation-dead

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Success Criteria
- **Location**: households/tests/test_access_control.py:17-24
- **Detail**: Phase 5.3's contract requires "a member of household A cannot reach household B's detail page" — the PRD's hard privacy guardrail. `test_household_detail_only_ever_resolves_own_household` logs in `member_a` and asserts `response.context['household'] == self.household_a`. Because `setUp` creates `household_a` first, that assertion survives even a global-resolve bug: measured, replacing `views.py:84` `household = user.membership.household` with `Household.objects.first()` leaves 10/10 tests in the file green. Lines 23-24 (`assertNotContains` on B's name and token) are template-leakage guards, not authorization guards. The sibling `test_item_list_only_ever_resolves_own_household` (line 26-31) logs in the *second* user and **does** catch the same mutation (`AssertionError: <Household: Kowalscy> != <Household: Nowakowie>`). Underlying cause: `/household/` carries no pk, so there is no attacker-controlled identifier and no IDOR surface — the criterion as written is unrepresentable against this design.
- **Fix A ⭐ Recommended**: Mirror the `item_list` test — log in `member_b` for the detail test and assert `response.context['household'] == self.household_b`.
  - Strength: Small change, and the `item_list` sibling already proves this shape catches a global-resolve bug (measured against both tests).
  - Tradeoff: Still not an authorization test — it pins the resolution source, nothing more.
  - Confidence: HIGH — measured directly.
  - Blind spot: None significant.
- **Fix B**: Reword the plan's Phase 5.3 criterion to what the design actually guarantees — "no view accepts a household identifier" — and assert that against the URLconf.
  - Strength: Tests the real invariant. The IDOR class is eliminated by URL design, not by a runtime check, so that is the thing worth locking down.
  - Tradeoff: Rewrites a success criterion after the fact; a URLconf assertion has no precedent in this codebase.
  - Confidence: MEDIUM — correct in principle, unusual test shape here.
  - Blind spot: Would not catch a future view resolving a household from a POST body or query string rather than a URL kwarg.
- **Decision**: FIXED via Fix A — `test_access_control.py:17-24` now logs in `member_b` and asserts `household_b`; the two `assertNotContains`/`assertNotIn` guards were inverted to household A's name and token. Mutation-verified: with `views.py:84` replaced by `Household.objects.first()` the test now fails (`<Household: Kowalscy> != <Household: Nowakowie>`); mutation reverted.

### F4 — `join` mutates state on GET; concurrent requests raise an uncaught IntegrityError

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality
- **Location**: households/views.py:65-66
- **Detail**: `hasattr` at line 65, `Membership.objects.create` at line 66, no `try/except`, autocommit. Two in-flight requests for the same user — a double-click on the invite link, or a reload during a slow join — both pass the `hasattr` check, and the second violates the `UNIQUE` on `households_membership.user_id`, surfacing as a 500 on an otherwise successful operation. This does **not** contradict the plan's ordering requirement: the resolve → check → branch → create order is correct and the code does not rely on catching `IntegrityError`; the concurrent case is simply unguarded. Joining is also irreversible with no confirmation step and no undo (see F1). On CSRF specifically: `SESSION_COOKIE_SAMESITE` is Django's default `Lax`, so the `<img src="/join/TOKEN/">` variant is already blocked — the subresource request arrives anonymous. The residual exposure is a clicked link, which is what an invite link inherently is. So this is a reliability and irreversibility finding, not a CSRF one.
- **Fix**: Split `join` into GET (renders a "Join <household>?" confirmation) and POST (creates the membership), matching the `require_POST` pattern already used for `regenerate_invite` at `views.py:97`.
  - Strength: One change closes the double-click race, adds the missing confirmation before an irreversible action, and reuses a pattern already in this file.
  - Tradeoff: Adds a click to the slice's headline flow, plus a new template; `test_invites.py` join tests need updating from GET to POST.
  - Confidence: HIGH — `require_POST` + CSRF form is already proven at `household_detail.html:11-14`.
  - Blind spot: Haven't checked whether the anonymous branch should also move behind POST; it only writes to the session, so probably not.
- **Decision**: FIXED — `join` now renders `households/join_confirm.html` (new template) on GET and only creates the `Membership` on POST. The create uses `Membership.objects.get_or_create(user=user, defaults={'household': household})`, which catches the `IntegrityError` and re-gets, so a double-submitted confirmation form cannot 500 either. The anonymous branch stays on GET (it only writes to the session). `test_authenticated_household_less_user_joins_directly` became `..._confirms_then_joins_on_post` (asserts GET renders the confirmation and creates nothing), plus a new `test_sequential_repeat_post_is_refused_not_duplicated`.

  **What is and isn't test-covered here** (checked by mutation, same method as F2/F3): reverting `get_or_create` to a bare `create` leaves all 11 invite tests green. The sequential re-POST test does *not* exercise the race — by the second request the membership is loaded with `request.user`, `hasattr` is True, and the view takes the already-a-member branch without reaching `get_or_create` at all. The `created=False` fall-through is unreachable from a single-threaded `TestCase`; it is the same "unrepresentable against this design" situation as F3. The guard is real and verified by reading, not by a test. The GET-does-not-mutate half of the fix *is* covered.

  **Follow-up:** Phase 4's manual criteria were verified against the pre-split flow and need re-checking on the live URL after this ships.

### F5 — The plan's SQLite/Postgres case-sensitivity premise is factually wrong

- **Severity**: 👁️ OBSERVATION
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Plan Adherence
- **Location**: context/changes/household-accounts-and-invites/plan.md:64-68, plan.md:110-116
- **Detail**: The plan states that `unique=True` on a username column "is case-sensitive on Postgres and effectively case-insensitive on SQLite", and builds a Critical Implementation Detail on it: "normalizing only at signup lets `Alice@x.com` fail to log in against a stored `alice@x.com` in production while every test passes on CI's SQLite." Measured against Django's actual `auth_user` DDL (`varchar NOT NULL UNIQUE`, default BINARY collation): an exact-match query for the lowercase value against a stored mixed-case row returns **0 rows**, and inserting `alice@example.com` alongside `Alice@Example.com` **succeeds**. SQLite is case-sensitive here, same as Postgres. `ModelBackend` authenticates via `get_by_natural_key`, an exact match — so `test_auth.py:78` genuinely fails on CI if `.lower()` is removed from `clean_username`. The guard is real, the test protecting it is real, and CI does cover it. Only the stated rationale is wrong. This is the same class of error as the accepted lesson "Verify a platform limitation before registering it as a risk" (`lessons.md:5`) — an unverified negative capability claim written into a planning contract that downstream skills read as ground truth.
- **Fix**: Correct the premise in the plan so a future maintainer does not add a Postgres-only CI job to chase a non-problem. Strong `/10x-lesson` candidate given the exact match to the existing rule.
- **Decision**: FIXED + ACCEPTED-AS-RULE: "Verify a database-engine behaviour difference before designing around it" — appended to `context/foundation/lessons.md`. The plan's Key Discoveries bullet and the "Email case must be normalized in two places" Critical Implementation Detail both now carry a dated correction stating that SQLite is case-sensitive here too, that CI does catch a missed normalization, and that `test_auth.py:78` is the test doing it. The `.lower()` guard and its test are untouched.

### F6 — `household_required` guards one of three eligible views, and the one view using it repeats the check unreachably

- **Severity**: 👁️ OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Architecture
- **Location**: households/views.py:127-131
- **Detail**: `item_list` carries `@household_required` at line 127 and then repeats `if not hasattr(user, 'membership'): return redirect(...)` at lines 130-131 — unreachable, since the decorator already guarantees membership. Meanwhile `household_detail` (lines 78-82) and `regenerate_invite` (lines 96-101) hand-roll the identical `@login_required` + `hasattr` + redirect pattern and could use the decorator. (`household_create` correctly must not — it is the redirect target.) Behavior is right in all four; this is duplication plus dead code, and it means the decorator the plan describes as "one guard for every household-scoped view" is currently one guard for one view.
- **Fix**: Apply `@household_required` to `household_detail` and `regenerate_invite`, and delete the unreachable branch at `views.py:129-131`.
- **Decision**: FIXED — both views now carry `@household_required` (`regenerate_invite` keeps `@require_POST` beneath it, preserving the 302-for-anonymous / 405-for-member-GET behavior its tests assert), and the dead branch in `item_list` is gone. Removing the `hasattr` checks also removed the narrowing mypy relied on for the untyped reverse one-to-one, so the three views now read the household through a new `_household_of()` helper (`views.py:21-30`) that casts the cached descriptor — no extra query. `uv run mypy` clean, 33 tests pass.

### F7 — `uv run mypy .` overrides the configured `files` restriction

- **Severity**: 👁️ OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Adherence
- **Location**: .github/workflows/deploy.yml:49
- **Detail**: Phase 1.5's contract restricts checked files to `households` and `domowa_apteka`, and `pyproject.toml` does configure `files = ["households", "domowa_apteka"]`. But passing a path on the command line overrides that setting. Measured: `mypy .` checks 21 source files, bare `mypy` checks 20 — the delta is only `manage.py`, so impact today is nil. The configured restriction is not actually in force, and adding any top-level `.py` file silently widens the blocking CI gate.
- **Fix**: Drop the `.` from the CI step (`uv run mypy`) so the `files` setting governs, or delete the `files` setting and accept whole-repo checking as the real convention.
- **Decision**: FIXED — `.github/workflows/deploy.yml:49` now runs `uv run mypy`, so `pyproject.toml:22` is the single source of truth for scope and a bare local `uv run mypy` checks exactly what CI checks. The alternative (deleting `files`) was rejected because it breaks the bare command, forcing everyone to remember the `.` forever.

### F8 — Two join-refusal tests assert the status code but not which branch rendered

- **Severity**: 👁️ OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Success Criteria
- **Location**: households/tests/test_invites.py:76-97
- **Detail**: `test_authenticated_user_with_other_household_is_refused...` (line 76) and `test_authenticated_member_clicking_own_link_sees_plain_confirmation` (line 90) both check `status_code == 200` plus membership counts, but neither asserts `response.context['same_household']` nor `assertTemplateUsed(response, 'households/join_refused.html')`. Both would pass with the *wrong* branch of `join_refused.html` rendered — i.e. telling a stranger "you already belong to this household". Phase 4's contract distinguishes the two messages explicitly.
- **Fix**: Add one `assertEqual(response.context['same_household'], True/False)` to each test.
- **Decision**: FIXED — `assertEqual(response.context['same_household'], False)` added to the other-household refusal test and `..., True)` to the own-link test, so swapping the branch now fails the suite.

### F9 — WITHDRAWN (not a finding)

Draft F9 claimed `docs/learning/django-templates-and-css.md` asserts "no CSS classes in any
template", contradicted by `class="container"` / `class="messages"` in `templates/base.html`.
Re-read of the source: line 102 says `households/templates/*.html` "never needs a single
`class="..."` attribute" — scoped to the app templates, which genuinely carry none. `base.html`
is outside that scope. The doc is accurate; the paraphrase was not. No action.

### F10 — `join` success redirects to `/household/`, not the list as the plan states

- **Severity**: 👁️ OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Adherence
- **Location**: households/views.py:68
- **Detail**: Phase 4's contract for the authenticated-no-membership case says "create the `Membership`, redirect to the list with a success message". Line 68 redirects to `households:household_detail`. Defensible at Phase 4 — `/list/` did not exist yet — but Phase 5 created it and never revisited this, and `test_invites.py:72` now locks the old destination in. Arguably `/household/` is the better landing page for a new joiner (they see who else is there), so this may be worth ratifying rather than reverting.
- **Fix**: Decide which destination is intended and make plan and code agree.
- **Decision**: FIXED — plan amended to match the code. Phase 4's "Authenticated, no membership" bullet now says `/household/` and records why: a new joiner's first question is who else is in the household, which the detail page answers and the (empty until S-02) list does not. Code and test unchanged. The same amendment documents the GET-confirm / POST-create split from F4.
