# Household Accounts and Invites — Implementation Plan

## Overview

Build the first user-facing surface in `domowa-apteka`: an adult can sign up, gets a
household, can share an invite link, and a second adult can join it and immediately see the
same shared list. This is roadmap slice **S-01**, and it is also the project's **first Django
app** — so it establishes the app layout, template and static shell, UI language, and
type-checking convention that every later slice inherits.

## Current State Analysis

The repo is a production-deployed Django scaffold with no application code.

- `INSTALLED_APPS` is stock `django.contrib` only (`domowa_apteka/settings.py:74-81`). Zero
  project apps, zero models.
- `TEMPLATES['DIRS']` is `[]` with `APP_DIRS: True` (`settings.py:98-111`). No template
  anywhere in the repo, no `base.html`.
- No `STATICFILES_DIRS`. `STATIC_ROOT` and WhiteNoise are configured and working
  (`settings.py:163-178`), so a project-level `static/` dir needs one settings line to be
  picked up by `collectstatic`.
- The only route besides `/admin/` is a `health` view (`domowa_apteka/urls.py:22-33`).
- `django.contrib.auth` and `AuthenticationMiddleware` are wired and proven: a superuser
  exists and `/admin/` login was verified end-to-end over HTTPS. Missing is the entire
  user-facing half — no login view, no signup, no household concept.
- **`auth.0001_initial` is already applied**, locally and in production Postgres (verified
  via `manage.py showmigrations`; production boot logged `No migrations to apply`, see
  `context/deployment/deploy-plan.md:313-318`). This closes the window on `AUTH_USER_MODEL`.
- **No `EMAIL_*` configuration exists.** Django's default backend is SMTP on localhost,
  which fails in production. Nothing in this slice may depend on sending mail.
- `LANGUAGE_CODE = 'en-us'`, `USE_I18N = True`, and `LocaleMiddleware` is **not** installed
  (`settings.py:151-157`, `settings.py:83-94`).
- No linter, formatter, or type-checker is configured. `context/foundation/tech-stack.md`
  calls for a type-hints-everywhere plus mypy convention "once apps exist"; this slice is
  that moment. Existing code already carries hints (`urls.py:22`).
- CI (`.github/workflows/deploy.yml`) runs `uv sync --locked`, `manage.py check`, and
  `manage.py test` on every PR. `manage.py test` currently finds **zero tests** — the
  deploy plan explicitly flags the `check` job as a thin gate until the first app lands
  (`deploy-plan.md:330-333`).
- CI runs on **SQLite** (no `DATABASE_URL` in the workflow); production is **Postgres**.

## Desired End State

Two adults, on their phones, can each hold an account; one creates the household implicitly
by signing up, shares a link over a messenger, and the other joins through it and lands on
the same (empty, for now) shared list. Both see each other in the member list. The link can
be revoked by regenerating it. No user can reach another household's data.

Verify by: signing up on the live Railway URL from a phone, copying the invite link into a
private browser window, completing a second signup through it, and confirming both accounts
show the same household with both members listed — then regenerating the link and confirming
the old URL no longer joins.

### Key Discoveries:

- `AUTH_USER_MODEL` cannot be swapped without recreating the production database
  (`auth` tables are live) — so stock `auth.User` is the design, not a compromise chosen
  from ignorance. `deploy-plan.md:313-318`.
- No email backend exists, which independently rules out passwordless auth **and** makes
  `include('django.contrib.auth.urls')` a trap: it registers password-reset views that
  render fine and then 500 on submit.
- `migrate --noinput` runs inside `railway.json`'s `startCommand`, with
  `restartPolicyMaxRetries: 3` and `numReplicas: 1`. A failed migration is a restart loop
  and a rolled-back deploy, not a clean error.
- The SQLite-in-CI / Postgres-in-prod split (documented in
  `docs/learning/database-migrations-and-dev-prod-parity.md`) makes string case a live
  hazard: `unique=True` on a username column is case-sensitive on Postgres and effectively
  case-insensitive on SQLite. A test suite green on CI would not catch it.
- `APP_DIRS: True` means app templates work with no settings change; only the shared
  `base.html` and the project-level `static/` dir need `settings.py` edits.

## What We're NOT Doing

