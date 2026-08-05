---
title: "What makes an invite link safe to share, and why regeneration is enough to revoke it"
slug: unguessable-invite-tokens
date: 2026-08-05
tags: [security, django, web-fundamentals]
classification: mixed
prerequisites: [orm-models-and-sql-ddl]
---

# What makes an invite link safe to share, and why regeneration is enough to revoke it

## Why this came up

The entire join mechanism in `context/changes/household-accounts-and-invites/plan.md` rests on
one field: `Household.invite_token`. Anyone who knows that string can join the household and
see its shared medication list — there's no separate password, no per-invitee anything. That
makes the token's generation the actual security boundary of this feature, which is worth
understanding precisely rather than trusting the one line in `households/models.py` on faith.

## Builds on

[orm-models-and-sql-ddl.md](orm-models-and-sql-ddl.md) covered what `invite_token =
models.CharField(max_length=64, unique=True, db_index=True, blank=True)` becomes as a column.
This doc covers the one line that actually *fills* that column — `save()` and
`regenerate_invite_token()` in `households/models.py` — and why it's written the way it is.

## The concept, from the ground up

### The property this token needs: not just "random," but *unpredictable to an attacker who has seen other tokens*

```python
def save(self, ...):
    if not self.invite_token:
        self.invite_token = secrets.token_urlsafe(32)
    ...

def regenerate_invite_token(self) -> None:
    self.invite_token = secrets.token_urlsafe(32)
    self.save(update_fields=['invite_token'])
```

