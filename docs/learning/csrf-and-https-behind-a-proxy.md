---
title: "What is CSRF, and why does it break behind a proxy? (CSRF_TRUSTED_ORIGINS and SECURE_PROXY_SSL_HEADER)"
slug: csrf-and-https-behind-a-proxy
date: 2026-08-01
tags: [security, deployment, django, web-fundamentals]
classification: mixed
prerequisites: [config-in-dev-vs-prod, from-dev-scaffold-to-production-ready]
---

# What is CSRF, and why does it break behind a proxy?

## Why this came up

Phase 0 of `context/changes/deployment/deployment-plan.md` adds two settings —
`SECURE_PROXY_SSL_HEADER` and `CSRF_TRUSTED_ORIGINS` — with the note that they're "needed
because end-to-end verification in Phase 4 is *log into `/admin/`* over HTTPS behind
Railway's TLS terminator." It also imposes an ordering constraint: `CSRF_TRUSTED_ORIGINS`
can't be set until *after* the first deploy, because the domain doesn't exist yet. That's
two unfamiliar concepts and a chicken-and-egg problem in one checkbox.

The practical stake: without these, you deploy successfully, open `/admin/`, type your
password, hit Log in, and get **"CSRF verification failed. Request aborted."** — with the
app otherwise working perfectly.

## Builds on

- [config-in-dev-vs-prod.md](config-in-dev-vs-prod.md) — `SECRET_KEY` is what signs the CSRF
  token, and `CSRF_TRUSTED_ORIGINS` follows the same env-var pattern (including the
  `"".split(",")` wart).

## The concept, from the ground up

### The attack, before the defence

Start with a browser behaviour that seems helpful and is the root of the whole problem:

**A browser attaches a site's cookies to every request aimed at that site — regardless of
which page triggered the request.**

So: you log into `https://domowa-apteka.example/admin/`. Your browser now holds a session
cookie proving you're an admin. Later, in another tab, you open some unrelated site that
contains this:

```html
<form action="https://domowa-apteka.example/admin/auth/user/1/delete/" method="post">
<script>document.forms[0].submit()</script>
```

The browser sends that POST **and attaches your session cookie**, because it's a request to
`domowa-apteka.example` and that's what browsers do. Your server sees a properly
authenticated admin request and obeys it. You never clicked anything on your own site.

That's **Cross-Site Request Forgery**: the attacker never steals your credentials, they just
get *your browser* to use them. It's the confused-deputy problem — an authority (the browser)
acting on someone else's instruction with its own privileges attached.

### Defence 1: a token the attacker can't read

Since the attacker can make your browser *send* requests but cannot *read* responses from
your site (a separate browser rule, the same-origin policy), the fix is to require something
in the request that could only have come from reading a page on your site.

Django does this: every form it renders includes a hidden `csrfmiddlewaretoken` field, and
`CsrfViewMiddleware` (already in your `settings.py:46`, on line 5 of `MIDDLEWARE`) rejects
any POST that doesn't carry a matching one. The attacker's form can't include a valid token
because their JavaScript can't read your page to extract it. The token is signed with
`SECRET_KEY` — which is why a leaked secret key undermines this too.

You've never noticed this locally because Django's own admin templates include the token
automatically and the check passes silently.

### Defence 2: checking where the request claims to come from

Django adds a second, independent check for HTTPS requests. Browsers attach an `Origin`
header saying which site initiated the request, and Django compares it against the host it
thinks it's serving. A mismatch is rejected before the token is even considered.

`CSRF_TRUSTED_ORIGINS` is the allow-list for that check: a list of full origins **including
the scheme**, e.g. `https://domowa-apteka.up.railway.app`. It exists for cases where the
origin legitimately isn't the same as the serving host — and, critically for you, for cases
where Django has been *misled* about what host and scheme it's serving under. Which brings
us to the proxy.

### The proxy problem: Django thinks it's serving plain HTTP

On Railway (and Fly, Render, App Service, anything behind a load balancer), your app does not
receive HTTPS traffic. The chain is:

```
Browser --HTTPS--> Railway's edge/TLS terminator --plain HTTP--> gunicorn --> Django
```

Railway decrypts TLS at its edge and forwards a plain HTTP request internally. This is called
**TLS termination**, and it's normal and desirable — certificate management is the platform's
job, and the internal hop is inside their network.

But Django, looking at the request it actually received, concludes: *this is an HTTP request*.
So `request.is_secure()` returns `False`, and when it compares the browser's
`Origin: https://your-domain` against its own idea of `http://your-domain`, the schemes don't
match → CSRF rejected.

The proxy does leave evidence: it sets an `X-Forwarded-Proto: https` header recording the
original scheme. `SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")` tells Django
*trust that header — if it says https, treat the request as secure.*

**Why isn't that just the default?** Because a header is only trustworthy if something you
control set it. If your app were reachable directly, an attacker could send
`X-Forwarded-Proto: https` on a plain HTTP request and Django would believe it — defeating
HTTPS redirects and secure-cookie handling. Django makes you opt in, deliberately, once you
know a trusted proxy is genuinely in front. On Railway it is.

### One error message, two causes

This is the thing worth memorizing, because both failures print **"CSRF verification failed"**:

| Cause | What's actually wrong | Fix |
| --- | --- | --- |
| Origin/scheme mismatch from TLS termination | Django thinks it's on `http://`, browser says `https://` | `SECURE_PROXY_SSL_HEADER` |
| Origin host not in the allow-list | Django sees `https://` correctly but doesn't recognize the domain | `CSRF_TRUSTED_ORIGINS` |

