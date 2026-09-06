# S-06 UX Audit Flow Fixes — Implementation Plan

## Overview

Fix 33 triaged-in audit findings plus 2 user-requested additions across 7 screens and a shared base template. Two must-fix flow breaks (F-11: invited existing user never joins; F-14: wrong error on add form), hierarchy inversions, layout bugs, copy rewrites, and missing affordances. All work stays within the S-06/S-07 boundary: structure and information only — no new visual language (colors, icons, verdict palette).

## Current State Analysis

The audit (`research.md`) walked the running app at phone width (390×844, 375×844) and recorded 35 findings. The user triaged 33 in-scope and 1 out (F-28: ordering/search/filter — a future slice). Two user-requested additions bring the total to 35 changes.

### Key Discoveries:

- The join-flow break (F-11) traces to `households/views.py:71-72` — `join()` stores the invite token in the session and redirects to signup only; stock `LoginView` never reads `INVITE_TOKEN_SESSION_KEY`
- The add-form break (F-14) traces to `pharmacy/forms.py:12-17` — `product` is a required hidden `ModelChoiceField`; Django's "required" error fires on the invisible field while the visible search input gets wiped
- The suggestion list is `position: static` (`app.css:68-105`), pushing the submit button under the phone keyboard — the root cause of F-14's mis-tap
- The data layer already has what the UI throws away: substances in the suggestion response, package counts on `/check/`, holders per producer — several findings are presentation-only

## Desired End State

Every core action — add an item, scan the list for duplicates, invite a member, check before buying — completes in fewer steps with clearer feedback, on a phone-width viewport, with no broken hand-offs between screens. An invited person who already has an account joins the household. The add form never shows a wrong error or wipes input. Delete requires confirmation. Identical items aggregate with a count. The list screen's hierarchy reflects what the app values: duplicate signals are prominent, delete is subordinate.

### Key Decisions:

| Decision | Choice | Why |
| --- | --- | --- |
| F-11 fix approach | `user_logged_in` signal handler | Decoupled from `LoginView` — works with any auth backend, no custom view class needed |
| F-14 fix approach | Client-side gate + better server error | Belt and suspenders — prevents the mis-tap (JS) and gives a clear message if JS fails (server) |
| F-15 suggestion positioning | Absolute overlay | Standard autocomplete pattern — doesn't reflow the page, submit button stays visible |
| F-17 producer selection | Native `<select>` dropdown | No keyboard needed; all options visible; works with mobile picker |
| F-25 identical items | Aggregate into one row with count | Shorter list, count visible; delete removes one instance |
| F-26 delete confirmation | JS `confirm()` dialog | Minimal change; styled confirm is S-07 |
| F-33 check→add bridge | "Wróć do listy" link only | Check is for the doctor's office; adding from there would prompt adding a drug you don't have yet |
| F-07 invite sharing | Copy button only | Simple, works everywhere; `navigator.share()` deferred |
| Phasing | By screen/flow area, 6 phases | Each phase testable as one screen; natural for manual verification |
| F-13+ household naming | Redirect to `/household/create/` | Form already exists; pre-fill with email prefix |

## What We're NOT Doing

- **F-28 (ordering/search/filter)**: Out of scope — a feature in its own right, not a fix this audit earns
- **New visual language**: No warning colors, icon system, or verdict palette — that's S-07's open question
- **Password reset flow**: F-05 is copy only ("not available yet"), not the flow itself
- **`navigator.share()`**: Deferred; copy button is the baseline
- **Undo on delete**: `confirm()` is the guard; an undo stack is a separate feature
- **Add-from-check**: The check screen is for the doctor's office, not for purchasing; an "add to shopping list" concept is out of scope now

## Phase 1: Base Template & Landing

### Overview

Cross-cutting changes to `base.html` and the landing page that improve every screen: flash messages stop looking like content, the header sticks, the brand becomes a link, the nav gains dedicated entries for household and check, and the landing page gets a CTA.

### Changes Required:

#### 1. Flash messages — strip list-marker styling (F-31)

**File**: `templates/base.html`

**Intent**: Flash messages currently render as `<ul class="messages"><li>…</li></ul>` with default Pico bullet markers, making them indistinguishable from page content. Remove the list markers and add minimal structure so messages read as notifications.

**Contract**: Replace the `<ul class="messages">` with a non-list container (e.g., a `<div>`) or add CSS in `app.css` to `.messages { list-style: none; padding: 0; margin: 0 0 1rem; }` and `.messages li { padding: 0.5rem 0; }`. Keep the `message.tags` CSS classes for S-07 to style later.