The roadmap's stated hazard for this slice is "the invite flow quietly growing into account
management the PRD never asked for." Explicitly out of scope:

- Password reset, password change, email verification, or any flow that sends mail.
- Removing a member, leaving a household, deleting a household, transferring ownership.
- Renaming a household after creation.
- Editing a user profile, display names, or avatars.
- Multiple households per user, or any household switcher.
- Invite expiry, per-invitee tokens, or an invite audit log (a single standing token per
  household, revoked by regeneration, is the whole mechanism).
- Rate limiting or brute-force protection on signup and login.
- Any pharmaceutical, substance, or list-item model — S-02 owns those. This slice ships the
  empty shell only.
- `SECURE_SSL_REDIRECT` and HSTS (parked in the roadmap, unchanged here).

## Implementation Approach

One new Django app, `households`, owning both the account surface and the household model.
Signup and login live there rather than in a separate `accounts` app because in this product
an account exists only to be a member of a household — splitting them would create an app
with three views and no models.

The one-household-per-user rule is enforced by the database, not by application code:
`Membership.user` is a `OneToOneField`, so a second membership raises `IntegrityError`
rather than silently creating an ambiguous state. `request.user.membership.household` is
then the single access path every later slice uses.

Auto-create-unless-invited is realised by making `/join/<token>/` stash the token in the
session when hit anonymously. The signup view checks for that stashed token: present means
join the named household, absent means create a new one. The two paths never overlap, which
is what keeps an invited user from arriving already-in-a-household.

Phases are ordered so migrations land exactly once, in Phase 2, and are purely additive.

## Critical Implementation Details

**Email case must be normalized in two places, and CI cannot catch a miss.** The lowercased
email is stored in `User.username`, whose `unique=True` is case-sensitive on Postgres and
effectively case-insensitive on SQLite. Normalize in the signup form's `clean` **and** in
the authentication form's `clean_username` — normalizing only at signup lets
`Alice@x.com` fail to log in against a stored `alice@x.com` in production while every test
passes on CI's SQLite.

**Setting `LANGUAGE_CODE = 'pl'` changes strings the tests read.** Django's own validation
messages ("This field is required", the password validators) become Polish. Assert against
form field keys and error codes (`form.errors['username']`, `ValidationError.code`), never
against rendered message text, or the suite breaks on a Django locale update. Do **not** add
`LocaleMiddleware` — without it the language is fixed by the setting rather than negotiated
per request, which is what makes test behavior deterministic.

**The stashed invite token must be cleared after use.** If `/join/<token>/` writes the token
to the session and the signup view does not `pop` it, a user who abandons signup and returns
later — or a shared browser — silently joins a household nobody invited them to on their
next signup.

**Migrations run at container boot.** Phase 2's migration is the only one in this slice and
it only creates tables. Keep it that way: `migrate --noinput` sits in `railway.json`'s
`startCommand` with `restartPolicyMaxRetries: 3`, so a migration that fails on production
data produces a restart loop and a rolled-back deploy rather than a readable error.

---

## Phase 1: First app, UI shell, and type-checking

### Overview

Create the `households` app, the shared template and static shell, and wire mypy into CI —
before any feature code exists, so the convention is set rather than retrofitted. Ships as a
deployable no-op with one visible landing page.

### Changes Required:

#### 1. The app itself

**File**: `households/` (via `uv run python manage.py startapp households`)

**Intent**: Create the project's first app so there is somewhere for models, views, and
tests to land.

**Contract**: Standard `startapp` layout. Delete the unused `models.py` boilerplate comment
but keep the file. Add `'households'` to `INSTALLED_APPS` in `domowa_apteka/settings.py`.

#### 2. Template and static wiring

**File**: `domowa_apteka/settings.py`

**Intent**: Give the project a shared `base.html` that every app's templates extend, and a
project-level `static/` directory that `collectstatic` picks up. Also switch the UI locale.

**Contract**: `TEMPLATES[0]['DIRS'] = [BASE_DIR / 'templates']`;
`STATICFILES_DIRS = [BASE_DIR / 'static']`; `LANGUAGE_CODE = 'pl'`. Leave `USE_I18N` at
`True` and do **not** add `LocaleMiddleware`. Add `LOGIN_URL`, `LOGIN_REDIRECT_URL`, and
`LOGOUT_REDIRECT_URL` in the same edit — Phase 3 needs them and they are pure configuration.

