# Household Accounts and Invites — Plan Brief

> Full plan: `context/changes/household-accounts-and-invites/plan.md`

## What & Why

Roadmap slice **S-01**. An adult signs up, gets a household, shares an invite link over any
messenger, and a second adult joins through it with full symmetric access to the same shared
list. Nothing else in the product can ship without it — the north star slice (S-02) has
nowhere to publish an item until a shared household exists.

## Starting Point

A production-deployed Django scaffold with zero application code: no apps, no models, no
templates, no user-facing views. `django.contrib.auth` is wired and proven (a superuser
exists and `/admin/` login works over HTTPS), but the entire user-facing half is missing.
Two facts from the existing deploy constrain the design: `auth`'s tables are already live in
production Postgres, and there is no email backend configured anywhere.

## Desired End State

Two people, on their phones, each hold an account and share one household. Each sees the
other in a member list, both reach the same (empty, until S-02) shared list page, and the
invite link can be revoked by regenerating it. No user can reach another household's data.

## Key Decisions Made

| Decision | Choice | Why |
| --- | --- | --- |
| User model | Stock `auth.User`, lowercased email in `username` | `auth` tables are already live in production — swapping `AUTH_USER_MODEL` now would mean recreating the database, for cosmetics nothing in the PRD needs |
| Household membership | Exactly one per user, via `OneToOneField` | Makes `request.user.membership.household` unambiguous for every later slice, and the database enforces it rather than view code |
| Invite lifetime | One standing token per household, regenerate to revoke | Matches how a link pasted into a messenger actually gets used; revocation is one overwrite with no expiry or clock-skew logic |
| Auth mechanism | Email + password, open signup | No `EMAIL_*` config exists, so passwordless would mean adding a mail provider, dependency, and secret — real work outside this slice |
| No-household state | Auto-create at signup, *unless* signing up via an invite | The two paths never overlap, so an invited user never arrives already in a household needing to be moved or deleted |
| Invite form | URL carrying an unguessable token | Tap to join; no typing on a phone keyboard, no ambiguous-character handling |
| Styling | Vendored classless CSS (Pico default) | Phone-usable with no build step; since templates carry no CSS classes the stylesheet stays a one-file swap |
| UI language | Polish, with `LANGUAGE_CODE = 'pl'` | The users are a Polish household, and the locale switch makes Django's own validation messages Polish too |
| Test depth | Comprehensive | Above the minimum by explicit choice — this is the slice every later slice trusts for access control |
| Type checking | mypy + django-stubs wired into CI now | `tech-stack.md` promises the convention "once apps exist"; this is that moment, and retrofitting across many apps is harder |

## Scope

**In scope:** signup / login / logout · household model with standing invite token ·
invite link, join flow, and regenerate-to-revoke · member list · signed-in header ·
empty shared-list shell · `household_required` decorator · comprehensive tests ·
mypy in CI · `docs/learning/` entries for the new concepts

**Out of scope:** password reset, email verification, anything sending mail · removing a
member, leaving, deleting, or renaming a household · multiple households or a switcher ·
invite expiry or per-invitee tokens · rate limiting · any pharmaceutical or list-item model
(S-02 owns those)

## Architecture / Approach

One new Django app, `households`, owning both the account surface and the household model —
in this product an account exists only to be a member of a household, so splitting them would
create an app with three views and no models. The one-household rule is enforced by the
database (`Membership.user` is a `OneToOneField`), not by application code. The
auto-create-unless-invited rule works by having `/join/<token>/` stash the token in the
session when hit anonymously; the signup view then pops it and either joins the named
household or creates a fresh one.

## Phases at a Glance

| Phase | What it delivers | Key risk |
| --- | --- | --- |
| 1. App, UI shell, type-checking | `households` app, `base.html`, vendored CSS, mypy in CI | django-stubs config is fiddly and can eat an evening before any feature exists |
| 2. Models | `Household` + `Membership`, one additive migration, admin | `migrate` runs in `startCommand` — a bad migration is a restart loop, not an error |
| 3. Signup / login / logout | Account surface, auto-created household, header | Email case normalization must happen on both write and read; CI's SQLite cannot catch a miss |
| 4. Invite and join | Shareable link, member list, regenerate, join state machine | Three arrival states must all be handled; a stale session token silently joins the wrong household |
| 5. List shell and hardening | Empty list page, `household_required`, isolation tests | Redirect loops; a cross-household leak here is a privacy breach, not a bug |

**Prerequisites:** None. S-01 has no roadmap prerequisites and can run in parallel with F-01.
**Estimated effort:** ~5 sessions, one PR per phase. Each phase is independently deployable.

## Open Risks & Assumptions

- The pre-existing superuser has no `Membership` and never will — the household-less code
  path must work rather than being papered over with a data migration.
- Open signup means a stranger can create an account on the public Railway URL. They see
  nothing (their own empty household), but there is no rate limiting in v1.
- A leaked invite link stays valid until someone regenerates it. Accepted for a two-adult
  household; not acceptable if this ever becomes a public product.
- Assumes `uv sync --locked` in CI installs the dev group so mypy is available, while
  Railway's `--no-dev` build keeps it out of production. Phase 1 de-risks this by adding and
  running mypy locally as its opening move, before any app code exists.

## Success Criteria (Summary)

- Two people on two phones end up in one household via a link shared through a messenger,
  each able to see the other listed.
- Regenerating the invite makes the previously shared link stop working, without disturbing
  anyone already joined.
- A member of one household cannot reach another household's data — proven by test, not by
  inspection.
