---
title: "Automated testing: what tests prove, the four kinds, and how Django runs them"
slug: automated-testing-types-and-django-mechanics
date: 2026-08-05
tags: [testing, django, ci-cd, quality, web-fundamentals]
classification: mixed
prerequisites: [ci-cd-and-deploy-triggers, database-migrations-and-dev-prod-parity, from-dev-scaffold-to-production-ready]
---

# Automated testing: what tests prove, the four kinds, and how Django runs them

## Why this came up

`.github/workflows/deploy.yml` already runs `uv run python manage.py test` on every pull
request — and it currently finds **zero tests**, which the deploy plan flags openly:
"`manage.py test` finds 0 tests, so today the only real signals are lockfile sync and
Django's system checks." The plan for `household-accounts-and-invites` is the first change
that fills that gap, and it commits to *comprehensive* coverage across four test files.
Deciding whether that was the right call — and reading those files later without guessing —
means knowing what each kind of test actually buys you.

## Builds on

- See [ci-cd-and-deploy-triggers.md](ci-cd-and-deploy-triggers.md) for what the `check` job
  is and why it runs on the PR rather than after the merge.
- See [database-migrations-and-dev-prod-parity.md](database-migrations-and-dev-prod-parity.md)
  for why CI runs against SQLite while production runs Postgres — that gap shows up again
  below, and it is the single most important limit on what a green test suite proves.
- See [from-dev-scaffold-to-production-ready.md](from-dev-scaffold-to-production-ready.md)
  for `manage.py check --deploy`, the *static* audit that sits next to tests in the same CI
  job but answers a completely different question.

## The concept, from the ground up

### Why bother, honestly

The usual answer — "tests improve quality" — is too vague to act on. The concrete answer is
about **change over time**.

You will verify by hand that login works when you build it in Phase 3. Then in Phase 5 you
add a `household_required` guard in front of several views. Does login still work? You
believe so. Are you going to manually re-run signup, login, logout, invite, join, and the
member list on a phone, at 22:30, to be sure? For five phases? Every time?

That is what a test suite is: **the accumulated memory of every manual check you have
already done**, replayed in two seconds instead of twenty minutes. It is worth the most
precisely in the situation this project is in — one person, working in short evening
sessions, with gaps of days between them, where "I remember verifying that" is doing far
more work than it can bear.

The second reason is specific to how this repo deploys. Merging to `main` ships to
production with no human in the loop. The tests in the `check` job are the last thing that
can say "no" before real users see the result.

### What a test actually is

Three steps, always:

1. **Arrange** — build a known starting state (create a user, create a household).
2. **Act** — do the thing (send a request to `/join/<token>/`).
3. **Assert** — declare what must now be true (`the user has exactly one membership`).

An **assertion** is a statement that must hold; if it doesn't, the test fails loudly and the
run stops being green. This is the same idea as a data-quality expectation in a pipeline —
you are not asking "what happened?", you are declaring "this must be true" and demanding to
be told when it isn't.

### Tests are not the only check, and not the same as static checks

The CI `check` job runs three different kinds of thing, and it is worth not confusing them:

| Command | What it does | Analogy |
| --- | --- | --- |
| `uv sync --locked` | Verifies the dependency lockfile matches the manifest | A cluster policy check — did anyone install something off-policy? |
| `manage.py check` / `check --deploy` | **Reads** code and config, flags known pitfalls. Never executes your logic. | BPA rules over a model before publish |
| `manage.py test` | **Executes** your code against a real (throwaway) database | An actual pipeline debug run |

A static check can tell you `SECURE_SSL_REDIRECT` is off. Only a test can tell you that a
member of one household can read another household's data.

### The four kinds of test

The categories differ by **how much of the system is inside the test's scope**. More scope
means more realism and also more slowness, more fragility, and vaguer failures.

**Unit test** — one function, method, or model, in isolation. In this project:
`regenerate_invite_token()` produces a value different from the previous one. Runs in
milliseconds. When it fails you know exactly which line to open.