`LOGIN_REDIRECT_URL` points at `/` for now, **not** `/list/`: the list shell does not exist
until Phase 5, so pointing at it here would send every Phase 3 and Phase 4 login to a 404.
Phase 5 moves it. `LOGOUT_REDIRECT_URL` is `/` permanently.

#### 3. Vendored classless stylesheet and base template

**File**: `static/css/pico.min.css`, `static/css/app.css`, `templates/base.html`

**Intent**: Establish a phone-usable visual baseline with no build step. The stylesheet is
committed rather than loaded from a CDN so the app has no external runtime dependency and
dev works offline. Pico.css is the default; any stylesheet from `cssbed.com` is a drop-in
swap because no template carries CSS classes.

**Contract**: `base.html` defines `{% block content %}` and a `{% block title %}`, loads
both stylesheets via `{% static %}` (Pico first, `app.css` second so overrides win), and
sets `<meta name="viewport" content="width=device-width, initial-scale=1">` — without that
tag a phone browser renders the page at desktop width and zooms out, which defeats the whole
point. `app.css` starts empty; it exists as the documented override seam.

#### 4. Landing page

**File**: `households/views.py`, `households/urls.py`, `households/templates/households/landing.html`, `domowa_apteka/urls.py`

**Intent**: One rendered page so the shell is verifiable in a browser before any feature
exists, and so `include()` wiring is proven.

**Contract**: A view at `/` rendering `landing.html` with Polish copy and links to
`/login/` and `/signup/` (both dead until Phase 3). `domowa_apteka/urls.py` gains
`path('', include('households.urls'))`, placed **after** the existing `health/` and `admin/`
patterns so neither is shadowed.

#### 5. Type checking

**File**: `pyproject.toml`, `.github/workflows/deploy.yml`

**Intent**: Wire the type-hints-everywhere convention `context/foundation/tech-stack.md`
promises, scoped so Django's own dynamic patterns cannot block a merge.

**Do this first, before any other work in this phase.** `django-stubs` constrains the `mypy`
version and pulls `django-stubs-ext`, so a resolution conflict is possible — and because the
CI step below is blocking, that conflict would otherwise surface as a red PR rather than a
local error. Run `uv add --dev mypy django-stubs` and `uv run mypy .` against the existing
two-file codebase as the opening move. If it resolves and passes clean there, the CI step is
safe; if it does not, you have learned it in five minutes with nothing else to unwind.

**Contract**: Add `mypy` and `django-stubs` as dev dependencies with `uv add --dev` (never
pip — `uv.lock` is git-tracked and CI runs `uv sync --locked`). Add a `[tool.mypy]` section
in `pyproject.toml` configuring the `django-stubs` plugin with
`django_settings_module = "domowa_apteka.settings"`, and restrict checked files to
`households` and `domowa_apteka`. Add a blocking `mypy` step to the CI `check` job after
the existing Django system-checks step. Railway builds with `uv sync --locked --no-dev`, so
these do not ship to production.

### Success Criteria:

#### Automated Verification:

- Lockfile is in sync: `uv sync --locked`
- Django system checks pass with the new app installed: `uv run python manage.py check`
- Type checking passes: `uv run mypy .`
- Test suite still runs: `uv run python manage.py test`
- Static files collect, including the vendored stylesheet: `uv run python manage.py collectstatic --noinput`
- No model changes were made accidentally: `uv run python manage.py makemigrations --check --dry-run`

#### Manual Verification:

- Landing page renders at `/` with the stylesheet applied, and is readable at phone width without horizontal scrolling
- Final stylesheet chosen after browsing `cssbed.com` (Pico kept, or one file swapped)
- CI `check` job is green on the PR, with the new mypy step visible in the log

**Implementation Note**: After completing this phase and all automated verification passes,
pause here for manual confirmation from the human that the manual testing was successful
before proceeding to the next phase.

---

## Phase 2: Household and Membership models

### Overview

The full data model for this slice, in one additive migration. Includes the invite token
field so Phase 4 requires no schema change.

### Changes Required:

#### 1. Models

**File**: `households/models.py`

