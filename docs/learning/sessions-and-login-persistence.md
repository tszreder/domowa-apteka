---
title: "How does a login stay logged in? Sessions, and this project's invite-token stash"
slug: sessions-and-login-persistence
date: 2026-08-05
tags: [django, sessions, auth, web-fundamentals]
classification: mixed
prerequisites: [csrf-and-https-behind-a-proxy]
---

# How does a login stay logged in? Sessions, and this project's invite-token stash

## Why this came up

Phase 3 of `context/changes/household-accounts-and-invites/plan.md` wires up
`django.contrib.auth`'s `login()`/`logout()` views, and Phase 4's `join()` view in
`households/views.py` does something that only makes sense once you know how a login
"remembers" you between requests: an anonymous visitor who clicks an invite link has the
token written into `request.session`, gets sent to sign up, and the signup view later reads
that same value back out — across what are, from HTTP's point of view, two completely
unrelated requests.

## Builds on

[csrf-and-https-behind-a-proxy.md](csrf-and-https-behind-a-proxy.md) already introduced the
session cookie in passing ("your browser now holds a session cookie proving you're an admin")
while explaining the CSRF attack. This doc explains what that cookie actually *is* and how it
works — the CSRF doc assumed it, this one fills the gap.

## The concept, from the ground up

### The problem: HTTP has no memory

Every HTTP request is independent — the server that handles your login `POST` has no built-in
way to know that the very next `GET` to `/household/` came from the same browser. Nothing about
plain HTTP links two requests together. If you've ever wondered why a Databricks notebook cell
or an ADF pipeline run doesn't "remember" the previous cell's local variables once the session
ends — same root idea, one level removed: without something explicit carrying state across
calls, each call starts from nothing.

### The fix: a cookie holding one opaque key, and server-side storage behind it

A **cookie** is a small piece of data the server asks the browser to store, which the browser
then automatically resends on every later request to that same site. Django's session
framework uses exactly one cookie for this, `sessionid`, and deliberately puts almost nothing
in it — just a random-looking key. The actual data (which user is logged in, and anything else
your code stashes) lives server-side, in the `django_session` database table, keyed by that
same value. So: cookie → session key → server-side row → the actual data. This indirection
matters: if the cookie held the data itself (e.g. `user_id=42` in plain text), a user could
edit their own cookie and become anyone. Because the cookie only holds an opaque lookup key,
tampering with it just points at a different (or no) row — it can't forge someone else's
session data.

`request.session` in a Django view is the Python-side handle to that row: read it like a dict
(`request.session['key']`), write to it, and Django's `SessionMiddleware` (already in this
project's `MIDDLEWARE`) transparently saves it back to `django_session` at the end of the
request and ensures the `sessionid` cookie is set on the response.

### `login()` and `logout()` are just two particular writes to that same session

`django.contrib.auth.login(request, user)` — called from `households/views.py`'s `signup()`
view after a successful signup — doesn't do anything magical beyond writing the authenticated
user's ID into that same session dict (under a Django-managed key), and rotating the session
key itself (a deliberate security measure: a session ID that existed *before* login is never
trusted *after* login, closing a fixation attack where an attacker sets a victim's session ID
before they authenticate). `AuthenticationMiddleware` then reads that stored ID back out on
every subsequent request and attaches the matching `User` object as `request.user`, which is
how `{% if user.is_authenticated %}` in `templates/base.html` knows who's signed in without
your view code ever touching the session directly. `logout()` is the mirror image: it clears
that data and rotates the session key again.

### This project's own use of the same mechanism: stashing the invite token

`households/views.py` defines `INVITE_TOKEN_SESSION_KEY = 'invite_token'` and uses the exact
same `request.session` dict for something that has nothing to do with authentication:

```python
def join(request: HttpRequest, token: str) -> HttpResponse:
    household = get_object_or_404(Household, invite_token=token)
    if not request.user.is_authenticated:
        request.session[INVITE_TOKEN_SESSION_KEY] = token
        return redirect('households:signup')
    ...
```

An anonymous visitor hits `/join/<token>/`. The view can't create a `Membership` yet — there's
no account to attach one to — so it writes the token into the session (request 1) and redirects
to `/signup/`. When that same browser later `POST`s the signup form (request 2, a genuinely
separate HTTP request, but the same `sessionid` cookie rides along automatically), `signup()`
reads it back:

```python
invite_token = request.session.pop(INVITE_TOKEN_SESSION_KEY, None)
```