#### 2. Sticky header (F-29)

**File**: `static/css/app.css`

**Intent**: The 136px header scrolls off-screen on a 2457px list page, leaving no nav access. Make it stick.

**Contract**: Add `header { position: sticky; top: 0; z-index: 10; background: var(--pico-background-color); }` to `app.css`.

#### 3. Brand as a link (F-02 companion)

**File**: `templates/base.html`

**Intent**: "Domowa Apteka" is `<strong>` text, not a link. Make it a route back to the list (for authenticated users) or landing (for anonymous).

**Contract**: Change `<strong>Domowa Apteka</strong>` to `<a href="/"><strong>Domowa Apteka</strong></a>`. Since F-02 redirects authenticated users from `/` to `/list/`, this single link serves both audiences.

#### 4. Authenticated redirect from `/` (F-02)

**File**: `households/views.py`

**Intent**: A logged-in user opening the site root gets the marketing page instead of their list. Redirect them.

**Contract**: In `landing()`, if `request.user.is_authenticated`, return `redirect(reverse('pharmacy:item_list'))`. The existing `@household_required` on `item_list` handles users without a household.

#### 5. Nav links for household and check (F-nav, F-34)

**File**: `templates/base.html`

**Intent**: `/household/` is only reachable via an obscure inline link; `/check/` is only reachable from the list screen. Add dedicated nav items.

**Contract**: In the authenticated nav section, add `<li><a href="{% url 'households:household_detail' %}">Gospodarstwo</a></li>` and `<li><a href="{% url 'pharmacy:product_check' %}">Sprawdź lek</a></li>` alongside "Lista leków". Remove the current inline email + household-name display; replace with the cleaner dedicated links.

#### 6. Member identity fallback in nav (F-10 nav part)

**File**: `templates/base.html`

**Intent**: When `user.email` is blank, the nav renders an orphan em-dash. Show a fallback.

**Contract**: Replace `{{ user.email }}` with `{{ user.email|default:user.username }}` in the nav.

#### 7. Landing page CTA (F-01)

**File**: `households/templates/households/landing.html`

**Intent**: The landing page is empty below the h1 — no call to action. Add signup/login buttons.

**Contract**: Below the existing `<p>` tagline, add two `<a role="button">` elements: one linking to signup ("Załóż konto") and one linking to login ("Zaloguj się"). These are only visible when the template renders for anonymous users (authenticated users are redirected by F-02).

#### 8. Differentiate list screen heading (F-30)

**File**: `pharmacy/templates/pharmacy/item_list.html`

**Intent**: Both `/list/` and `/household/` use the household name as their `<h1>`. The list screen should name what it is.

**Contract**: Change the list screen's `<h1>` from `{{ household.name }}` to `Lista leków`.

### Success Criteria:

#### Automated Verification:

- Django system check passes: `uv run manage.py check`
- All tests pass: `uv run manage.py test`

#### Manual Verification:

- At 390×844: flash messages have no bullet markers
- Header sticks to top when scrolling a multi-screen list
- "Domowa Apteka" is a clickable link that reaches `/list/` (authenticated) or landing (anonymous)
- Authenticated user at `/` is redirected to `/list/`
- Nav shows "Gospodarstwo", "Lista leków", "Sprawdź lek" links for authenticated users with a household
- Blank-email user sees username in nav, not an orphan em-dash
- Landing page shows CTA buttons for anonymous visitors
- List screen heading says "Lista leków", not the household name

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase.

---

## Phase 2: Auth Screens

### Overview

Fix the signup and login templates: password help text placement, autocomplete attributes for mobile autofill, and login page copy (no reset, link to signup).

### Changes Required:

#### 1. Password rules below input (F-03)

**File**: `households/templates/households/signup.html`

**Intent**: Django renders password help text between the label and input, so the label and field are 230px apart. Render fields manually to control placement.

**Contract**: Replace `{{ form }}` with manual field rendering: for each field, render `<label>`, `{{ field }}` (the widget), then `{{ field.help_text }}` below. This puts the four password rules under the password box, not above it.

#### 2. Autocomplete attributes (F-04)

**File**: `households/forms.py`

**Intent**: No `autocomplete` attributes means no password-manager autofill on mobile. Add them.

**Contract**: In `SignupForm.__init__`, set `self.fields['email'].widget.attrs['autocomplete'] = 'email'`, `self.fields['password1'].widget.attrs['autocomplete'] = 'new-password'`, `self.fields['password2'].widget.attrs['autocomplete'] = 'new-password'`. In `EmailAuthenticationForm.__init__`, set `autocomplete='email'` on username and `autocomplete='current-password'` on password.