**Intent**: Model a household, its standing invite token, and the one-household-per-user
membership rule — enforcing that rule in the database rather than in view code.

**Contract**: `Household` with `name` (CharField), `created_at`, and `invite_token`
(unique, indexed, populated on save if empty). `Membership` with
`user = OneToOneField(settings.AUTH_USER_MODEL, on_delete=CASCADE, related_name='membership')`,
`household = ForeignKey(Household, on_delete=CASCADE, related_name='memberships')`, and
`joined_at`. The `OneToOneField` is what makes a second membership an `IntegrityError`
rather than an ambiguous state — do not weaken it to a `ForeignKey`.

Token generation uses `secrets.token_urlsafe(32)`, not `uuid4` and not anything seeded from
`random`: this value is the only thing standing between a stranger and a household's medical
data, so it must come from a cryptographically secure source. A `regenerate_invite_token()`
method on `Household` overwrites and saves it — that single overwrite is the entire
revocation mechanism.

#### 2. Migration

**File**: `households/migrations/0001_initial.py`

**Intent**: Create both tables.

**Contract**: Generated by `makemigrations households` and committed. Creation-only, no data
migration, no alterations to `auth` tables.

#### 3. Admin registration

**File**: `households/admin.py`

**Intent**: Make households and memberships inspectable through the already-working
`/admin/` surface, which is the only way to see this data before Phase 4's UI exists.

**Contract**: Register both models with `list_display` covering the fields above. The invite
token may be shown — `/admin/` is superuser-only.

#### 4. Model tests

**File**: `households/tests/__init__.py`, `households/tests/test_models.py`

**Intent**: Prove the invariants the rest of the slice assumes.

**Contract**: Convert `tests.py` to a `tests/` package. Cover: an invite token is generated
on save and is unique across households; `regenerate_invite_token()` produces a different
value and does not alter membership; a second `Membership` for the same user raises
`IntegrityError`; deleting a household cascades to its memberships but does not delete the
`User` rows.

### Success Criteria:

#### Automated Verification:

- Migration is complete and committed: `uv run python manage.py makemigrations --check --dry-run`
- Migration applies cleanly from empty: `uv run python manage.py migrate`
- Model tests pass: `uv run python manage.py test households.tests.test_models`
- Type checking passes: `uv run mypy .`

#### Manual Verification:

- `Household` and `Membership` are visible and editable at `/admin/`
- After merge, the production deploy goes green — confirming the migration applied inside `startCommand` without a restart loop

**Implementation Note**: After completing this phase and all automated verification passes,
pause here for manual confirmation from the human that the manual testing was successful
before proceeding to the next phase.

---

## Phase 3: Signup, login, logout

### Overview

The account surface: email-as-username with lowercase normalization on both write and read
paths, a household auto-created for anyone signing up without an invite, and a signed-in
header carrying logout.

### Changes Required:

#### 1. Forms

**File**: `households/forms.py`

**Intent**: Accept an email address as the login identifier while leaving `auth.User`
untouched, and guarantee the stored and submitted values are compared consistently.

**Contract**: `SignupForm` subclasses `UserCreationForm`, presents the identifier field as
an email input with Polish labels, validates it as an email address, lowercases it, and
writes it to both `username` and `email`. `EmailAuthenticationForm` subclasses
`AuthenticationForm` and lowercases the submitted identifier in `clean_username()`.

Both normalizations are required. See "Critical Implementation Details" — omitting the login
side produces a bug that is invisible on CI's SQLite and real on production Postgres.

#### 2. Views and URLs

**File**: `households/views.py`, `households/urls.py`

**Intent**: Wire signup, login, and logout, and implement the auto-create-unless-invited
rule at the single point where an account comes into existence.

**Contract**: `/signup/` (`CreateView` or function view using `SignupForm`) — on success,
log the user in, then `session.pop()` the stashed invite token: if present, create a
`Membership` to that household; if absent, create a `Household` named from the email's local
part and a `Membership` to it. Both branches run inside `transaction.atomic()` so a failure
cannot leave a user with no household.

`/login/` and `/logout/` use `django.contrib.auth.views.LoginView` (with
`authentication_form = EmailAuthenticationForm`) and `LogoutView`, wired **explicitly**.
Do not use `include('django.contrib.auth.urls')`: it registers password-reset views that
require an email backend this project does not have, and they fail at submit time rather
than at import time.