`.pop()` rather than a plain read is deliberate and is called out explicitly in the plan's
"Critical Implementation Details": it both reads *and clears* the value in one step. If
`signup()` only read it, a user who abandons the signup form and comes back later — or anyone
sharing that browser — would silently join the stashed household on their *next* signup,
because the value would still be sitting in the session. Clearing it on read means the stash is
genuinely one-shot, matching what the UI implies: "this invite gets consumed by the signup that
follows it, not by whichever signup happens next."

## In terms you already know

| This project's concept | What it's like in your world |
| --- | --- |
| A session (cookie holds a key, real data stored server-side) | Closer to a **Power BI Service report session / dataset refresh context** than a cookie holding data directly — the browser holds a small token, the actual state (filters applied, who's viewing) lives server-side, looked up by that token. |
| `request.session` as a per-visitor dict that survives across requests | A **Databricks notebook's cluster-scoped state while the cluster stays "Running"** — each new command (request) can read what an earlier command (request) wrote, as long as the same cluster (session) is still up. |
| Session data expiring / getting cleared | A **cluster auto-terminating after inactivity** — once gone, the next command starts from nothing, same as a browser with an expired or cleared session cookie. |
| `request.session.pop(key, None)` — read once, then gone | A **queue message you explicitly acknowledge and remove after processing** (Service Bus/Event Hub semantics), rather than a value you'd leave sitting in a shared table for the next unrelated run to accidentally pick up. |

## What's universal vs. what's specific to this project's choices

**True for any web app that needs to "remember" a visitor across requests:**
- HTTP itself is stateless; every framework needs *some* mechanism to link requests from the
  same browser — a cookie holding an opaque session key is the standard approach across
  virtually every web stack (PHP sessions, Rails, Express + `express-session`, ASP.NET Core).
- Storing the actual data server-side, with the cookie holding only a lookup key, is the safe
  default — it's what stops a client-editable cookie from being able to forge session contents.
- Session fixation (rotating the session ID at login) is a known, general class of attack every
  session-based auth system needs to defend against, not a Django-specific concern.

**Specific because this project picked Django's session framework:**
- The `django_session` table, `SessionMiddleware`, and the `request.session` dict-like API are
  Django's own implementation of the general pattern above — a Node/Express app would use
  `express-session` with a different storage backend (Redis, in this project's case SQLite/
  Postgres via Django's own DB-backed session engine, the default).
- Using the session for something other than auth state — this project's invite-token stash —
  is an application choice, not something Django prescribes; `request.session` is a general-
  purpose per-visitor store and this project uses it for exactly one non-auth value.
- `login()`'s automatic session-key rotation on authentication is Django's built-in fixation
  defense; a hand-rolled session system would need to implement that rotation itself.

## Go deeper

- [How Sessions Work — web.dev / general web explainer](https://developer.mozilla.org/en-US/docs/Web/HTTP/Cookies) —
  MDN's cookie reference, the mechanism sessions are built on, explained without assuming prior
  web-dev background.
- [Django official docs: How to use sessions](https://docs.djangoproject.com/en/5.2/topics/http/sessions/) —
  the authoritative reference for `request.session`, session engines, and expiry configuration.

## Quick recap

**Q: What does the `sessionid` cookie actually contain?**
A: Just an opaque lookup key — not the logged-in user's identity or any other data directly.
The real data lives server-side in the `django_session` table, keyed by that value.

**Q: Why not just put `user_id=42` straight in the cookie instead of a lookup key?**
A: A cookie is stored and editable on the visitor's own machine. If it held the data directly,
editing it would let someone claim to be any user; an opaque key pointing at server-side data
can't be forged that way.

**Q: What does `django.contrib.auth.login(request, user)` actually do?**
A: Writes the user's ID into `request.session` (using a Django-managed key) and rotates the
session key itself, so any session ID that existed before authentication is never trusted
afterward.

**Q: Why does this project's `signup()` view use `request.session.pop(...)` instead of just reading the invite token?**
A: `.pop()` reads and clears in one step. A plain read would leave the stashed token sitting in
the session, so a later, unrelated signup from the same browser could silently join a household
nobody meant it to.

**Q: When would you reach for `request.session` for something that isn't authentication?**
A: Whenever you need a value to survive from one request to a *specific* later request from the
same visitor, without a database row to attach it to yet — exactly this project's case: the
invite token exists before there's a `User` row to attach a `Membership` to.