**Integration test** — several pieces wired together, hitting a real database. In this
project: a POST to `/signup/` results in a `User`, a `Household`, **and** a `Membership`,
all three, in one request. No individual unit test would catch it if the view forgot to
create the membership — each part works, the wiring doesn't.

**Smoke test** — shallow but broad: does it respond at all? "Every URL returns something
that isn't a 500." Cheap, and catches whole categories of stupidity (a typo'd template
name, a broken import) in one sweep. It proves almost nothing about correctness.

**End-to-end (E2E) test** — the whole system, driven the way a person drives it, usually
through a real browser. This project has E2E steps, but performed **by hand**: the
two-browser manual check in Phase 4 where you copy an invite link into a private window and
confirm both accounts see each other. That is a genuine end-to-end test; it just has a human
as the test runner. Automating browser tests (Selenium, Playwright) is deliberately out of
scope here.

### Why the shape is a pyramid

The standard advice is many unit tests, fewer integration tests, very few E2E tests:

```
        /\        E2E — few, slow, brittle, but closest to reality
       /  \
      /    \      Integration — moderate count, real DB, tests the wiring
     /      \
    /________\    Unit — many, fast, precise
```

The reason is failure *diagnosis*, not just speed. When an E2E test goes red it tells you
"something in the signup-to-join journey broke" — you still have to go find it. When a unit
test goes red it tells you which method. A suite made entirely of E2E tests is slow enough
that you stop running it, and vague enough that you dread it when you do.

"Flaky" is the word for the specific misery E2E tests are prone to: a test that passes and
fails on identical code, usually because of timing — the browser hadn't finished rendering
when the assertion ran. Flaky tests are worse than no tests, because they train you to
ignore red.

### Where regression tests fit — a different axis, not a fifth kind

The four categories above classify a test by **scope**. "Regression test" classifies by
**why the test exists**. Those axes are independent, so any test at any scope can also be a
regression test — there is no such thing as "a regression instead of a unit test."

The term carries two distinct meanings, and conflating them is what makes it feel like a
missing category:

**Regression testing, the activity.** Re-running your existing suite to confirm that new
work didn't break old behavior. In this sense your *whole suite is* the regression suite —
not because of what's in it, but because you re-run it. This is precisely the "accumulated
memory of manual checks" idea from the top of this doc.

**A regression test, the artifact.** One test written in response to one specific bug, to
pin it shut permanently. The workflow is always the same: bug appears → write a test that
*fails*, reproducing it → fix the code → the test goes green → it lives in the suite
forever, guarding a door that is now known to swing open.

That second kind is the highest-value test you can write, for a reason worth internalizing:
every test written up front is **speculative** — an educated guess about what might break. A
regression test is **proven** — something did break, here, once, and you have hard evidence
this path is fragile. Speculative tests guard against failures that may never occur.

**Where they go in this project: into the existing files, by concern.** A bug in the invite
link produces a test in `test_invites.py`, sitting alongside the speculative ones. Do *not*
create a `test_regressions.py` — organizing by history rather than by subject means that six
months later nobody can find the tests relevant to the code they're about to change.

Note that this project has **zero** regression tests today and cannot have any: there is no
app code, so there is no bug history. All four planned files are entirely speculative. That
is normal for greenfield. Regression tests accumulate as a byproduct of things going wrong,
and in a year they will likely be the most trustworthy tests in the suite.

### What tests cannot do

**They only check what you assert.** This is the trap the plan calls out explicitly: a view
that leaks another household's data still returns HTTP 200. A smoke test asserting `200`
passes happily while a privacy breach ships. That is precisely why
`test_access_control.py` exists as a separate file asserting on *what the response
contains and who is allowed to see it*, not on status codes.

**A green suite does not mean production is correct.** CI runs on SQLite; production is
Postgres. The clearest example is live in this very plan: a `unique=True` text column is
case-sensitive on Postgres but effectively case-insensitive on SQLite. Store `Alice@x.com`,
log in as `alice@x.com` — on SQLite it works and every test is green; on Postgres it fails.
No amount of test-writing closes that gap. Only running against the same engine does, and
this project accepts the gap knowingly (see the parity doc above).

**They cannot prove the absence of bugs.** They prove that the specific things you thought
to check are still true. That is genuinely valuable and genuinely limited.