Note that `LogoutView` requires a POST — a `<a href="/logout/">` link silently 405s. The
header uses a small POST form with `{% csrf_token %}`.

#### 3. Templates and header

**File**: `templates/base.html`, `households/templates/households/signup.html`, `households/templates/households/login.html`

**Intent**: Give the auth flow Polish pages and put the current identity on screen — without
a logout control the two-user flow cannot be manually tested in one browser.

**Contract**: `base.html` gains a header block showing the signed-in email and household
name with a logout form when `user.is_authenticated`, and login/signup links otherwise.
Form templates render `{{ form }}` against the classless stylesheet; no CSS classes.

#### 4. Auth tests

**File**: `households/tests/test_auth.py`

**Intent**: Cover the account lifecycle and the case-normalization hazard specifically.

**Contract**: Cover: signup creates a `User`, a `Household`, and a `Membership` in one
request; the stored `username` is lowercase regardless of submitted case; login succeeds
when the submitted email case differs from the stored one; a duplicate email (differing only
in case) is rejected with a form error; logout clears the session; an authenticated user
hitting `/signup/` is redirected rather than creating a second account.

Assert on form error **keys and codes**, not rendered message text — `LANGUAGE_CODE = 'pl'`
means Django's built-in messages are Polish and subject to change between releases.

### Success Criteria:

#### Automated Verification:

- Auth tests pass: `uv run python manage.py test households.tests.test_auth`
- Full suite still passes: `uv run python manage.py test`
- Type checking passes: `uv run mypy .`
- System checks pass: `uv run python manage.py check`

#### Manual Verification:

- Sign up on the live Railway URL from a phone and land on a signed-in page
- Header shows the signed-in email and household name; logout returns to the landing page
- Polish diacritics render correctly, and Django's own validation errors (e.g. submitting a too-short password) appear in Polish
- Logging in with a differently-cased email succeeds **against production Postgres**, not just locally

**Implementation Note**: After completing this phase and all automated verification passes,
pause here for manual confirmation from the human that the manual testing was successful
before proceeding to the next phase.

---

## Phase 4: Invite link and join flow

### Overview

The slice's payoff: a shareable link, a household page showing who is in it, regenerate-to-
revoke, and a join view that handles all three ways a person can arrive at it.

### Changes Required:

#### 1. Join view

**File**: `households/views.py`, `households/urls.py`

**Intent**: Turn an invite URL into a membership, covering every arrival state without a
500 or a redirect loop.

**Contract**: `/join/<str:token>/` resolves the token to a `Household` or 404s. Three cases,
all of which must be handled explicitly.

**Ordering is load-bearing**: resolve the token → check whether the user already has a
membership (`hasattr(request.user, 'membership')`) → branch → and only then create anything.
Because `Membership.user` is a `OneToOneField`, a naive "create and see what happens" would
raise `IntegrityError` and surface as a 500 — which is precisely what manual check 4.8 and
the "authenticated, already a member" test assert against. The database constraint is the
backstop, not the control flow.

The cases:

- **Anonymous** — stash the token in `request.session`, redirect to `/signup/`. Phase 3's
  signup view consumes it. This is what makes the token survive the signup round-trip.
- **Authenticated, no membership** — create the `Membership`, redirect to the list with a
  success message. (Reachable by the pre-existing superuser, who has no household.)
- **Authenticated, already a member of some household** — render a clear Polish refusal
  page. If it is the *same* household, say so plainly rather than treating it as an error.
  Never attempt to move or delete a membership; that is the account-management scope this
  slice excludes.

#### 2. Household page

**File**: `households/views.py`, `households/templates/households/household_detail.html`

**Intent**: Show the invite link, let it be copied, list current members, and expose
regeneration — the inviter otherwise has no way to confirm the invite worked.

**Contract**: `/household/` renders the household name, its members (email and join date),
and the absolute invite URL built with `request.build_absolute_uri()` so the link carries the
real Railway host rather than a relative path. Regeneration is a **POST** to
`/household/invite/regenerate/` with `{% csrf_token %}` — a GET link would let any page that
embeds the URL silently revoke the household's invite.

#### 3. Household creation fallback

**File**: `households/views.py`, `households/templates/households/household_create.html`