#### 3. Login page copy (F-05)

**File**: `households/templates/households/login.html`

**Intent**: The login page has zero links — no password reset, no route to signup. A user who forgets their password has no path forward and no acknowledgement. Add copy and a signup link.

**Contract**: Below the form, add: `<p>Nie masz jeszcze konta? <a href="{% url 'households:signup' %}">Załóż konto</a></p>` and `<p><small>Resetowanie hasła nie jest jeszcze dostępne.</small></p>`.

### Success Criteria:

#### Automated Verification:

- Django system check passes: `uv run manage.py check`
- All tests pass: `uv run manage.py test`

#### Manual Verification:

- At 390×844: password rules appear below the password input, not between label and field
- Chrome DevTools shows no `autocomplete` console warnings on `/signup/` and `/login/`
- Login page shows "Załóż konto" link and password-reset disclosure
- Password manager fills email and password on both signup and login

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase.

---

## Phase 3: Join + Household

### Overview

The heaviest phase — 9 findings including the must-fix F-11. Fixes the invite link overflow, adds copy button, demotes the destructive regenerate button, adds confirmation before regenerate, handles blank-email members, wires invite consumption into the login path, shows invitation context on signup, acknowledges joins, and redirects to household creation (with naming) instead of auto-creating.

### Changes Required:

#### 1. Invite link overflow (F-06)

**File**: `households/templates/households/household_detail.html`, `static/css/app.css`

**Intent**: The invite URL in `<code>` overflows for ~25% of households because `overflow-wrap: break-word` only breaks at `-`/`_` characters in an inline-block `<code>`. Make it break anywhere.

**Contract**: Change the `<code>` element to a block-level element or add CSS: `code { word-break: break-all; display: block; }` scoped to the invite section.

#### 2. Copy button (F-07)

**File**: `households/templates/households/household_detail.html`

**Intent**: The only way to share the invite link is manual selection of a 93-character URL on a phone. Add a copy button.

**Contract**: Add a `<button type="button" id="copy-invite">Kopiuj link</button>` next to the invite URL. Inline `<script>`: on click, `navigator.clipboard.writeText(inviteUrl)` and change button text to "Skopiowano!" for 2 seconds. The invite URL value comes from a `data-invite-url` attribute or a `<template>` element.

#### 3. Demote regenerate button (F-08)

**File**: `households/templates/households/household_detail.html`

**Intent**: "Wygeneruj nowy link" is the only button and gets primary-blue treatment. Demote it.

**Contract**: Add `class="secondary outline"` to the regenerate button, making it visually subordinate to the copy button.

#### 4. Regenerate confirmation (F-09)

**File**: `households/templates/households/household_detail.html`

**Intent**: Regenerating the invite link is one unconfirmed tap that invalidates any already-shared link. The warning arrives after the fact.

**Contract**: Add `onclick="return confirm('Wygenerowanie nowego linku unieważni obecny. Kontynuować?')"` to the regenerate button.

#### 5. Member identity fallback (F-10)

**File**: `households/templates/households/household_detail.html`

**Intent**: A member with blank `email` renders as "— dołączył(a) …" — no identity. Show a fallback.

**Contract**: Replace `{{ member.user.email }}` with `{{ member.user.email|default:member.user.username }}`.

#### 6. Invite token consumption on login (F-11) — MUST-FIX

**Files**: `households/signals.py` (new), `households/apps.py`

**Intent**: An invited person who already has an account taps the invite link, chooses "Zaloguj się", and never joins the household. The invite token is stored in the session by `join()` but only consumed by `signup()`. Wire it into the login path via a `user_logged_in` signal handler.

**Contract**:
- Create `households/signals.py` with a handler connected to `django.contrib.auth.signals.user_logged_in`. The handler: pops `INVITE_TOKEN_SESSION_KEY` from `request.session`; if present, looks up the household by token (`Household.objects.filter(invite_token=token).first()`); if valid and user has no membership, creates `Membership`; flashes a success message; if user already has a membership, flashes info.
- Update `households/apps.py`: add `def ready(self): import households.signals`.
- The handler must be idempotent — a stale or reused token does nothing harmful.

#### 7. Invitation context on signup screen (F-12)

**Files**: `households/views.py`, `households/templates/households/signup.html`

**Intent**: An anonymous invite target sees a bare "Załóż konto" form with no mention of the invitation or the household they're joining. Show context.