## Django mechanics

Everything above is universal. Here is how Django in particular does it.

### Where tests live and how they're found

`startapp` gives every app a `tests.py`. The runner finds any file matching `test*.py`
anywhere under the app and any method named `test_*` inside a `TestCase` class — **discovery
is by naming convention, not registration**. You never list your tests anywhere.

Once there is more than a handful, `tests.py` becomes a `tests/` package (a directory with
`__init__.py`), which is what this plan does:

```
households/tests/__init__.py
households/tests/test_models.py
households/tests/test_auth.py
households/tests/test_invites.py
households/tests/test_access_control.py
```

### The throwaway test database — the part that surprises people

`django.test.TestCase` **creates an entirely separate database** for the test run, applies
all migrations to it, runs the tests, and destroys it at the end. Your `db.sqlite3` dev file
is never touched, and production is never in the picture at all.

Better still, each individual test method runs inside a **database transaction** — a unit of
work the database can undo wholesale — which is rolled back the moment the method ends. So
every test starts from an identical clean slate regardless of what the test before it
created. You never write cleanup code.

This is also why a Django "unit" test isn't really a unit test in the purist sense: it has a
live database underneath it. That's a pragmatic trade the framework makes, and it's fine —
just don't be confused when the categories above don't map perfectly onto the file names.

### The test client — a fake browser

`self.client` sends requests without any server running and without real network:

- `self.client.get('/list/')`
- `self.client.post('/signup/', {'username': 'a@x.com', 'password1': '...'})`
- `self.client.force_login(user)` — skip the login form when the test is about something else

It returns a normal response object you can assert against: `response.status_code`,
`response.context`, `response.content`.

### Useful assertions

`assertEqual`, `assertTrue` — general purpose. `assertRedirects(response, '/login/')` —
checks the redirect target *and* that the target itself works. `assertContains(response,
'text')` — checks status and body together. `assertRaises(IntegrityError)` — for the
one-household-per-user constraint, where the *failure* is the expected outcome.

### Running them

```bash
uv run python manage.py test                              # everything
uv run python manage.py test households.tests.test_auth   # one file
uv run python manage.py test -v 2                         # name each test as it runs
```

### One project-specific gotcha

This plan sets `LANGUAGE_CODE = 'pl'`, which makes Django's own validation messages Polish.
So tests must assert on **form error keys and codes** (`form.errors['username']`), never on
rendered message text — otherwise the suite breaks when Django updates a translation, and
the failure has nothing to do with your code.

### What the four planned files each prove

| File | Mostly | Proves |
| --- | --- | --- |
| `test_models.py` | Unit | Invite tokens are unique and regenerable; one household per user is enforced *by the database*; deleting a household doesn't delete users |
| `test_auth.py` | Integration | Signup creates user + household + membership together; email case is normalized on both signup and login |
| `test_invites.py` | Integration | The join flow handles all three arrival states; the session token is cleared; a regenerated token kills the old link |
| `test_access_control.py` | Integration | One household cannot read another's data; anonymous users are redirected; no redirect loops |

The split is by *concern*, not by test type — that's the normal convention, and it's why a
file named for a feature contains a mix of unit and integration tests.

## In terms you already know

| This project's concept | What it's like in your world |
| --- | --- |
| An **assertion** | A **data-quality expectation** on a load — declares what must be true and fails the run loudly when it isn't, rather than reporting what happened |
| **Unit test** | Validating a single **DAX measure or transformation function** against a tiny hand-built input table — no pipeline, no source systems |
| **Integration test** | An **ADF pipeline debug run** end-to-end against dev linked services — several activities wired together, real connections |
| **Smoke test** | A **"does it run at all" debug run over a tiny sample** before committing to the full load |
| **End-to-end test** | **UAT against the published report** in the real workspace, driven the way a consumer drives it |
| The **throwaway test database** (built, migrated, destroyed per run) | A **scratch schema spun up for a validation run and dropped afterwards** — never the dev or prod store |
| **Per-test transaction rollback** | An ADF debug run against a **sandbox that resets between runs**, so run order never matters |
| **Discovery by naming convention** (`test*.py`) | `adf_publish` **picking up everything in the declared folders** — the layout is the registration; you never enumerate items by hand |
| A **flaky test** | An **intermittently failing pipeline** whose failures are timing, not logic — it trains everyone to re-run instead of investigate |
| **`manage.py check`** (static) vs **`manage.py test`** (executes) | **BPA rules over a model** vs. **actually running the refresh** |