**Intent**: Give users who have no household a way to get one. Normal signup auto-creates,
so this exists for the pre-existing superuser and as the target of Phase 5's decorator —
without it, that redirect has nowhere to point.

**Contract**: `/household/create/` accepts a household name and creates the `Household` plus
`Membership`. Refuses (redirects) if the user already has a membership.

#### 4. Invite tests

**File**: `households/tests/test_invites.py`

**Intent**: Cover the join state machine and the revocation guarantee.

**Contract**: Cover: anonymous join stashes the token and completes on signup; the session
key is cleared afterwards so a later signup does not silently rejoin; an authenticated
household-less user joins directly; an authenticated user with a household is refused with a
non-500 response and gains no second membership; a bogus token 404s; a regenerated token
invalidates the previous URL while the household and its memberships survive unchanged;
regeneration requires POST.

### Success Criteria:

#### Automated Verification:

- Invite tests pass: `uv run python manage.py test households.tests.test_invites`
- Full suite passes: `uv run python manage.py test`
- Type checking passes: `uv run mypy .`
- No stray model changes: `uv run python manage.py makemigrations --check --dry-run`

#### Manual Verification:

- Two-browser test on the live URL: copy the invite link from browser A, open it in a private window, complete signup, and confirm both accounts show the same household with both members listed
- The copied link contains the real production host, not `localhost` or a relative path
- Regenerate the token, then confirm the previously copied URL no longer joins
- An already-in-a-household user clicking someone else's link sees a readable Polish message, not a stack trace

**Implementation Note**: After completing this phase and all automated verification passes,
pause here for manual confirmation from the human that the manual testing was successful
before proceeding to the next phase.

---

## Phase 5: List shell and access-control hardening

### Overview

The empty shared-list page S-02 will fill, the decorator that lets every later view assume a
household exists, and the isolation tests that cover the PRD's privacy guardrail.

### Changes Required:

#### 1. Household-required decorator

**File**: `households/decorators.py`

**Intent**: Give every current and future household-scoped view one guard, so no slice has
to re-derive "which household is this user acting in" or handle the household-less case
defensively.

**Contract**: A `household_required` decorator that redirects anonymous users to
`LOGIN_URL` and authenticated-but-household-less users to `/household/create/`. It must not
redirect a request that is *already* on its own target — the classic source of an infinite
redirect loop. `/household/create/`, `/join/<token>/`, `/login/`, `/signup/`, and `/` stay
undecorated.

#### 2. Shared list shell

**File**: `households/views.py`, `households/templates/households/item_list.html`

**Intent**: Make the slice's stated outcome — "immediately sees the household's shared
list" — literally true, and give S-02 a page to plug into instead of inventing one.

**Contract**: `/list/` (decorated with `household_required`) renders the household name and
an empty state in Polish explaining that no pharmaceuticals have been added yet. No item
model, no add form — S-02 owns those.

This phase also repoints `LOGIN_REDIRECT_URL` from `/` to `/list/` in
`domowa_apteka/settings.py` — Phase 1 deliberately parked it at `/` because this page did
not exist yet.

#### 3. Access-control tests

**File**: `households/tests/test_access_control.py`

**Intent**: Cover the PRD's hard guardrail. A cross-household leak here is a privacy breach,
not a bug, and it is the one failure in this slice that a smoke test returning 200 would
miss entirely.

**Contract**: Build two households with one member each. Cover: a member of household A
cannot reach household B's detail page; every protected URL redirects an anonymous user to
login; a logged-in user with no membership is redirected to `/household/create/` and not
into a loop; the decorator does not loop for any of anonymous, household-less, or
household-holding users; `request.user.membership.household` is the only household any view
resolves.

#### 4. Learning documentation

**File**: `docs/learning/<new docs>`, `docs/learning/_index.md`

**Intent**: This slice introduces five concepts `docs/learning/` did not cover — automated
testing, ORM models versus SQL DDL, sessions and how login persists across requests, Django
templates and CSS, and unguessable-token invites. The existing docs stopped at deployment.

**Already written (2026-08-05, ahead of implementation):**
`docs/learning/automated-testing-types-and-django-mechanics.md` covers the testing half —
the unit/integration/smoke/E2E ladder, what a green suite does and does not prove, and
Django's test runner, throwaway test database, and test client, mapped onto the four test
files this plan specifies. Do not re-write it; the remaining four concepts are still open.