**Contract**: In `signup()` GET path, peek at `request.session.get(INVITE_TOKEN_SESSION_KEY)` (without popping); if present, look up the household and pass `invite_household` as context. The template shows: `{% if invite_household %}<p>Rejestrujesz się, aby dołączyć do gospodarstwa „{{ invite_household.name }}".</p>{% endif %}` above the form.

#### 8. Join acknowledgement (F-13)

**File**: `households/views.py`

**Intent**: After invited signup, the new member is dropped on the list with no message saying they joined.

**Contract**: In `signup()`, after successful invited join, add `messages.success(request, f'Dołączyłeś do gospodarstwa „{household.name}".')`.

#### 9. Household naming on signup (F-13+, user-requested)

**Files**: `households/views.py` (signup and household_create views)

**Intent**: Auto-creating a household from `email.split('@')[0]` with no naming prompt doesn't work. Redirect to the naming form that already exists.

**Contract**:
- In `signup()`: remove the auto-create block (lines 52-53 that create `Household` and `Membership` when there's no valid invite token). After login, redirect to `settings.LOGIN_REDIRECT_URL` (`/list/`). The `@household_required` decorator on `/list/` redirects users without a household to `/household/create/`.
- In `household_create()` GET: pre-fill the form with `initial={'name': request.user.email.split('@')[0]}` so the email prefix is a suggestion, not a fait accompli.
- Add a flash message when redirecting to household creation: in the `@household_required` decorator or in `household_create()`, add `messages.info(request, 'Utwórz swoje gospodarstwo domowe, aby zacząć.')` if the user has no household. Guard against duplicate messages on re-render.

### Success Criteria:

#### Automated Verification:

- Django system check passes: `uv run manage.py check`
- All tests pass: `uv run manage.py test`
- New tests for F-11 signal handler: invite token consumed on login, membership created, idempotent on stale token

#### Manual Verification:

- At 390×844: invite link wraps within the viewport for tokens with no `-`/`_`
- "Kopiuj link" button copies the URL; "Skopiowano!" feedback appears
- "Wygeneruj nowy link" is visually subordinate (outline) and asks for confirmation
- Blank-email member shows username instead of orphan em-dash
- **F-11**: Log out → open invite link → tap "Zaloguj się" → log in → verify user is now a member of the inviting household
- Signup via invite shows "Rejestrujesz się, aby dołączyć do…" and after signup shows "Dołączyłeś do…"
- Signup without invite: no auto-created household; redirected to `/household/create/` with email prefix pre-filled

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase.

---

## Phase 4: Add Medicine Form

### Overview

Fix the must-fix F-14 (wrong error + wiped input), reposition the suggestion dropdown as an absolute overlay, show resolved substances after picking, replace the producer typeahead with a native `<select>`, fix string sorting of strengths, add the holder to suggestion labels, and trim queries server-side.

### Changes Required:

#### 1. Client-side submission gate (F-14 client half)

**File**: `pharmacy/static/pharmacy/js/autocomplete.js`, `pharmacy/templates/pharmacy/item_form.html`

**Intent**: Prevent form submission until a suggestion is picked. The submit button should be disabled by default and enabled only when `pickPresentation()` fires.

**Contract**:
- Template: Add `disabled` to the submit button, and add a `<small>` hint below it explaining "Wybierz lek z listy podpowiedzi, aby dodać".
- JS in `autocomplete.js`: in `pickPresentation()`, enable the submit button. In `clearSelection()`, disable it.
- Preserve typed text: add a `<input type="hidden" name="search_text" id="search-text-hidden">` to the template. JS sets its value on each input event. On re-render, the view passes `search_text` back and the template sets the visible input's `value` from it.

#### 2. Server-side error message (F-14 server half)

**File**: `pharmacy/forms.py`

**Intent**: Replace the generic "To pole jest wymagane" with a message that names the real rule, as a fallback for when JS fails.

**Contract**: On the `product` field, set `error_messages={'required': 'Wybierz lek z listy podpowiedzi.', 'invalid_choice': 'Wybrany lek nie został znaleziony. Spróbuj ponownie.'}`.

#### 3. Preserve typed text on re-render (F-14 UX)

**File**: `pharmacy/views.py`, `pharmacy/templates/pharmacy/item_form.html`

**Intent**: When the form is re-rendered after a validation error, the visible search input is empty because it's not a form field. Preserve the user's typed text.

**Contract**: In `item_add()` POST path, read `request.POST.get('search_text', '')` and pass it as `search_text` in the template context. The template sets `value="{{ search_text }}"` on the visible search input.

#### 4. Absolute overlay suggestions (F-15)

**File**: `static/css/app.css`, `pharmacy/templates/pharmacy/item_form.html`, `pharmacy/templates/pharmacy/product_check.html`

**Intent**: The suggestion list is `position: static`, pushing content down and landing under the keyboard. Make it an overlay.

**Contract**:
- Template: Wrap the search input and `<ul id="suggestions">` in a `<div class="search-wrapper">` with `position: relative`.
- CSS: Change `.suggestions` from static to `position: absolute; top: 100%; left: 0; width: 100%; z-index: 20; background: var(--pico-background-color); box-shadow: 0 4px 6px rgba(0,0,0,.1);`.
- Apply the same wrapper to the check screen template (`product_check.html`).

#### 5. Substance preview after pick (F-16)

**File**: `pharmacy/static/pharmacy/js/autocomplete.js`, `pharmacy/templates/pharmacy/item_form.html`

**Intent**: After picking a suggestion, the user sees only a truncated label in the input. Show the resolved substances so they know what the app found.

**Contract**:
- Template: Add `<div id="substance-preview" hidden></div>` below the search wrapper.
- JS in `autocomplete.js`: in `pickPresentation()`, populate the preview with `presentation.substances.join(', ')` and show it. In `clearSelection()`, hide and clear it.

#### 6. Native `<select>` for producer (F-17)

**File**: `pharmacy/static/pharmacy/js/autocomplete.js`, `pharmacy/templates/pharmacy/item_form.html`

**Intent**: The producer typeahead over a set of 2 is a keyboard for a binary choice. Replace with a native `<select>`.

**Contract**:
- Template: Replace the producer text input + suggestion list with `<select id="producer-select" hidden><option value="">Wybierz producenta (opcjonalnie)</option></select>`.
- JS in `autocomplete.js`: in `pickPresentation()` when `producers.length > 1`, populate the select with `<option>` elements from `presentation.producers` (label: `producer.holder`, value: `producer.product_id`), and show the producer field. On `change` event, set `productField.value` and `producerConfirmedField.value = 'true'`.
- Remove the producer search input, producer suggestion list, and `renderProducerOptions()` logic.

#### 7. Numeric strength sorting (F-18)

**File**: `registry/suggestions.py`

**Intent**: Strengths sort as strings: "80 mg" lands after "500 mg". Sort numerically.

**Contract**: In `search_presentations()`, sort the final presentation list by a key that extracts the leading number from `strength` (e.g., `float(re.match(r'[\d.,]+', s).group().replace(',', '.'))` with a fallback to `float('inf')` for non-numeric strengths). Apply as a secondary sort after name matching.

#### 8. Holder in suggestion label (F-19)

**File**: `pharmacy/static/pharmacy/js/product-search.js`

**Intent**: Two suggestions can be indistinguishable when they differ only by marketing-authorisation holder. Add the holder to the label.

**Contract**: In the JS rendering of suggestion items, append the default holder: `${p.name} — ${p.strength} — ${p.form} / ${p.producers[0]?.holder || ''}`. The holder is already in the API response as `producers[0].holder`.

#### 9. Server-side query trim (F-20)

**File**: `registry/suggestions.py`

**Intent**: A trailing space returns zero results because the query is not trimmed server-side. The JS trims client-side, but the server should be robust on its own.

**Contract**: In `search_presentations()`, add `query = query.strip()` before the length check.

### Success Criteria:

#### Automated Verification:

- Django system check passes: `uv run manage.py check`
- All tests pass: `uv run manage.py test`
- New tests: F-14 custom error message on empty product field; F-20 trimmed query returns results

#### Manual Verification:

- At 390×844: submit button is disabled until a suggestion is picked; pressing it shows helpful text
- If JS fails to load: server-side error says "Wybierz lek z listy podpowiedzi", not "To pole jest wymagane"
- After a validation error, the typed search text is preserved in the input
- Suggestion list overlays content (not in-flow); submit button stays visible
- After picking "APAP — 500 mg", substance preview shows "Paracetamolum" below the input
- Producer step shows a native `<select>` dropdown, not a typeahead
- "paracetamol hasco" results show 80 mg before 500 mg
- Two APAP suggestions are distinguishable by holder name
- Query " APAP " returns the same results as "APAP"

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase.

---

## Phase 5: List Screen

### Overview

Restructure the household medicine list: demote delete to outline, expand partial overlap by default with clearer wording, emphasize duplicate headings, flash a duplicate warning on add, aggregate identical items with a count, add delete confirmation, and clean up unresolved items.

### Changes Required:

#### 1. Demote delete button (F-21)

**File**: `pharmacy/templates/pharmacy/_item_row.html`

**Intent**: Delete buttons are 17.8% of the list screen's pixel area, all primary-blue. Demote them.

**Contract**: Add `class="outline secondary"` to the delete `<button>`, making it a low-contrast outline button instead of a solid blue slab.

#### 2. Expand partial overlap by default + reword (F-22)

**File**: `pharmacy/templates/pharmacy/_partial_overlap_badge.html`

**Intent**: The partial-duplicate signal is a 16px collapsed `<details>` whose summary conflates product names with substance names. Expand by default and fix the wording.

**Contract**:
- Change `<details>` to `<details open>` so partial overlaps are visible without interaction.
- Reword the `<summary>` from "Wspólna substancja: {product_names}" to a formulation that distinguishes substances from products — e.g., the summary names the shared substance(s) and the expanded content lists which products share them.

#### 3. Substance names in duplicate heading (F-23)

**File**: `pharmacy/templates/pharmacy/item_list.html`

**Intent**: The heading "Zamienniki — ta sama substancja czynna" doesn't say WHICH substance is shared. State the fact.

**Contract**: For zamienniki groups (`not group.same_product`), derive the substance display names from the first item's substance links and include them in the heading: "Zamienniki — substancja czynna: {{ substances }}". The `same_product` heading stays as is.

#### 4. Duplicate flash on add (F-24)

**File**: `pharmacy/views.py`

**Intent**: Adding a duplicate doesn't mention the overlap. The app detects the exact thing it exists to detect and says nothing.

**Contract**: In `item_add()`, after saving the item, call `check_candidate(item.product, other_items)` where `other_items = Item.objects.filter(household=household).exclude(pk=item.pk).select_related('product').prefetch_related('product__substance_links__substance')`. If `check.matches` is non-empty, append to the success message: for full matches "Uwaga: masz już lek z tą samą substancją czynną ({matched_names}).", for partial "Uwaga: {matched_name} ma wspólne substancje czynne."

#### 5. Aggregate identical items with count (F-25)

**Files**: `pharmacy/duplicates.py`, `pharmacy/templates/pharmacy/item_list.html`, `pharmacy/templates/pharmacy/_item_row.html`

**Intent**: Two byte-identical rows with no count — `/check/` already computes pack count but `/list/` doesn't show it. Aggregate.

**Contract**:
- In `pharmacy/duplicates.py`: add an `ItemStack` dataclass with fields `product: Product`, `representative: Item` (the item whose pk is used for delete), `count: int`, `producer_confirmed: bool`. Add a `stacks` property to `DuplicateGroup` that sub-groups `self.items` by `product_id`, yielding one `ItemStack` per unique product with `count = len(sub_items)` and `representative = sub_items[0]`.
- In `_item_row.html`: accept an `ItemStack` (or keep backward compatibility). When `stack.count > 1`, display "×N" or "N opakowań" next to the product name. The delete form targets `stack.representative.pk`.
- In `item_list.html`: iterate `group.stacks` instead of `group.items`.

#### 6. Delete confirmation (F-26)

**File**: `pharmacy/templates/pharmacy/_item_row.html`

**Intent**: Delete is one tap, no confirm. Combined with F-25's aggregation, the user should know what they're deleting.

**Contract**: Add `onclick="return confirm('Usunąć {{ item.product.name }}?')"` (or the stack's product name) to the delete button.

#### 7. Unresolved items cleanup (F-27)

**File**: `pharmacy/templates/pharmacy/item_list.html`

**Intent**: Unresolved items show the same "Nie udało się ustalić substancji" sentence twice (section heading + per-item mark) and offer only "Usuń" — no recovery path.

**Contract**:
- Remove the per-item `<mark>` warning — the section heading already states the problem.
- Add a link below each unresolved item: "Usuń i dodaj ponownie" or just a "Dodaj ponownie" link to `/list/add/` — the user can try a different search term.

### Success Criteria:

#### Automated Verification:

- Django system check passes: `uv run manage.py check`
- All tests pass: `uv run manage.py test`
- New tests: F-24 duplicate flash message content; F-25 `ItemStack` aggregation logic, `DuplicateGroup.stacks` property

#### Manual Verification:

- At 375×844: delete buttons are outline/secondary, not solid blue — list hierarchy is inverted from before
- Partial overlap badges are expanded by default with clear substance-vs-product wording
- Zamienniki headings name the shared substance: "Zamienniki — substancja czynna: Paracetamolum"
- Adding a duplicate APAP to a household with APAP shows "Uwaga: masz już lek z tą samą substancją czynną"
- Two Nurofen Express Forte boxes render as one row with "×2" (or "2 opakowania"); delete removes one
- Delete asks "Usunąć {name}?" before proceeding
- Unresolved section: no duplicate sentence, recovery link present

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase.

---

## Phase 6: Check Screen

### Overview

Add a verdict sentence so the two match states look different, add a "Wróć do listy" link, and keep the query text visible after a check.

### Changes Required:

#### 1. Verdict sentence (F-32)

**File**: `pharmacy/templates/pharmacy/product_check.html`

**Intent**: Full match and partial match render in visually identical cards with no summary. Add a clear verdict at the top.

**Contract**: Before the match list, add a verdict block:
- If `check.matches` includes any `is_same_product` or `is_same_substances`: "Masz już lek z tą samą substancją czynną w domu."
- If matches are only `is_shared_substance`: "Masz lek z częściowo wspólnymi substancjami czynnymi."
- If no matches and resolved: "Nie masz tego leku ani zamienników w domu."
- Text emphasis only (bold or `<strong>`); colored cards/icons are S-07.

#### 2. Back-to-list link (F-33, revised)

**File**: `pharmacy/templates/pharmacy/product_check.html`

**Intent**: After a check there's no way back to the list. Add a link.

**Contract**: At the bottom of the result section, add `<a href="{% url 'pharmacy:item_list' %}">Wróć do listy</a>`.

#### 3. Keep query text after check (F-35)

**File**: `pharmacy/templates/pharmacy/product_check.html`

**Intent**: After a check, the search input returns to its placeholder while the result stays below, making it unclear what was checked.

**Contract**: When the template renders with a `candidate`, set the search input's `value` to the candidate's label: `value="{{ candidate.name }}{% if candidate.strength %} — {{ candidate.strength }}{% endif %}{% if candidate.pharmaceutical_form %} — {{ candidate.pharmaceutical_form }}{% endif %}"`.

### Success Criteria:

#### Automated Verification:

- Django system check passes: `uv run manage.py check`
- All tests pass: `uv run manage.py test`

#### Manual Verification:

- At 390×844: checking a product that has a full match shows "Masz już lek z tą samą substancją czynną w domu." prominently before the detail
- Checking a product with a partial match shows a different verdict than a full match
- Checking a product with no match shows "Nie masz tego leku ani zamienników w domu."
- "Wróć do listy" link is present and works
- After a check, the search input still shows the checked product's name

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase.

---

## Testing Strategy

### Unit Tests:

- F-11: Signal handler — invite token consumed on login, membership created; stale/expired token does nothing; user already in household gets info message
- F-14: Form error message — empty product field returns "Wybierz lek z listy podpowiedzi"
- F-20: `search_presentations(" APAP ")` returns the same results as `search_presentations("APAP")`
- F-24: Adding a duplicate item includes duplicate info in the flash message
- F-25: `DuplicateGroup.stacks` aggregates items by product_id with correct counts

### Integration Tests:

- F-11: Full flow — anonymous → invite link → redirect to signup → tap login → log in → verify membership exists
- F-02: Authenticated GET `/` → 302 to `/list/`
- F-13+: Signup without invite → redirect to `/household/create/` → form pre-filled with email prefix

### Manual Testing Steps:

1. Walk the invite flow end-to-end as an existing user (F-11 regression)
2. Walk the invite flow as a new user (F-12, F-13 regression)
3. Sign up fresh, verify household creation prompt (F-13+)
4. Add a medicine with and without picking a suggestion (F-14)
5. Check the suggestion list position relative to the keyboard (F-15)
6. Verify the populated list at 375×844 with 11+ items (F-21, F-22, F-23, F-25)
7. Delete an item from an aggregated group and verify count decreases (F-25, F-26)
8. Check a duplicate and a non-duplicate on `/check/` (F-32)

## Performance Considerations

- F-24 (duplicate flash on add): `check_candidate()` runs one extra query after item save. Acceptable for a single-item add; the queryset is already household-scoped.
- F-25 (aggregation): `DuplicateGroup.stacks` is computed in Python from the existing `items` list — no additional queries.
- F-15 (absolute overlay): No performance impact; CSS-only change.

## References

- Research/audit: `context/changes/ux-audit-and-flow-fixes/research.md`
- Evidence screenshots: `context/changes/ux-audit-and-flow-fixes/evidence/`
- Duplicate logic: `pharmacy/duplicates.py`
- Suggestion API: `registry/suggestions.py`
- Roadmap entry: `context/foundation/roadmap.md` §S-06

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles.

### Phase 1: Base Template & Landing

#### Automated

- [x] 1.1 Django system check passes — 7d7d707
- [x] 1.2 All existing tests pass — 7d7d707

#### Manual

- [x] 1.3 Flash messages have no bullet markers at 390×844 — 7d7d707
- [x] 1.4 Header sticks to top when scrolling — 7d7d707
- [x] 1.5 Brand is a clickable link — 7d7d707
- [x] 1.6 Authenticated user at `/` redirected to `/list/` — 7d7d707
- [x] 1.7 Nav shows Gospodarstwo, Lista leków, Sprawdź lek links — 7d7d707
- [x] 1.8 Blank-email user shows username in nav — 7d7d707
- [x] 1.9 Landing CTA buttons visible for anonymous — 7d7d707
- [x] 1.10 List screen heading says "Lista leków" — 7d7d707

### Phase 2: Auth Screens

#### Automated

- [x] 2.1 Django system check passes — 5af87fa
- [x] 2.2 All existing tests pass — 5af87fa

#### Manual

- [x] 2.3 Password rules below input at 390×844 — 5af87fa
- [x] 2.4 No autocomplete console warnings — 5af87fa
- [x] 2.5 Login page shows signup link and reset disclosure — 5af87fa

### Phase 3: Join + Household

#### Automated

- [x] 3.1 Django system check passes — 91a60d9
- [x] 3.2 All existing tests pass — 91a60d9
- [x] 3.3 New F-11 signal handler tests pass — 91a60d9

#### Manual

- [x] 3.4 Invite link wraps within viewport — 91a60d9
- [x] 3.5 Copy button works and shows feedback — 91a60d9
- [x] 3.6 Regenerate is outline and asks for confirmation — 91a60d9
- [x] 3.7 Blank-email member shows username — 91a60d9
- [x] 3.8 F-11: login via invite link joins the household — 91a60d9
- [x] 3.9 Signup via invite shows household name and join acknowledgement — 91a60d9
- [x] 3.10 Signup without invite redirects to household creation with pre-filled name — 91a60d9

### Phase 4: Add Medicine Form

#### Automated

- [x] 4.1 Django system check passes — f09bb48
- [x] 4.2 All existing tests pass — f09bb48
- [x] 4.3 New F-14 error message test passes — f09bb48
- [x] 4.4 New F-20 trim test passes — f09bb48

#### Manual

- [x] 4.5 Submit disabled until suggestion picked — f09bb48
- [x] 4.6 Server error says "Wybierz lek z listy podpowiedzi" — f09bb48
- [x] 4.7 Typed text preserved on re-render — f09bb48
- [x] 4.8 Suggestions overlay content (not in-flow) — f09bb48
- [x] 4.9 Substance preview shown after pick — f09bb48
- [x] 4.10 Producer uses native `<select>` — f09bb48
- [x] 4.11 Strengths sort numerically — f09bb48
- [x] 4.12 Holder visible in suggestion labels — f09bb48
- [x] 4.13 Trimmed query returns results — f09bb48

### Phase 5: List Screen

#### Automated

- [x] 5.1 Django system check passes — cb7109e
- [x] 5.2 All existing tests pass — cb7109e
- [x] 5.3 New F-24 duplicate flash test passes — cb7109e
- [x] 5.4 New F-25 ItemStack aggregation tests pass — cb7109e

#### Manual

- [x] 5.5 Delete buttons are outline/secondary — cb7109e
- [x] 5.6 Partial overlaps expanded with clear wording — cb7109e
- [x] 5.7 Zamienniki headings name the shared substance — cb7109e
- [x] 5.8 Adding a duplicate shows duplicate warning flash — cb7109e
- [x] 5.9 Identical items aggregated with count; delete removes one — cb7109e
- [x] 5.10 Delete asks for confirmation — cb7109e
- [x] 5.11 Unresolved items: no duplicate sentence, recovery link present — cb7109e

### Phase 6: Check Screen

#### Automated

- [x] 6.1 Django system check passes — 870ffc6
- [x] 6.2 All existing tests pass — 870ffc6

#### Manual

- [x] 6.3 Full-match verdict differs from partial-match verdict — 870ffc6
- [x] 6.4 No-match verdict says "Nie masz tego leku…" — 870ffc6
- [x] 6.5 "Wróć do listy" link present and works — 870ffc6
- [x] 6.6 Query text persists in input after check — 870ffc6
