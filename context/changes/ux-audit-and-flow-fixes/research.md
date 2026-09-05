---
date: 2026-09-05T18:16:58+02:00
researcher: Tomasz Szreder
git_commit: f8a533d831a520f1855414f74b46d2f4fd8492ae
branch: worktree-feature+ux-audit-and-flow-fixes
repository: tszreder/domowa-apteka
topic: "S-06 UX audit — walking the running app at phone width"
tags: [research, ux-audit, mobile, flows, s-06]
status: complete
last_updated: 2026-09-05
last_updated_by: Tomasz Szreder
---

# Research: S-06 UX audit — walking the running app at phone width

**Date**: 2026-09-05T18:16:58+02:00
**Researcher**: Tomasz Szreder
**Git Commit**: `f8a533d` (audited build; identical to `origin/main` and to what is deployed)
**Branch**: `worktree-feature+ux-audit-and-flow-fixes` (a second worktree off
`feature/ux-audit-and-flow-fixes`, whose own worktree was locked by another
session while this audit ran — fold this commit into that branch)
**Repository**: tszreder/domowa-apteka

> **Naming note.** `roadmap.md` §S-06 names this artifact
> `context/changes/ux-audit-and-flow-fixes/ux-audit.md`. It is written here as
> `research.md` instead, because `research.md` is the filename the rest of the
> chain (`/10x-plan`, the `/10x-test-plan` orchestrator's state machine) reads.
> There is one artifact, not two. The roadmap line should be corrected to say
> `research.md` — flagged rather than edited, because `context/foundation/**` is
> not hand-edited (AGENTS.md).

## Research Question

Produce the S-06 audit: reach every core action — add an item, scan the list for
duplicates, invite a member — as a user on a phone-width viewport, and record
what the running app actually does, per screen, with observed behaviour rather
than template reading.

## Method, and its honest limits

Per `roadmap.md` §S-06, the audit had to be produced *by driving the running app
as a user*, not by reading the templates it was written against.

- **Viewport**: 390×844 (iPhone 14/15) for the first pass, 375×844 (iPhone SE /
  mini — the narrowest common phone) for the populated-household pass. Both are
  recorded per finding where the number matters.
- **Order of work**: the entire walkthrough — signup, invite, join, add, list,
  check, delete, logout — was completed **before any template or view file was
  opened**. Code anchors in *Code References* were added afterwards, only to give
  `/10x-plan` a starting point, and only for findings already established by
  observation.
- **Target**: the local dev server (`127.0.0.1:8765`) running `f8a533d`, which is
  byte-for-byte `origin/main` and therefore the deployed build. The audit was
  *not* run against the Railway URL, because every interesting screen is behind a
  household and creating audit accounts in production would leave real rows
  behind. As a check that this substitution is safe, the deployed landing page's
  `<main>` markup was fetched and compared against the local render — identical.
  **Where a finding's severity depends on URL length (F-06), the production URL
  was substituted into the live page and re-measured**, so that finding is stated
  in production terms.
- **Data**: the local database carries the real registry (20 254 products, 3 394
  substances) and a pre-existing 11-item household, so the list screen was
  audited at realistic scale, not against three hand-made rows.
- **Dev-data side effects** (local only, gitignored): three audit accounts were
  created, one household's invite token was regenerated, and one item was
  deleted — each as part of a finding below.

**What this audit does not do**: it does not rank findings and it does not decide
scope. `roadmap.md` §S-06 makes triage the user's decision and blocks `/10x-plan`
until it exists. The *Triage sheet* at the end is an empty column for that
decision, not a filled one.

## Summary

The app works. Every core flow completes, resolution is fast and correct, and the
duplicate rule — the reason the product exists — produces right answers. The
problems are not "it's broken"; they are that **the interface consistently gives
the most visual weight to the least important action, and the least to the most
important one**, and that **two flows break outright at the seams between
screens**.

Three findings are flow breaks, not polish:

1. **An invited person who already has an account never joins the household.**
   Tapping the invite link and then choosing "Zaloguj się" lands them on *"Załóż
   gospodarstwo domowe"* — the app asks them to create a rival household. Measured:
   `audit-partner@example.com` ended with zero memberships. The signup path works;
   the login path silently drops the invitation.
2. **The add form reports the wrong reason for a rejection and destroys the
   user's input.** Type a real product name, tap the big blue "Dodaj" without
   tapping a suggestion, and the answer is *"To pole jest wymagane."* ("This field
   is required") above a field that has been wiped clean. The real rule — "pick a
   suggestion" — is never stated.
3. **The invite screen scrolls sideways for roughly one household in four.**
   Whether the page fits a phone depends on whether the randomly generated invite
   token happens to contain a `-` or `_`. Measured: 575px of content in a 390px
   viewport when it doesn't; 390px when it does.

Beyond those, the recurring theme is inverted hierarchy. On the populated list
screen, **17.8 % of the rendered pixel area is "Usuń" (Delete) buttons** —
eleven full-width solid-blue slabs — while the partial-duplicate signal, the
product's second-biggest claim, is a 16px-tall grey disclosure that is collapsed
by default. The screen reads as "delete your medicines".

## Detailed Findings

Each finding: **screen → what was observed → the measurement or reproduction that
makes it checkable**. Severity labels describe *what kind of thing it is*, not
what should be done about it:

- **flow** — the user cannot complete a core task, or completes the wrong one
- **layout** — the screen misrenders at phone width
- **hierarchy** — the user completes the task but the screen argues against it
- **copy** — the words say something other than what is true
- **gap** — a needed affordance is absent

---

### Screen: `/` — landing

**F-01 · gap · The landing page has no way forward except the top-right nav.**
Below the `<h1>` and one sentence, the page is empty for the remaining ~600px of
an 844px viewport. There is no body CTA. The only routes onward are two nav items
squeezed against the right edge alongside the wrapped brand.
*Evidence*: `evidence/01-landing.png`.

**F-02 · flow · A logged-in user who opens the site root gets the marketing page,
not their list.** `/` returns 200 with the same hero for an authenticated user —
no redirect, no "Przejdź do listy". Reaching the medicine list from a home-screen
bookmark or a typed domain takes an extra tap on a nav link. The brand text
`Domowa Apteka` is a `<strong>`, not a link, so it is not the way back either.
*Reproduction*: logged in as `manualtest@example.com`, `GET /` → 200, `<main>`
contains only the hero heading and paragraph.

---

### Screen: `/signup/` and `/login/` — account

**F-03 · layout · Django's four password rules sit between the "Hasło:" label and
the password box.** The help text is rendered above its own input, so on a phone
the label and the field it labels are separated by a four-item bulleted list, and
the password field lands ~230px below its label.
*Evidence*: `evidence/02-signup.png`.

**F-04 · gap · No `autocomplete` attributes on the email or password fields.**
Chrome logs it unprompted: `[DOM] Input elements should have autocomplete
attributes (suggested: "username")`. On a phone this is the difference between a
password manager filling the form and the user typing an email address by thumb.
*Evidence*: console log at `/signup/`, captured during the walkthrough.

**F-05 · gap · There is no password reset, and the login screen does not say so.**
`main` on `/login/` contains **zero links** — no "Nie pamiętasz hasła?", no route
to signup. A user who forgets their password has no path back to their household
and no on-screen acknowledgement that this is the case.
*Reproduction*: fetched `/login/`, searched the rendered HTML for
`reset|zapomnia|przypomnij` → no match; `main a` → empty.

---

### Screen: `/household/` — invite and members

**F-06 · layout · The invite link pushes the page 185px wider than the phone, for
about a quarter of households.** The invite URL sits in an `inline-block <code>`.
`overflow-wrap: break-word` is set, but an auto-width inline-block sizes to
max-content, so the string only wraps if it already contains a break opportunity
— and the only candidates are `-` and `_` inside the base64url token.

Controlled measurement on one page, same styles, changing only the token text:

| invite URL | document `scrollWidth` @ 390px viewport |
| --- | --- |
| local, token contains `-` | **390** (fits) |
| local, token has no `-`/`_` | **575** (+185px sideways scroll) |
| production URL, token contains `-` | **390** (fits) |
| production URL, token has no `-`/`_` | **567** (+177px) |

Incidence: 4 of the 13 local households (31 %) hold a token with neither `-` nor
`_`; for a 43-character base64url token the expected share is 25.5 %. This was
also reproduced live — pressing "Wygeneruj nowy link" on *Manual Test Household*
minted `8m7tfyyTBuMwwiDRVqwfh0EC4r2qOghAUGSg4K4BfP8` and the page went from 390px
to 575px in one step.
*Evidence*: `evidence/04-household-invite-overflow.png`.

**F-07 · gap · There is no way to copy or send the invite link.** The single most
important action on this screen — get the link to your partner — requires
manually selecting a 93-character URL inside a `<code>` block on a phone. No copy
button, no `navigator.share`, no SMS/mail affordance.

**F-08 · hierarchy · The only button on the invite screen is the destructive
one.** "Wygeneruj nowy link" gets full-width primary-blue treatment; the action
the screen exists for gets none.

**F-09 · flow · Regenerating the invite link is one unconfirmed tap, and the
warning arrives only afterwards.** No confirm dialog, no `onclick`, no
`data-confirm`. The consequence is stated *after* the fact: *"Wygenerowano nowy
link zaproszenia. Poprzedni link już nie działa."* — by which point the link
already texted to a partner is dead.
*Reproduction*: performed on *Manual Test Household* during the audit.

**F-10 · flow · The members list can show a member with no identity at all.** For
an account whose `email` field is blank, the Members entry renders as
**"— dołączył(a) 24.08.2026"** — an em-dash, a join date, and nothing else. You
cannot tell who is in your household. The same blank feeds the nav, which renders
an orphan `—` above the household name. 3 of 17 local accounts have a blank
`email`.
*Evidence*: `evidence/13-household-members-anonymous.png`.

---

### Screen: `/join/<token>/` — accepting an invitation

**F-11 · flow · An invited person who already has an account never joins.**
Reproduced end to end:

1. Log out. Open the invite link → redirected to `/signup/`. The URL loses the
   token; nothing on screen mentions an invitation or names the household.
2. Tap **"Zaloguj się"** — the correct choice for someone who already has an
   account — and sign in as `audit-partner@example.com`.
3. Land on **"Załóż gospodarstwo domowe"**. The invitation is gone.

Verified in the database afterwards: `audit-partner@example.com` → **no
membership**. The same link followed through the *signup* form does work
(`audit-invitee@example.com` → joined `audit-s06`), so the defect is specific to
the login path.
*Evidence*: `evidence/11-join-lands-on-bare-signup.png`.

**F-12 · copy · The invitation is invisible on the screen it lands on.** The
anonymous invite target is a bare "Załóż konto" form: no household name, no "You
have been invited to …", no indication that signing up here joins someone else's
household rather than creating a new one. Contrast the *logged-in* join screen,
which is good and does all of this: *"Dołączyć do gospodarstwa „audit-s06"?"*
plus a plain-language consequence and one button.

**F-13 · gap · A successful join is never acknowledged.** After signing up
through an invite, the new member is dropped on the list with the household's
`<h1>` and someone else's medicines, and no message saying they joined. (The
*failure* case — an expired token — does get a message.) The same silence applies
to an ordinary first signup, which auto-creates a household named after the email
local part — `audit-s06@example.com` became a household called `audit-s06`, never
announced and never offered for naming, even though a household-naming screen
exists on the other path.
*Evidence*: `evidence/03-list-empty-after-signup.png`.

---

### Screen: `/list/add/` — adding a medicine

**F-14 · flow · The rejection message names the wrong field and wipes the input.**
Type `Ibuprom` (a real, resolvable product), tap the always-visible blue "Dodaj"
without tapping a suggestion. Result: **"To pole jest wymagane."** rendered above
an input that has been emptied back to its placeholder. The message is about the
hidden `product` field the user cannot see; the visible field was not empty. The
actual rule — you must choose a suggestion — is stated nowhere, and the typed
text is gone, so recovery means retyping.
*Evidence*: `evidence/06-add-wrong-error-message.png`.

**F-15 · layout · The suggestion list is in-flow, not overlaid, and 256px of it
lands where the phone keyboard will be.** `position: static`, `max-height: 256px`,
`overflow-y: auto`. Measured at 390×844: the list occupies y=300→556 and pushes
"Dodaj" below it. With a software keyboard (~300px) the usable viewport is ~544px
— the bottom of the list and the submit button are both under the keyboard, which
is exactly what makes F-14's mis-tap the natural thing to do. Only 4.5 of the 10
returned options are visible without scrolling the inner list.
*Evidence*: `evidence/05-add-autocomplete.png`.

**F-16 · hierarchy · Choosing a suggestion shows no confirmation of what was
resolved.** The picked option's whole label is pasted into the text box —
`Nurofen Forte — 400 mg — Tabletki powlekar…`, truncated by the input width, so
the user cannot even read their own choice — and the active substances are not
shown, although the API already returned them (`substances: ["Ibuprofenum"]`).
The user learns what the app resolved only *after* adding.
*Evidence*: `evidence/07-producer-typeahead.png`.

**F-17 · hierarchy · The producer step is a free-text typeahead over a set of two.**
For a multi-producer product a second field appears — "Producent (opcjonalnie)",
placeholder *"Zacznij pisać nazwę producenta…"*. For *Nurofen Forte* there are
exactly two holders; typing `re` narrows to one. Choosing between two known
options costs a keyboard. The field also appears with no explanation of why it
turned up or what leaving it blank does — and leaving it blank silently produces
a list row with no producer line, next to rows that have one.

**F-18 · layout · Suggestion ordering is alphabetical, including the strengths.**
Typing `paracetamol hasco` returns strengths in the order
`120 mg/5 ml, 125 mg, 250 mg, 500 mg, 500 mg, 80 mg` — **80 mg sorts last**,
after 500 mg, because strengths are compared as strings. A parent looking for the
child's 80 mg suppositories finds them in position 6 of 8. Likewise `paracetamol`
returns `Ibuprofen/Paracetamol Mylan` first and `Paracetamol Accord` ninth.

**F-19 · layout · Two suggestions can be indistinguishable.** `apap` returns both
`APAP — 500 mg — Tabletki powlekane` and `Apap — 500 mg — Tabletki powlekane`.
Same strength, same form, different marketing-authorisation holders (Delfarma
vs US Pharmacia) — but the holder is not in the option label, so the two rows
differ only by capitalisation. There is also a hard cap of 10 results with no
"showing 10 of N" hint.

**F-20 · flow · A trailing space returns nothing.** `q=" APAP "` → `{"results":
[]}`; `q="apap"` → 10 results. The query is not trimmed. A phone keyboard that
autocorrects or appends a space produces an empty dropdown, which reads as "this
medicine is not in the registry".

---

### Screen: `/list/` — the household list (the payoff)

Measured on a real 11-item household at 375×844.

**F-21 · hierarchy · Delete is the loudest thing on the screen.** Eleven
full-width solid-blue "Usuń" buttons occupy **154 750 px² of the 870 516 px²
list area — 17.8 %**. The page is 2 457px tall: **2.9 phone screens**, ~211px per
item, most of it delete affordance.
*Evidence*: `evidence/12-list-11-items.png`.

**F-22 · hierarchy · The partial-duplicate signal is the quietest thing on the
screen, and it is collapsed.** Partial overlaps render as a `<details>` whose
`<summary>` is **16px tall** — the smallest tap target on the page, below a 40px
delete button — and closed by default. Expanded, the content is exactly what the
user needs (`Paracetamolum: Paracetamol Hasco, APAP` / `Ibuprofenum: Nurofen
Forte`). Collapsed, the summary reads *"Wspólna substancja: Paracetamol Hasco,
APAP, Nurofen Forte"* — a singular "shared substance" followed by a list of
*product* names, so it parses as though those products were the substance, and it
hides the fact that two different substances are involved.
*Evidence*: `evidence/09-list-partial-collapsed.png`.

**F-23 · hierarchy · Two visual grammars in one list.** A duplicate group renders
as a bordered card with a bold heading; a non-duplicate item renders as a bare
`<li>` with a default bullet marker. Neither the card nor the heading carries any
warning treatment — no colour, no icon — so "Zamienniki — ta sama substancja
czynna" reads as a section label, not as *you already have this*.
*Evidence*: `evidence/08-list-full-duplicate.png`.

**F-24 · flow · Adding a duplicate does not say so at the moment it happens.**
Adding *Paracetamol Hasco* to a household that already holds *APAP* acknowledges
*"Dodano Paracetamol Hasco. Substancje czynne: Paracetamolum."* — and stops. The
app has just detected the exact thing it exists to detect and does not mention it;
the user has to notice the regrouping further down the page.

**F-25 · flow · Duplicate physical boxes render as byte-identical rows with no
count.** The real household contains two rows reading exactly `Nurofen Express
Forte — 400 mg — Kapsułki miękkie / Reckitt Benckiser (Poland) S.A. /
Ibuprofenum`, and two reading `ManualTest Apap — 500 mg / Paracetamol`. Nothing
distinguishes them and there is no "×2". Deleting one is a coin flip. The
`/check/` screen *does* show `Liczba opakowań: N` for the same items — the two
screens disagree about whether package count exists.

**F-26 · flow · Delete is one tap, unconfirmed, with no undo.** `POST
/list/<id>/delete/`, no confirm handler, no `data-confirm`. Performed during the
audit: the acknowledgement is *"Usunięto Nurofen Express Forte."* — no undo
offered. Combined with F-25, the user cannot know which of two identical rows
they removed.

**F-27 · gap · Unresolved items are a dead end.** Items whose substance could not
be determined are pushed to the bottom under an `<h2>` *"Nie udało się ustalić
substancji"*, and each one *also* carries a highlighted *"Nie udało się ustalić
substancji czynnej."* — the same sentence twice. The only action offered is
"Usuń": no retry, no "pick it from the registry", no explanation of what went
wrong.

**F-28 · gap · There is no ordering, no search, and no filter.** Eleven items
across 2.9 screens arrive in an order the user cannot reason about (duplicate
group, two loose items, another duplicate group, unresolved). Answering "do we
already have ibuprofen?" — US-03's job — means scrolling and reading.

**F-29 · layout · The header is 136px tall and does not stick.** `position:
static`. Once past the first screen of a 2 457px page there is no route to "Dodaj
lek" or to any nav item without scrolling all the way back to the top.

**F-30 · copy · Both `/list/` and `/household/` use the household name as their
`<h1>`.** Two different screens present an identical page heading; only the
browser tab title differs. The list screen never says what it is.

**F-31 · hierarchy · Flash messages are rendered as bulleted list items.**
`<ul class="messages"><li>…</li></ul>` inside `<main>` with no alert styling, so
"Dodano APAP…" appears as a `▪` bullet indistinguishable from page content —
including the 1-second acknowledgement the NFR cares about.
*Evidence*: `evidence/08-list-full-duplicate.png` (top of page).

---

### Screen: `/check/` — checking before you buy

**F-32 · hierarchy · There is no verdict.** The screen answers the pharmacy-aisle
question with two prose paragraphs in two visually identical cards: *"Masz już lek
z tą samą substancją czynną."* (full match) and *"Masz już lek, który ma
przynajmniej jedną wspólną substancję czynną."* (partial). Same border, same
weight, same colour. The two states the whole product exists to separate look the
same, and neither is summarised at the top.
*Evidence*: `evidence/10-check-result.png`.

**F-33 · flow · Deciding "yes, I do need it" is a dead end.** After a check there
is no "Dodaj do listy" — and no link back to the list. The user retypes the whole
name in the other screen. The negative answer (*"Żaden lek w domu nie zawiera tych
substancji czynnych."*) is exactly the moment they know they want it.

**F-34 · gap · `/check/` is unreachable from the nav.** Its only entry point is
"Sprawdź lek bez dodawania" on the list screen — a **21px-tall** plain link
(under half the 44px tap guideline) sitting next to a filled blue button.

**F-35 · copy · The checked query is cleared from the field.** After a check the
input returns to its placeholder while the result stays below, so it is unclear
whether the result is still live or stale.

---

## Verified non-issues

Recorded so `/10x-plan` does not spend a phase on a problem that is not there
(`lessons.md`: verify before designing around it).

- **Editing the name after picking a suggestion does not leave a stale binding.**
  Selecting *APAP* sets `product=14575`; typing over the text clears it to
  `product=` and `producer_confirmed=false`. No risk of adding a different
  medicine than the one shown.
- **Suggestion latency is not the 1-second-ack risk.** Measured locally: 4–69 ms
  across nine queries, and typing four characters issued exactly one request, so
  debouncing works. Whatever threatens the ack NFR, it is not this endpoint.
- **The keyboard highlight on the suggestion list is styled.** ArrowDown sets
  `.active` and it renders (`#525f7a` background, white text) — distinct from a
  plain option. (This was a defect noted in a previous slice; it is fixed.)
- **`Nurofen Forte` appearing twice in the dropdown is correct.** The two rows are
  different dosage forms — *Tabletki drażowane* vs *Tabletki powlekane* — and the
  form is in the option label, so they are distinguishable. Unlike F-19.
- **`Paracetamol` vs `Paracetamolum` on the list is test-fixture data**, not a
  presentation inconsistency: the short forms belong to hand-made `ManualTest…`
  rows, not to registry-resolved items.
- **The logged-in join screen is good** and should be left alone — it names the
  household, states the consequence in plain Polish, and offers one button. F-11
  and F-12 are about the *logged-out* path only.

## Code References

Added after the walkthrough, for `/10x-plan`'s benefit only. Every one of these
was reached from an observed behaviour, not the other way round.

- `templates/base.html:19` — `{{ user.email }}{% if user.membership %} — <a …>`:
  the orphan em-dash of F-10 when `email` is blank.
- `templates/base.html:15` — brand is `<strong>`, not a link (F-02).
- `templates/base.html:36-40` — `<ul class="messages">` with no alert styling
  (F-31).
- `households/views.py:71-72` — anonymous `join` stores the token in the session
  and redirects to **signup only** (F-11, F-12).
- `households/views.py:43` — the token is consumed only inside `signup`;
  `households/urls.py:14` wires login to Django's stock `LoginView`, which never
  reads `INVITE_TOKEN_SESSION_KEY` (F-11).
- `households/views.py:52-53` — household auto-created from `email.split('@')[0]`,
  with no prompt and no message; contrast the `household_create` screen at
  `households/views.py:122`, which does ask for a name (F-13, and the naming
  inconsistency behind it).
- `households/views.py:60` — successful invited signup redirects with no message;
  only the *expired* branch (`:56`) messages the user (F-13).
- `households/views.py:101-102` — `invite_url` built with `build_absolute_uri`,
  rendered into the `<code>` block of F-06/F-07.
- `pharmacy/forms.py:12-23` — `product` is the required `ModelChoiceField`; the
  visible search box is not a form field, which is why its "required" error lands
  where it does (F-14).

## Architecture Insights

- **The seams between screens are where this app fails, not the screens
  themselves.** Every individual screen completes its own job. Both flow breaks
  (F-11, F-14) happen at a hand-off: session → login view, and visible field →
  hidden field. This is what an audit of the running app catches and a
  template-by-template read does not.
- **Stock Pico plus stock Django form rendering sets the hierarchy, and the
  hierarchy is wrong.** Every `<button>` is primary-blue, so "Usuń" ×11
  out-shouts the duplicate warnings; every `<ul>` is a bulleted list, so flash
  messages look like content; every `help_text` renders above its input, so the
  password rules split label from field. These are not eleven separate decisions
  — they are one absent decision, which is precisely what S-07 is for. **S-06
  should fix the flows and the information, and resist restyling**, or it will
  spend itself on S-07's work.
- **The data layer already knows things the UI throws away**: substances at
  suggestion time (F-16), package counts on `/check/` but not `/list/` (F-25),
  the holder that distinguishes two identical-looking suggestions (F-19). Several
  findings are presentation-only and need no new queries.

## Historical Context (from prior changes)

- `context/archive/2026-08-24-duplicate-flagging-on-list/` — the full/partial
  presentation audited in F-22/F-23 originates here.
- `context/archive/2026-08-29-prescription-duplicate-check/` — `/check/` (F-32 –
  F-35). Its own roadmap entry flagged "where is the entry point?" as an open
  question deferred to S-06; F-34 is the answer, observed rather than assumed.
- `context/archive/2026-08-14-add-drug-with-substance-resolution/` — the picker
  and producer-confirmation flow of F-14 – F-20.
- `context/archive/2026-08-05-household-accounts-and-invites/` — invite and join
  (F-06 – F-13).

## Open Questions

Answering these is the user's call, and `roadmap.md` §S-06 makes the first of
them blocking:

1. **Triage.** Which findings are in this slice? 35 findings is several slices'
   worth. `/10x-plan` cannot start against an unranked list without silently
   choosing scope for itself.
2. **Is copy rewriting inside this slice?** F-12, F-22, F-30, F-32 and F-35 are
   wording, and wording is what those screens *mean*. Named as non-blocking in
   the roadmap, but it changes the shape of the plan.
3. **Where is the S-06/S-07 line?** Several hierarchy findings (F-08, F-21, F-23,
   F-31) can be fixed either by changing *what is on the screen* (S-06) or by
   changing *how it looks* (S-07). Choosing per finding avoids paying twice.
4. **Is package count (F-25) a presentation fix or a model question?** `/check/`
   already reports `Liczba opakowań`; whether `/list/` should aggregate identical
   items or merely label them is a product decision.
5. **Is password reset (F-05) in scope at all,** or is the fix simply to say on
   the login screen that it does not exist yet?

## Triage sheet

For the user to fill in. `/10x-plan` reads the **In slice?** column.

| ID | Screen | Kind | One line | In slice? |
| --- | --- | --- | --- | --- |
| F-01 | landing | gap | No body CTA; nav is the only way forward | |
| F-02 | landing | flow | Logged-in user at `/` gets marketing page | |
| F-03 | signup | layout | Password rules split label from field | |
| F-04 | signup/login | gap | No `autocomplete`; no mobile autofill | |
| F-05 | login | gap | No password reset and no mention of it | |
| F-06 | household | layout | Invite link scrolls page sideways (~25 % of households) | |
| F-07 | household | gap | No way to copy or share the invite link | |
| F-08 | household | hierarchy | Only button on screen is the destructive one | |
| F-09 | household | flow | Regenerate is unconfirmed; warning comes after | |
| F-10 | household | flow | Member can render with no identity at all | |
| F-11 | join | flow | **Invited existing user never joins** | |
| F-12 | join | copy | Invite target never mentions the invitation | |
| F-13 | join | gap | Successful join is never acknowledged | |
| F-14 | add | flow | **Wrong error, and the typed name is wiped** | |
| F-15 | add | layout | In-flow suggestion list sits under the keyboard | |
| F-16 | add | hierarchy | Selection shows no resolved substance; label truncated | |
| F-17 | add | hierarchy | Typeahead over two known producers | |
| F-18 | add | layout | Strengths sort as strings — 80 mg after 500 mg | |
| F-19 | add | layout | Two suggestions differing only by letter case | |
| F-20 | add | flow | Trailing space returns zero results | |
| F-21 | list | hierarchy | Delete is 17.8 % of the screen | |
| F-22 | list | hierarchy | Partial-duplicate signal is 16px and collapsed | |
| F-23 | list | hierarchy | Duplicate group has no warning treatment | |
| F-24 | list | flow | Adding a duplicate does not say so | |
| F-25 | list | flow | Identical rows, no count; `/check/` disagrees | |
| F-26 | list | flow | Delete: one tap, no confirm, no undo | |
| F-27 | list | gap | Unresolved items have no recovery action | |
| F-28 | list | gap | No ordering, search, or filter over 2.9 screens | |
| F-29 | list | layout | 136px header, not sticky | |
| F-30 | list | copy | Same `<h1>` as `/household/` | |
| F-31 | all | hierarchy | Flash messages render as bullets | |
| F-32 | check | hierarchy | No verdict; two states look identical | |
| F-33 | check | flow | No "add it anyway", no way back | |
| F-34 | check | gap | Unreachable from nav; 21px entry link | |
| F-35 | check | copy | Query cleared; result may read as stale | |