"Random" alone isn't a strong enough requirement here. What actually matters is: given every
token an attacker has ever observed (their own household's, or ones leaked/logged elsewhere),
can they predict or narrow down *anyone else's* token, or the next one this household will get
on regeneration? That's a **cryptographic** property, not just a statistical one — it requires
the generator's internal state to be practically unrecoverable from its output.

### Three ways to generate "a random-looking string" in Python, and only one fits

**`random.random()` / `random.choice()` / anything from the `random` module** — genuinely the
wrong tool here. Python's `random` module is a **Mersenne Twister**, a pseudo-random number
generator built for simulations and statistics, not secrecy: its full internal state can be
reconstructed from a modest number of consecutive outputs, after which every future output
becomes predictable. It's excellent for shuffling a deck in a game; it must never generate
anything a security decision depends on.

**`uuid.uuid4()`** — not wrong for the reason people often assume. In current CPython,
`uuid4()` is implemented as `UUID(bytes=os.urandom(16), version=4)` — it *does* draw from the
same operating-system cryptographic random source `secrets` uses. The real reasons this project
avoids it for a bearer token are narrower and more concrete:
- **Less usable entropy at the same nominal size.** A UUID reserves 6 of its 128 bits to encode
  its own version/variant, leaving 122 bits of actual randomness — `secrets.token_urlsafe(32)`
  draws a full 256 bits, with none spent on self-description.
- **Not a documented security guarantee.** `uuid4()`'s use of `os.urandom` is today's CPython
  implementation, not a contract the `uuid` module promises to keep — nothing in its
  documentation commits to a cryptographically secure source on every Python implementation,
  forever. `secrets` exists specifically to be that documented, load-bearing promise (it was
  added in Python 3.6, via [PEP 506](https://peps.python.org/pep-0506/), explicitly so
  security-sensitive code has an unambiguous, intentional API to reach for instead of relying on
  an incidental property of some other module).
- **Mismatched convention.** UUIDs are the ecosystem's default choice for *public*, non-secret
  identifiers — primary keys, correlation IDs, trace IDs, values that show up in logs and admin
  screens without a second thought. Storing a bearer secret in a field shaped exactly like every
  other harmless UUID in the codebase invites a future contributor (or you, in six months) to
  treat it as just another ID and log it, display it in an unrelated admin list, or pass it
  somewhere secrets shouldn't go — precisely the mistake the plan's own note that "the invite
  token may be shown [in `/admin/`] — `/admin/` is superuser-only" is quietly aware of.

**`secrets.token_urlsafe(nbytes)`** — the actual right tool, and what this project uses. It
draws `nbytes` bytes from `os.urandom` (the operating system's cryptographically secure random
source — the same primitive that generates TLS session keys) and base64-URL-encodes them, so
the result is safe to embed directly in a URL path with no further escaping. `token_urlsafe(32)`
requests 32 bytes — 256 bits of entropy — and produces a 43-character string (measured directly:
`len(secrets.token_urlsafe(32)) == 43`), which is why `invite_token`'s `max_length=64` in
`households/models.py` has comfortable headroom rather than being sized to exactly fit. 256 bits
of search space is not "hard to guess" — it is astronomically larger than any brute-force attack
against a web endpoint could ever exhaust, even at a global scale, before the heat death of
several universes.

### Why *regenerating* the token is a complete revocation, with nothing else needed

`regenerate_invite_token()` does exactly one thing: overwrite `invite_token` with a fresh
`secrets.token_urlsafe(32)` call and save it. That's the entire revocation mechanism this slice
implements — no expiry timestamp, no per-invitee tokens, no invite audit log (all explicitly
listed as out of scope in the plan's "What We're NOT Doing"). This is sufficient specifically
*because* the token is the sole credential:

- The old value is simply gone from the database the instant the new one is saved — any URL
  built from it (`households:join` with the old token as a path argument) resolves via
  `get_object_or_404(Household, invite_token=token)`, which now matches no row, so the request
  404s. There is nothing left anywhere that still recognizes the old string.
- A membership that already exists is untouched — regeneration only changes which *future*
  presented token grants a *new* membership; it was never how existing members' access is
  represented, so revoking the link cannot accidentally remove anyone already inside.
- Because the new value is drawn from the same 256-bit source as the first, there's no
  meaningful sense in which the *n*-th token is "more guessable" than the first — regenerating
  as many times as you like never degrades the guarantee.

A design with expiring tokens or per-invitee tokens would need a real reason (e.g., wanting to
audit exactly who joined via which link, or a threat model where the invite channel itself might
leak over time) — this project's threat model is simpler: one household, a small number of
trusted adults, sharing one link over a private messenger, and the standing worry is "someone
outside the household got hold of the link," which regenerate-to-revoke answers directly.

## In terms you already know

| This project's concept | What it's like in your world |
| --- | --- |
| `secrets.token_urlsafe(32)` — a cryptographically secure random token | Generating a **Power BI embed token / SAS token** — both draw from a secure random/signing source specifically because possessing the value *is* the authorization, with no separate identity check behind it. |
| `os.urandom` as the underlying entropy source | The **hardware/OS entropy pool** any cloud platform's key-generation service ultimately draws from — not something you'd ever reimplement yourself, only ever consume through a trusted, documented API. |
| `random.random()` (Mersenne Twister, reconstructible state) | A **fixed-seed random number generator used to make a Databricks notebook demo reproducible** — perfect when you *want* repeatability, disqualifying the moment unpredictability is the actual requirement. |
| Revocation by regenerating the token (no separate revoke flag) | **Rotating a Key Vault secret / SAS token** rather than maintaining a denylist of old ones — the old value simply stops existing anywhere that matters, instead of being tracked and explicitly blocked. |

## What's universal vs. what's specific to this project's choices

**True for any application handing out a bearer secret (a value that grants access to whoever
holds it, with no separate identity check):**
- The generator must be cryptographically secure — unpredictable even to someone who has seen
  many prior outputs — not merely "looks random," which is a much weaker and insufficient bar.
- Enough entropy to make brute-force guessing infeasible at your threat model's scale is a
  numeric property (bits of randomness), not a matter of the string merely "looking long."
- "Revoke by regenerating, since the old value stops being recognized" only works cleanly when
  the secret truly is the sole credential — the moment you need per-holder tracking or expiry,
  you need a different, more structured design (a table of tokens, not a single field).

**Specific because this project picked Python + Django's ORM:**
- `secrets` being the documented, purpose-built module for this is a Python-ecosystem detail
  (PEP 506); another language's standard library draws this same generic/secure-random
  distinction with different named APIs (e.g. .NET's `RandomNumberGenerator` vs. `Random`).
- Storing the token as a plain indexed `CharField` with `unique=True` — rather than, say,
  hashing it before storage the way a password would be — is a deliberate choice appropriate to
  *this* value: a password's hash defends against a stolen database revealing the real password,
  but an invite token's entire purpose is to be looked up by its plaintext value on every
  `/join/<token>/` request, so hashing it would only add cost without a matching benefit here.
- The single-standing-token-per-household model (one field, no separate tokens table) is this
  slice's explicit scope choice, not something Django or the ORM prescribes — a system needing
  per-invitee tracking would model tokens as their own table instead.

## Go deeper

- [Python docs: `secrets` — Generate secure random numbers for managing secrets](https://docs.python.org/3/library/secrets.html) —
  the authoritative reference, including the module's own explicit recommendation over `random`.
- [PEP 506 — Adding a secrets module to the standard library](https://peps.python.org/pep-0506/) —
  the actual rationale for why `secrets` was added as its own module rather than leaving this to
  `random` or `uuid`, written in plain language for exactly this kind of question.

## Quick recap

**Q: What's actually wrong with using `random.random()` to build a token?**
A: Its Mersenne Twister generator is reconstructible — observing enough consecutive outputs lets
someone recover its full internal state and predict every future value. Fine for simulations,
unsafe for anything a security decision depends on.

**Q: Is `uuid.uuid4()` "insecure" in the sense that its randomness is weak?**
A: Not in current CPython — it draws from the same `os.urandom` source `secrets` uses. The real
issues are fewer usable entropy bits (122 vs. 256), no documented guarantee that every Python
implementation will keep doing this, and UUIDs conventionally reading as public IDs, which
invites a secret to get treated like one and logged or displayed carelessly.

**Q: Why is 256 bits of entropy considered "enough," rather than needing to be even bigger?**
A: The search space is astronomically larger than any feasible brute-force attempt against a web
endpoint — adding more bits buys no practical security margin once you're already at this scale.

**Q: Why does `regenerate_invite_token()` not need to also track or blocklist the old value?**
A: Because the token is looked up directly against the `Household` row on every join attempt —
once the column holds the new value, no code path anywhere still recognizes the old one, so
there's nothing left to separately block.

**Q: When would regenerate-to-revoke stop being sufficient, and you'd need a real tokens table instead?**
A: The moment you need to know *who* used which link (an audit trail) or *individually* revoke
one invitee without affecting others — both require tracking tokens as separate rows, not one
field on the household.