## What's universal vs. what's specific to this project's choices

**True for any codebase, any language, any platform:**

- The arrange / act / assert shape of a test.
- The unit → integration → smoke → E2E scope ladder, and the pyramid trade-off between
  realism and diagnosability.
- Tests only check what you assert — a 200 status proves the page rendered, never that it
  rendered the *right* thing to the *right* person.
- Tests are how you make change safe over time; their value scales with how long the project
  lives and how long the gaps between your sessions are.
- A test suite that passes against a different database engine than production does not
  prove production behavior.

**Specific because this project picked Django (and Django's built-in runner):**

- `manage.py test` is the runner, discovering `test*.py` by convention. The common
  alternative in Python is **pytest**, with `pytest-django` — more concise syntax, better
  failure output, and a plugin ecosystem. This project deliberately uses the built-in runner
  (`AGENTS.md`: "no pytest config present") because it is one less dependency for an MVP.
- `django.test.TestCase` handing you a migrated throwaway database and wrapping each test in
  a rolled-back transaction is a Django convenience, not a law of testing. In many stacks you
  build and tear down test data yourself.
- The test client (`self.client`) is Django's in-process fake browser. Other frameworks have
  equivalents (Flask's `test_client`, FastAPI's `TestClient`); the idea is portable, the API
  is not.
- Asserting on error *codes* rather than message text matters here because
  `LANGUAGE_CODE = 'pl'` translates Django's built-in messages. In an English-only app the
  temptation to assert on text is less immediately punishing — still a bad habit.

## Go deeper

- [The Practical Test Pyramid — Ham Vocke (martinfowler.com)](https://martinfowler.com/articles/practical-test-pyramid.html)
  — the canonical explanation of the scope ladder and why the shape matters. Long, but the
  first third alone is worth it and assumes no framework knowledge.
- [Writing your first Django app, part 5 — "Introducing automated testing"](https://docs.djangoproject.com/en/5.2/intro/tutorial05/)
  — starts from "what even is an automated test" and builds one against a real bug. Written
  for people new to testing, not new to Django only.
- [Django: Testing overview](https://docs.djangoproject.com/en/5.2/topics/testing/) — the
  authoritative reference for `TestCase`, the test client, and the full assertion list.

## Quick recap

**Q: What is the difference between `manage.py check` and `manage.py test`?**
A: `check` reads your code and configuration and flags known pitfalls without running
anything — a static audit, like BPA rules over a model. `test` actually executes your code
against a throwaway database. Both run in the same CI job and answer different questions.

**Q: Why not just write end-to-end tests, since they're the most realistic?**
A: They're slow, prone to flaky timing failures, and when one goes red it tells you *that*
something broke in a long journey, not *what*. A suite of only E2E tests gets slow enough
that you stop running it and vague enough that you dread it — hence the pyramid.

**Q: A test asserts that a page returns HTTP 200 and it passes. What might still be badly wrong?**
A: Anything about the *content*. A view leaking another household's private data returns a
perfectly cheerful 200. That's the reason this plan has a dedicated access-control test file
asserting on who can see what, rather than trusting status codes.

**Q: Does a fully green test suite mean the code is correct in production?**
A: No. CI here runs on SQLite and production runs Postgres, so any behavior that differs
between engines — text case-sensitivity on a unique column being the live example — can be
green in CI and broken in production. Tests prove the things you thought to assert, on the
environment you ran them in.

**Q: You're about to add a guard in front of six existing views. Which kind of test do you most want to already have, and why?**
A: Integration tests over those views' existing behavior. A unit test of the guard proves the
guard's own logic; only an integration test proves you didn't break the six flows that were
working yesterday — which is exactly the "memory of manual checks" the suite exists to be.