**Contract**: Write the entries with the `concept-tutor` skill so they match the established
generic-versus-project-specific split and the analogies in
`docs/learning/_learner-profile.md`, then add rows to `docs/learning/_index.md`. Docs-only
changes are covered by the workflow's `paths-ignore`, so this can ship without triggering a
deploy.

### Success Criteria:

#### Automated Verification:

- Access-control tests pass: `uv run python manage.py test households.tests.test_access_control`
- Full suite passes: `uv run python manage.py test`
- Type checking passes: `uv run mypy .`
- System checks pass: `uv run python manage.py check`
- Migrations are complete: `uv run python manage.py makemigrations --check --dry-run`

#### Manual Verification:

- The empty list page reads sensibly in Polish at phone width
- No redirect loop for any of: anonymous, logged-in-without-household (the pre-existing superuser), logged-in-with-household
- `docs/learning/` entries written and indexed
- End-to-end run on the live URL: two accounts, one household, both members visible, list shell reachable by both

**Implementation Note**: After completing this phase and all automated verification passes,
pause here for manual confirmation from the human that the manual testing was successful.

---

## Testing Strategy

Coverage level is **comprehensive** by explicit decision — above the minimum for a two-user
MVP, justified by this being the slice every later slice trusts for access control.

### Unit Tests:

- Invite token generation, uniqueness, and regeneration semantics
- One-household-per-user enforced at the database level
- Email lowercase normalization on both the signup and login paths
- Cascade behavior: deleting a household removes memberships, not users

### Integration Tests:

- Signup → auto-created household → list shell, in one flow
- Invite link → anonymous signup → membership in the inviting household, with the session key cleared afterwards
- Regenerate → previously issued URL no longer joins
- Cross-household isolation: a member of A cannot read B
- Every protected URL redirects anonymous users to login

### Manual Testing Steps:

1. Sign up on the live Railway URL from a phone; confirm the page is readable without zooming.
2. Open `/household/`, copy the invite link, and confirm it carries the production host.
3. Open the link in a private window, sign up as a second user, and confirm both accounts list both members.
4. Log out and log back in using a differently-cased email — this exercises the Postgres case-sensitivity path that CI's SQLite cannot.
5. Regenerate the invite token and confirm the old link no longer works.
6. As the second user, click the *first* user's regenerated link and confirm a readable refusal, not a stack trace.

## Performance Considerations

Nothing in this slice is performance-sensitive at the target scale (`target_scale.users:
small` in the PRD). The one thing worth doing right the first time is the member list: render
it via `household.memberships.select_related('user')` so a household with N members costs one
query rather than N+1. The PRD's one-second acknowledgement NFR bites in S-02, not here.

## Migration Notes

One migration, in Phase 2, creating two tables. It touches no existing table and no existing
row, so it applies cleanly against the production database as it stands (one superuser, no
domain data).

The superuser predates this slice and will have **no** `Membership`. That is the concrete
reason `/household/create/` and the household-less branch of `household_required` exist. Do
not paper over it with a data migration that invents a household for the superuser — the
household-less path needs to work anyway, and a real user in that state is the best test of
it.

Rollback: reverting the merge and redeploying restores the previous image; the created tables
remain but are unreferenced and harmless. There is no destructive step in this slice.

## References

- Roadmap slice S-01: `context/foundation/roadmap.md:114-126`
- PRD user story US-02 and Access Control: `context/foundation/prd.md:51-61`, `prd.md:102-110`
- Deploy constraints (startCommand, replica pinning, restart policy): `context/deployment/deploy-plan.md:59-66`
- CI gate and the zero-tests gap: `.github/workflows/deploy.yml`, `context/deployment/deploy-plan.md:330-333`
- Existing type-hint style to match: `domowa_apteka/urls.py:22`
- SQLite/Postgres parity background: `docs/learning/database-migrations-and-dev-prod-parity.md`

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles. See `references/progress-format.md`.

### Phase 1: First app, UI shell, and type-checking

#### Automated