The plan sets both, which is right — you can't easily tell them apart from the error page.

### Why the ordering constraint exists

`CSRF_TRUSTED_ORIGINS` must contain your actual domain, and Railway doesn't generate one until
after the first successful deploy. So the sequence is necessarily:

1. Deploy without it (Phase 4) → `/health/` works, since a GET with no form has nothing to
   verify.
2. Generate the domain.
3. Set `CSRF_TRUSTED_ORIGINS=https://<that-domain>` as an env variable and redeploy.
4. *Now* test admin login.

Guessing the domain in advance and hardcoding it just moves the failure later, when nobody's
looking for it. And note the scheme is mandatory — a bare hostname trips Django's `4_0.E001`
system check, which is also what a stray `[""]` from `"".split(",")` will do if you don't
filter empty strings out.

## In terms you already know

| This project's concept | What it's like in your world |
| --- | --- |
| CSRF (browser auto-attaching credentials to any request) | A **Logic App with a managed identity** that anyone able to trigger it can effectively borrow — the identity is attached automatically, so the ability to *invoke* becomes the ability to *act as*. Confused deputy, exactly. |
| The CSRF token | A **correlation/nonce value the caller must echo back**, issued only to someone who actually read your page — proof of "you came through the front door," separate from proof of identity. |
| `SECRET_KEY` signing that token | The **SAS/embed-token signing key** already mapped in [config-in-dev-vs-prod.md](config-in-dev-vs-prod.md) — same key, so the same leak breaks both session cookies and CSRF tokens. |
| TLS termination at Railway's edge | **Azure Front Door / Application Gateway terminating SSL** in front of an App Service — the backend receives plain HTTP inside the trusted network and has to be told the original request was HTTPS. |
| `X-Forwarded-Proto` and having to opt into trusting it | Trusting a **client-supplied header** in general: fine when a gateway you control is guaranteed to overwrite it, dangerous the moment the backend is reachable directly. |
| `CSRF_TRUSTED_ORIGINS` | A **CORS / reply-URL allow-list on an app registration** — an explicit list of the origins permitted to interact, checked before anything else happens. |

## What's universal vs. specific to this project's choices

**True for any web app on any platform:**
- CSRF is a browser-behaviour problem, not a framework problem — every framework that uses
  cookie-based sessions needs a defence (ASP.NET antiforgery tokens, Rails'
  `protect_from_forgery`, Express's `csurf`).
- TLS termination at an edge proxy, with the original scheme preserved only in an
  `X-Forwarded-*` header, is how essentially every managed platform works.
- "Don't trust a forwarded header unless a proxy you control sets it" is a general security
  principle.
- Cookie-based sessions are what make CSRF applicable at all. A pure token-in-a-header API
  (where the browser doesn't attach credentials automatically) has a different threat model.

**Specific because this project picked Django + Railway:**
- The setting names, the `CsrfViewMiddleware` in `MIDDLEWARE`, and the requirement that
  `CSRF_TRUSTED_ORIGINS` entries include a scheme are Django's.
- Django's opt-in `SECURE_PROXY_SSL_HEADER` is a deliberate design choice; some frameworks
  auto-detect common proxy headers, trading a little safety for less configuration.
- The "domain doesn't exist until after the first deploy" ordering problem comes from
  Railway generating the domain post-deploy. On a platform where you attach a domain up front,
  you'd set this in one pass.

## Go deeper

- [Cross Site Request Forgery (CSRF) — OWASP](https://owasp.org/www-community/attacks/csrf) —
  the attack explained from the attacker's side first, which is the order that makes the
  defence obvious.
- [Cross Site Request Forgery protection — Django official docs](https://docs.djangoproject.com/en/5.2/ref/csrf/)
  and [HTTPS behind a proxy / `SECURE_PROXY_SSL_HEADER`](https://docs.djangoproject.com/en/5.2/ref/settings/#secure-proxy-ssl-header) —
  the second one includes the explicit warning about when trusting the header is unsafe.

## Quick recap

**Q: What is CSRF, in one sentence?**
A: An attacker's page causes *your* logged-in browser to send a request to your site, and the
browser helpfully attaches your session cookie — so the server sees a legitimate authenticated
request you never intended.

**Q: How does a token stop it if the attacker can already send requests?**
A: The attacker can make your browser send requests but can't read your site's pages, so they
can't obtain the per-session token Django embeds in every form and requires on every POST.

**Q: Why would CSRF suddenly fail in production when it works locally?**
A: Because production sits behind a TLS-terminating proxy. Django receives plain HTTP, believes
it's serving `http://`, and rejects the browser's `https://` origin as a mismatch — a failure
mode that simply doesn't exist on `runserver`.

**Q: What's the difference between the two settings the plan adds?**
A: `SECURE_PROXY_SSL_HEADER` tells Django "the original request really was HTTPS, trust
`X-Forwarded-Proto`." `CSRF_TRUSTED_ORIGINS` tells it "this domain is a legitimate origin."
Both failures print the same "CSRF verification failed" message, which is why both get set.

**Q: When would trusting `X-Forwarded-Proto` be a mistake?**
A: Whenever the app can be reached without passing through the proxy — then a client can set
the header itself and claim a plain HTTP request was secure. It's safe on Railway because all
external traffic goes through their edge.

**Q: Why can't `CSRF_TRUSTED_ORIGINS` just be set in Phase 0 with everything else?**
A: The value must be the real deployed domain, and Railway doesn't generate one until after the
first deploy. Hence: deploy, generate domain, set the variable, redeploy, then test admin login.