- [x] 1.1 Lockfile is in sync: `uv sync --locked` — 29e4d8e
- [x] 1.2 Django system checks pass with the new app installed: `uv run python manage.py check` — 29e4d8e
- [x] 1.3 Type checking passes: `uv run mypy .` — 29e4d8e
- [x] 1.4 Test suite still runs: `uv run python manage.py test` — 29e4d8e
- [x] 1.5 Static files collect, including the vendored stylesheet: `uv run python manage.py collectstatic --noinput` — 29e4d8e
- [x] 1.6 No model changes were made accidentally: `uv run python manage.py makemigrations --check --dry-run` — 29e4d8e

#### Manual

- [x] 1.7 Landing page renders at `/` with the stylesheet applied, readable at phone width without horizontal scrolling — 29e4d8e
- [x] 1.8 Final stylesheet chosen after browsing `cssbed.com` — 29e4d8e
- [x] 1.9 CI `check` job green on the PR, with the new mypy step visible in the log — 29e4d8e

### Phase 2: Household and Membership models

#### Automated

- [x] 2.1 Migration is complete and committed: `uv run python manage.py makemigrations --check --dry-run` — ef3bf43
- [x] 2.2 Migration applies cleanly from empty: `uv run python manage.py migrate` — ef3bf43
- [x] 2.3 Model tests pass: `uv run python manage.py test households.tests.test_models` — ef3bf43
- [x] 2.4 Type checking passes: `uv run mypy .` — ef3bf43

#### Manual

- [x] 2.5 `Household` and `Membership` visible and editable at `/admin/` — ef3bf43
- [x] 2.6 Production deploy green after merge — migration applied inside `startCommand` without a restart loop — ef3bf43

### Phase 3: Signup, login, logout

#### Automated

- [x] 3.1 Auth tests pass: `uv run python manage.py test households.tests.test_auth` — b37f7ec
- [x] 3.2 Full suite still passes: `uv run python manage.py test` — b37f7ec
- [x] 3.3 Type checking passes: `uv run mypy .` — b37f7ec
- [x] 3.4 System checks pass: `uv run python manage.py check` — b37f7ec

#### Manual

- [x] 3.5 Sign up on the live Railway URL from a phone and land on a signed-in page — b37f7ec
- [x] 3.6 Header shows signed-in email and household name; logout returns to the landing page — b37f7ec
- [x] 3.7 Polish diacritics render correctly and Django's own validation errors appear in Polish — b37f7ec
- [x] 3.8 Logging in with a differently-cased email succeeds against production Postgres — b37f7ec

### Phase 4: Invite link and join flow

#### Automated

- [x] 4.1 Invite tests pass: `uv run python manage.py test households.tests.test_invites` — e59318c
- [x] 4.2 Full suite passes: `uv run python manage.py test` — e59318c
- [x] 4.3 Type checking passes: `uv run mypy .` — e59318c
- [x] 4.4 No stray model changes: `uv run python manage.py makemigrations --check --dry-run` — e59318c

#### Manual

- [x] 4.5 Two-browser test on the live URL: both accounts show the same household with both members listed — e59318c
- [x] 4.6 The copied link contains the real production host — e59318c
- [x] 4.7 Regenerated token invalidates the previously copied URL — e59318c
- [x] 4.8 An already-in-a-household user clicking another invite sees a readable Polish message, not a stack trace — e59318c

### Phase 5: List shell and access-control hardening

#### Automated

- [x] 5.1 Access-control tests pass: `uv run python manage.py test households.tests.test_access_control` — 4a0690f
- [x] 5.2 Full suite passes: `uv run python manage.py test` — 4a0690f
- [x] 5.3 Type checking passes: `uv run mypy .` — 4a0690f
- [x] 5.4 System checks pass: `uv run python manage.py check` — 4a0690f
- [x] 5.5 Migrations are complete: `uv run python manage.py makemigrations --check --dry-run` — 4a0690f

#### Manual

- [x] 5.6 Empty list page reads sensibly in Polish at phone width — 4a0690f
- [x] 5.7 No redirect loop for anonymous, logged-in-without-household, or logged-in-with-household — 4a0690f
- [x] 5.8 `docs/learning/` entries written and indexed — 4a0690f
- [x] 5.9 End-to-end run on the live URL: two accounts, one household, both members visible, list shell reachable by both — 4a0690f
