# Add a Drug and See Its Active Substance(s) Resolved — Implementation Plan

## Overview

Roadmap item **S-02**, the north star. A household member types a pharmaceutical's
name, picks it from registry-backed autocomplete, and the app records which active
substance(s) that product contains — or tells them plainly that it could not be
determined. The item lands on the shared household list at `/list/`, where every
member of that household sees it.

This is the slice that proves the product's central claim. F-01 loaded the registry
and S-01 built the household; neither has ever been asked whether a real brand name
a household would type actually resolves to a substance set they would recognise.

## Current State Analysis

**What exists.** Two apps, both with their roadmap items `done`:

- `registry` — a local mirror of the Polish national medicinal-products registry,
  loaded by `manage.py import_registry`. Three models (`registry/models.py`):
  `Product` (keyed on the registry's own `registry_id`), `Substance` (deduplicated
  vocabulary keyed on `name_key`), and `ProductSubstance` (the link, carrying the
  amount fields the source stated plus a `source_field` provenance column). No views,
  no URLs — reference data only. Production Postgres holds 20,245 active products,
  3,391 substances and 25,884 links as of snapshot `2026-08-13`
  (`context/archive/2026-08-07-registry-substance-data/production-baseline.md`).
- `households` — auth (`EmailAuthenticationForm`, signup, login), `Household` with an
  `invite_token`, `Membership` as a `OneToOneField` to the user, and a
  `household_required` decorator (`households/decorators.py:10`) that redirects
  anonymous users to login and household-less users to household creation.

**What is missing.** There is no item model of any kind. `households/views.py:139`
already defines an `item_list` view at `/list/` — it renders a household name and the
hardcoded string *"W tym gospodarstwie nie dodano jeszcze żadnych leków."*
(`households/templates/households/item_list.html:7`). `LOGIN_REDIRECT_URL` points at
`/list/`, so this is the first page every user sees after logging in, and it is a
placeholder. This slice fills it in.

**Measurements taken during planning** (local SQLite copy of the production snapshot,
20,245 active products — see "Key Discoveries" for what each one implies):

| Measurement | Value |
| --- | --- |
| Active products | 20,245 |
| Distinct `(name, strength, pharmaceutical_form)` presentations | 16,191 |
| Largest presentation group | 28 rows (`Concor Cor 2,5 / 2,5 mg / Tabletki`) |
| Mean / p95 / p99 group size | 1.25 / 2 / 8 |
| Groups with >1 distinct producer | 1,003 (6.2%) |
| Most distinct producers in one group | 10 |
| Groups whose rows disagree on substances | 201 (1.24%) |
| Groups resolving to zero substances | 428 groups, 457 products |
| `icontains` + SQL `LIMIT 10` over raw product rows | 0.5–10 ms (**SQLite dev**) |

The last row measured `Product.objects.filter(is_active=True, name__icontains=q)[:10]` —
a bounded query over raw rows. It is **not** a measurement of
`search_presentations`, which must group before it can slice. See "Performance
Considerations".

## Desired End State

A logged-in household member opens `/list/`, clicks through to an add form, types
`grip`, and sees a short list of real registry presentations — each showing name,
strength and pharmaceutical form. They pick one. If that presentation exists under
more than one marketing-authorisation holder, an optional producer field lets them
narrow to the exact box in their cabinet by typing part of the holder's name. They
save. The item appears on the household list showing its resolved active
substance(s), and any other member of the same household sees it on their next page
load. A member of a different household never does.

If the picked product carries no substance links in the registry, the item still
saves, the user sees a message saying the substance could not be determined, and the
item is displayed on the list in a visibly distinct unresolved state rather than
being dropped, hidden, or guessed at.

Items can be removed with a POST-only delete scoped to the owning household.

**How to verify:** `uv run manage.py test` is green; `uv run mypy` is clean; and the
manual pass in Phase 4 walks the flow against the real 20,245-row snapshot with two
accounts in two households.

### Key Discoveries:

- **Autocomplete cannot list raw `Product` rows.** 20,245 active products collapse to
  16,191 distinct `(name, strength, form)` presentations — parallel importers repeat
  the same presentation under different `marketing_holder` values.
  `Concor Cor 2,5 / 2,5 mg / Tabletki` appears **28 times**. A raw-row picker would
  offer 28 visually identical options with nothing to choose between them. Grouping by
  presentation is what makes FR-001's *"disambiguates specific products"* real.
- **Grouping is safe, and the exception is measured.** Only **201 of 16,191 groups
  (1.24%)** contain more than one distinct substance set. Sampled causes: salt-form
  variants (`Sortis 20` → `atorvastatinum` vs `atorvastatinum calcicum`;
  `Rennie Antacidum` → `magnesii subcarbonas` vs `magnesii subcarbonas ponderosus`)
  and groups where one importer's row simply carries no links (`Peditrace`,
  `Moviprep`).
- **The unresolved path is real, not hypothetical.** **428 presentation groups
  (457 products)** carry zero substance links. A user can pick a valid registry entry
  and still get nothing. US-01 and US-03 both have to hold on this path.
- **Producers are cheap to inline.** Only 6.2% of groups have more than one distinct
  producer, and no group has more than 10. Serializing producers into the suggestion
  payload costs ~2 KB for 10 results (vs 763 bytes without), so the producer field
  filters client-side with **no second round-trip**.
- **`PROTECT` on `ProductSubstance.substance` and keep-and-mark-inactive on `Product`
  (`registry/models.py:82`, `plan-brief.md` "Withdrawn products") mean a re-import can
  never orphan a user item.** This is what makes deriving substances live through the
  FK safe — it was designed for exactly this slice.
- **Raw-row search is fast; the grouped search is unmeasured.** `icontains` with a SQL
  `LIMIT 10` returned in 0.5–10 ms on **SQLite dev** — stated rather than asserted as
  Postgres parity, per `lessons.md`. But `search_presentations` cannot slice before it
  groups, so its query shape differs from the one measured. `ibu` matches 138 products
  and a 2-character query matches thousands. Phase 2 measures the real shape before
  anything is concluded about it.
- **`households:item_list` is referenced in 6 places** in
  `households/tests/test_access_control.py` (lines 29, 55, 70, 77, 85, 91). Moving the
  view renames the URL, and those tests are worth keeping — they already cover
  cross-household isolation and the `household_required` redirect chain.

## What We're NOT Doing

Scope creep is the roadmap's named hazard for the slices around this one, and S-03/S-04
both sit directly adjacent. Explicitly out of scope:

- **Duplicate flagging of any kind** — full or partial, on the list or anywhere else.
  That is **S-03** (`duplicate-flagging-on-list`). This slice writes the substance sets
  S-03 will compare; it does not compare them.
- **Expiration dates** — that is **S-04** (`expiration-date-per-item`). No date field,
  not even a nullable one "for later".
- **Editing an item** — add and delete only. S-04 will reopen the edit surface to add
  its date field; building an update form now means building it twice.
- **Free-text entry of drugs absent from the registry.** v1 requires picking a registry
  suggestion. The model is shaped so a nullable `product` FK is a later migration, but
  nothing in this slice is built to support it.
- **Scheduled registry refresh and freshness display** — that is **F-02**
  (`registry-freshness-refresh`).
- **Real-time updates.** PRD US-01 requires visibility *"without requiring a manual
  refresh/re-sync action **beyond normal navigation**"* — a server-rendered page load
  satisfies it verbatim. No WebSockets, no polling, no SSE.
- **Quantity, dosage, notes, photos, barcode scanning** — none are in the PRD for v1;
  barcode is an explicit Non-Goal.
- **Any change to `registry`'s models, migrations, parser, loader, or import command.**
  This slice reads registry data and adds one query module; it does not reshape it.
- **Search over substances** (e.g. "show me everything with paracetamol"). Not in FR-001.
- **Indexes, caching, or query tuning** for autocomplete, given the measurement above.
- **Splitting the 201 divergent groups** or reconciling salt-form variants. See
  "Accepted limitations".

## Implementation Approach

A new `pharmacy` app owns household-scoped item data. It reads `registry` but
`registry` never imports it — the same one-way dependency F-01 established between its
pure parser and its dumb loader.

```
        pharmacy (user data)                    registry (reference data)
  ┌──────────────────────────────┐         ┌────────────────────────────────┐
  │ Item ──FK──────────────────────────────▶ Product ──▶ ProductSubstance   │
  │   household, added_by,       │         │                   │            │
  │   added_at                   │         │                   ▼            │
  │                              │         │              Substance         │
  │ views: item_list, item_add,  │  reads  │                                │
  │        item_delete,          │────────▶│ suggestions.py  [pure queries] │
  │        product_suggestions   │         │   presentation grouping        │
  └──────────────────────────────┘         │   producer lists + tiebreak    │
                                           └────────────────────────────────┘
```

Three deliberate seams:

1. **Substances are derived, never copied.** There is no item→substance table. An
   item's substances are read through `item.product.substance_links` at display time,
   so they always match what the registry currently states — which is what the NFR
   ("current to within about a day") asks for. A snapshot copy would show a substance
   the source no longer states.
2. **Grouping and tiebreak live in `registry/suggestions.py`, not in a view.** They are
   the correctness-critical rules of this slice and they are pure functions over the
   registry schema, testable with no HTTP involved — mirroring how F-01 kept every rule
   that touches the never-infer NFR inside a database-free parser.
3. **The form's field is a plain `Product` id.** Grouping is a *presentation* concern
   that the suggestion endpoint resolves; by the time the form is submitted the choice
   has already collapsed to one registry row. This keeps the form trivial and keeps the
   tiebreak in one testable place.

## Critical Implementation Details

**Deriving substances costs a query per item unless prefetched.** The list view must
use `select_related('product')` plus
`prefetch_related('product__substance_links__substance')`; without it a 30-item list
issues 60+ queries. `ProductSubstance.Meta.ordering = ['source_order']`
(`registry/models.py:105`) already guarantees a stable display order within a product,
so the template must not re-sort.

**The prefetch is easy to defeat without noticing.** `prefetch_related` populates
`_prefetched_objects_cache` for `.all()` only — `.exists()`, `.count()`, and
`.filter()` on a related manager all go back to the database, one query per item, even
when the prefetch ran. So `Item.unresolved` must read the cache
(`not self.product.substance_links.all()`), never
`self.product.substance_links.exists()`, which reads like the obvious implementation
and is the wrong one. The `assertNumQueries` test will catch it; the correct response
to that failure is to fix the property, not to loosen the assertion.

**The tiebreak must prefer a row that has substance links.** Among the group's rows,
choose one with at least one `ProductSubstance`; break the remaining tie on the lowest
`registry_id`. The naive "lowest `registry_id`, whatever it has" rule reports
"substance unknown" for products whose sibling row in the same group resolves fine —
`Peditrace` and `Moviprep` are measured instances. `registry_id` is the registry's own
stable key, so the choice is reproducible across re-imports; a database pk is not,
because F-01's loader may re-create rows.

**"Unresolved" is derived, never stored.** An item is unresolved iff its product has
zero substance links. A stored boolean would silently drift out of date the first time
a re-import adds links to a product a user already saved.

## Phase 1: `pharmacy` app, `Item` model, and the list view

### Overview

Stand up the app and the model, and move the existing placeholder list view into it so
that everything downstream has a real, household-scoped, CI-covered home. No add form
yet — items are created in tests and via the shell.

### Changes Required:

#### 1. App scaffold

**File**: `pharmacy/` (new, via `uv run manage.py startapp pharmacy`)

**Intent**: Create the app that owns user-entered pharmaceutical items, separate from
`registry` (reference data) and `households` (identity and grouping).

**Contract**: `pharmacy` added to `INSTALLED_APPS` in `domowa_apteka/settings.py`, and
to `[tool.mypy] files` in `pyproject.toml` — which currently lists
`["households", "registry", "domowa_apteka"]`, so a new app is invisible to the type
checker until added.

#### 2. The `Item` model

**File**: `pharmacy/models.py`

**Intent**: One pharmaceutical box a household has at home, pointing at the registry
row it was resolved to. Carries no substance data of its own — substances are read
through the product FK so they stay current.

**Contract**: `Item` with `household` (FK to `households.Household`, `CASCADE`,
`related_name='items'`), `product` (FK to `registry.Product`, `PROTECT`,
`related_name='items'`), `added_by` (FK to `settings.AUTH_USER_MODEL`, `SET_NULL`,
nullable), `added_at` (`auto_now_add`), and `producer_confirmed`
(`BooleanField(default=False)`). `Meta.ordering = ['-added_at']`.

`producer_confirmed` exists because the `product` FK alone cannot answer "did the user
actually choose this producer?". Two different user actions produce byte-identical
rows: picking `Concor Cor 2,5` and leaving the producer blank stores the tiebreak
default (measured: the Merck row, out of 8 distinct holders across 28 rows), and
explicitly picking Merck stores the same row. Without the flag, the list would print
"Merck" in both cases — presenting a 1-in-8 guess as fact in the 6.2% of groups where
the field matters most. See Phase 1 § 5 for the display rule it drives.

`PROTECT` on `product`, matching `ProductSubstance.substance`: F-01's loader marks
absent products inactive rather than deleting them, so this should never fire — and if
a future change starts deleting products, the error is the correct outcome, not a
silent cascade through user data. `SET_NULL` on `added_by` so removing a user account
does not delete the household's list.

An `unresolved` property returning whether the product has zero substance links, so
templates and tests share one definition of the term. It **must** evaluate
`self.product.substance_links.all()` rather than `.exists()` — see "Critical
Implementation Details" for why the obvious spelling silently defeats the list view's
prefetch.

**Note on the deliberate non-null `product`:** the "free text later" decision means a
future migration makes this nullable and adds a raw-name column. Nothing is built for
that now; it is recorded here so the later migration is understood as planned, not as
a reversal.

#### 3. Migration

**File**: `pharmacy/migrations/0001_initial.py`

**Intent**: Create the table.

**Contract**: Generated by `uv run manage.py makemigrations pharmacy`. Depends on
`households.0001_initial` and `registry`'s initial migration.

#### 4. Move the list view

**File**: `pharmacy/views.py`, `pharmacy/urls.py`, `domowa_apteka/urls.py`

**Intent**: Relocate `item_list` from `households` to `pharmacy` and make it render
real items with their derived substances, unresolved items distinctly.

**Contract**: `item_list` decorated with `households.decorators.household_required`,
resolving the household the same way `households/views.py:21` does. Registered under
`app_name = 'pharmacy'` and included so the URL path stays **`/list/`** — this keeps
`LOGIN_REDIRECT_URL = '/list/'` (`domowa_apteka/settings.py:210`) unchanged. The URL
name becomes `pharmacy:item_list`.

Delete `households.views.item_list` and its `path('list/', …)` entry.

The queryset must be `Item.objects.filter(household=…)` with
`select_related('product')` and
`prefetch_related('product__substance_links__substance')`.

#### 5. Templates

**File**: `pharmacy/templates/pharmacy/item_list.html` (new);
`households/templates/households/item_list.html` (delete)

**Intent**: Render the household's items with their resolved substances, and show
unresolved items in a visibly distinct state. Keep the existing empty-state text.

**Contract**: Extends `base.html`. Per item: product name, strength, form, and its
substance names. Unresolved items carry a distinct marker (Pico supports this without
custom CSS). Nothing in this template sorts, groups, or compares items — that is S-03.

**Producer is shown only when it is known to be right.** Render
`item.product.marketing_holder` **iff `item.producer_confirmed`**, and suppress it
otherwise. Displaying it unconditionally would reintroduce exactly the flaw that ruled
out the show-but-don't-store option: an unchosen producer is arbitrary and likely wrong
for the box in hand.

The rule is deliberately a single boolean read, not a derived check. The alternative —
"show it when the product's presentation group has one distinct holder" — is equally
correct but costs a group-membership query per item at render time, which fights the
prefetch contract this same view depends on. Phase 3 § 4 is where the flag gets set so
this stays a plain field read.

#### 6. Retarget the existing access-control tests

**File**: `households/tests/test_access_control.py`

**Intent**: Keep the six existing assertions working against the moved URL. They
already cover cross-household isolation and both `household_required` redirect
branches; re-pointing them is cheaper and better than rewriting them.

**Contract**: `reverse('households:item_list')` → `reverse('pharmacy:item_list')` at
lines 29, 55, 70, 77, 85, 91.

#### 7. Model and scoping tests

**File**: `pharmacy/tests/__init__.py`, `pharmacy/tests/test_models.py`,
`pharmacy/tests/test_item_list.py`

**Intent**: Pin that the list is household-scoped and that resolved and unresolved
items render differently.

**Contract**: A small fixture helper building `Substance` / `Product` /
`ProductSubstance` rows directly (no snapshot file, no import command). Cases: an item
in household A never appears for a member of household B; an item whose product has
links shows its substance names; an item whose product has zero links renders as
unresolved; `Item.unresolved` matches in both directions; an item with
`producer_confirmed=True` shows its `marketing_holder` on the list and one with
`producer_confirmed=False` does not.

### Success Criteria:

#### Automated Verification:

- Migration applies cleanly: `uv run manage.py migrate`
- No model changes are left unmigrated: `uv run manage.py makemigrations --check --dry-run`
- Full test suite passes: `uv run manage.py test`
- Type checking passes: `uv run mypy`
- Django's system checks pass: `uv run manage.py check`
- The six retargeted access-control tests pass against `pharmacy:item_list`

#### Manual Verification:

- Logging in still lands on `/list/` with no 404 and no redirect loop
- An item created in the shell appears on the list with its substance names
- An item whose product has no substance links is visibly distinct on the list

**Implementation Note**: After completing this phase and all automated verification
passes, pause here for manual confirmation from the human before proceeding.

---

## Phase 2: Presentation search and the suggestion endpoint

### Overview

The correctness-critical half of this slice, built with no UI attached: group registry
products into pickable presentations, resolve which concrete row a pick maps to, and
serve the result as JSON.

### Changes Required:

#### 1. The suggestion query module

**File**: `registry/suggestions.py` (new)

**Intent**: Own the two rules that decide whether this slice is correct — how products
collapse into presentations, and which concrete row a presentation without an explicit
producer resolves to. Lives in `registry` because both are facts about the registry's
own data shape, and is pure-queries-only so it can be tested without HTTP.

**Contract**: Two functions plus a result dataclass.

`search_presentations(query: str, limit: int = 10) -> list[Presentation]` — matches
active products on `name__icontains`, groups them by
`(name, strength, pharmaceutical_form)`, and returns at most `limit` presentations
ordered by name. `icontains` over `istartswith`: no measurable cost difference at this
scale and it matches `cor` against `Concor Cor`.

`Presentation` carries `name`, `strength`, `pharmaceutical_form`, the substance display
names of its default product, and `producers` — a list of
`(marketing_holder, product_id)` pairs for the group, **one pair per _distinct_
`marketing_holder`, not one per row**, sorted by holder name, with the default product's
id identified. The representative row for each holder is chosen with the same
default-product rule below, so there is one tiebreak in the module rather than two.

> **Corrected 2026-08-16 after implementation review (F7).** As originally written, this
> paragraph said only "pairs for the group", which permits one pair per row — and that is
> how it was implemented. Every measurement and rationale around it assumed distinct
> holders (Phase 1 § 2 "8 distinct holders across 28 rows", manual criterion 3.6, and the
> inline-payload sizing resting on "no group has more than 10 producers"), so the plan
> contradicted itself and the contradiction was resolved silently in the permissive
> direction. Per-row producers reintroduce exactly the flaw presentation grouping exists
> to remove: `Concor Cor 2,5` offered 28 options across 8 distinguishable names, and
> because identical-looking options carry different `product_id`s, in the 1.24% of groups
> whose rows disagree on substances the user could unknowingly select a different
> substance set. Do not "simplify" this back to one pair per row.

The default-product rule, which is the phase's core contract:

```
default product of a group =
    min(rows that have ≥1 ProductSubstance, key=registry_id)
    if any such row exists
    else min(all rows in the group, key=registry_id)
```

Comparing `registry_id` as the registry's own stable key, not as a database pk — F-01's
loader may recreate rows, so pks are not reproducible across re-imports.

`registry_id` is a `CharField` (`registry/models.py:43`), so "lowest" means
**lexicographic on the stored string**, not numeric. Say so in the implementation and
keep it consistent: a Python-side `min(..., key=…)` and a database-side
`order_by('registry_id')` must not be mixed, or the tests and the running code can
disagree on a group the fixtures never cover.

The blank-`strength` case matters: measured values include `'-'` and multi-paragraph
free text (`registry/models.py:47`), so grouping must treat the raw stored string as
opaque and never parse it.

#### 2. Suggestion tests

**File**: `registry/tests/test_suggestions.py` (new)

**Intent**: Pin the grouping and tiebreak rules against hand-built rows reproducing the
shapes measured in the real data.

**Contract**: Cases, each mirroring a measured instance:
- N rows sharing `(name, strength, form)` under different holders collapse to one
  presentation with N producers (the `Concor Cor 2,5` shape).
- Same name, different strengths → separate presentations (the `Xanax` shape).
- A group where one row has links and another has none → the default product is the
  one **with** links (the `Peditrace` / `Moviprep` shape).
- A group where all rows have links but disagree → default is the lowest `registry_id`
  (the `Sortis 20` salt-variant shape), and the test states this is one of two
  defensible answers, chosen for determinism.
- A group with no links anywhere → a presentation with an empty substance list, not an
  omission (the 428-group shape).
- Inactive products are excluded.
- `icontains` matches mid-string and is case-insensitive.
- `limit` is respected.

#### 3. The JSON endpoint

**File**: `pharmacy/views.py`, `pharmacy/urls.py`

**Intent**: Serve presentations to the add form's autocomplete.

**Contract**: `product_suggestions`, `household_required`, GET-only, reading a `q`
query parameter. Returns `JsonResponse` with a `results` list of presentations, each
with `name`, `strength`, `form`, `substances`, `default_product_id`, and `producers`
(`{holder, product_id}` objects). Producers are inlined rather than fetched on demand —
measured at ~2 KB for 10 results, versus a second round-trip against a 1-second NFR.

Returns an empty `results` list for a query shorter than 2 characters, so a single
keystroke does not scan for `a`.

`household_required` rather than `login_required`: it costs nothing and keeps every
authenticated surface in this app on one rule.

#### 4. Endpoint tests

**File**: `pharmacy/tests/test_suggestions_endpoint.py` (new)

**Intent**: Pin the JSON contract the phase-3 JavaScript will consume, and the auth
boundary.

**Contract**: Anonymous GET redirects to login; a household-less user redirects to
household creation; a member gets JSON with the documented keys; a short query returns
an empty list; the response is `application/json`.

### Success Criteria:

#### Automated Verification:

- Full test suite passes: `uv run manage.py test`
- Type checking passes: `uv run mypy`
- The tiebreak test asserting "prefer a row with substances" fails when the preference
  is removed (confirming the test can actually fail, per `lessons.md`)

#### Manual Verification:

- **Measure `search_presentations` against the real 20,245-row local database with a
  worst-case 2-character query** (the shortest the endpoint accepts) and record the
  number in the change folder — the planning measurement covered a different query
  shape and does not transfer. If the fetch-then-group shape is slow, compare the
  group-in-SQL shape before adding any index. See "Performance Considerations".
- `curl`ing the endpoint while logged in against the real 20k-row local database
  returns sensible presentations for `grip`, `apap`, `xanax`, and `concor`
- `xanax` returns its distinct strengths as separate entries, not 59 near-identical rows
- `concor cor 2,5` returns one entry carrying multiple producers
- Response feels instantaneous by hand

**Implementation Note**: After completing this phase and all automated verification
passes, pause here for manual confirmation from the human before proceeding.

---

## Phase 3: The add flow

### Overview

The user-facing half: a form, the autocomplete that drives it, the optional producer
field, and the unresolved message. The only phase containing hand-written JavaScript.

### Changes Required:

#### 1. The add form

**File**: `pharmacy/forms.py` (new)

**Intent**: Validate that the submitted choice is a real, active registry product.

**Contract**: A `ModelForm` on `Item` exposing `product` and `producer_confirmed`,
both with `widget=forms.HiddenInput`. `product` is a `ModelChoiceField` whose queryset
is active products; `producer_confirmed` is not required and defaults to `False`.
`household` and `added_by` are set by the view, never accepted from the request.

The widget override on `product` is not cosmetic: a `ModelForm` on a FK defaults to a
`Select`, and `{{ form.product }}` would render 20,245 `<option>` tags into a page
governed by a one-second NFR. `HiddenInput` still validates the submitted id against
the active-products queryset, so the inactive-product rejection below is unaffected.

`producer_confirmed` is set by the browser (Phase 3 § 4) and trusted. A crafted POST
could set it without picking a producer, but it crosses no privilege boundary — it is
the user's own household item, and the only consequence is that they caused a producer
to be displayed on their own list. Not worth a server-side derivation, which cannot
work anyway: a user who explicitly picks the producer that *happens* to be the tiebreak
default is indistinguishable from one who skipped the field.

Rejecting an inactive product matters: a user could hold a stale form open across a
re-import that withdrew the product. The error message must say the product is no
longer in the registry.

#### 2. The add view

**File**: `pharmacy/views.py`

**Intent**: Save the item to the requesting user's household and tell them what was
resolved — including when nothing was.

**Contract**: `item_add`, `household_required`, GET renders the form, POST saves and
redirects to `pharmacy:item_list` (POST-redirect-GET, so a refresh does not duplicate
the item).

On success, a `messages.success` naming the product and its resolved substances. When
the product has **zero** substance links, a `messages.warning` instead, stating the item
was saved but its active substance could not be determined from the registry. Both
paths save. This is the PRD Guardrail — a lookup failure is never silent — and US-03's
"shown separately" requirement is what makes saving (rather than rejecting) the
correct reading.

#### 3. Templates

**File**: `pharmacy/templates/pharmacy/item_form.html` (new);
`pharmacy/templates/pharmacy/item_list.html` (edit)

**Intent**: A search input driving a suggestion list, a hidden field carrying the
chosen product id, an optional producer field that appears only when the picked group
has more than one producer, and a link to the form from the list.

**Contract**: The visible search input is **not** the form field — the form field is a
hidden `product` input the JavaScript sets. The template must render usefully with
JavaScript disabled to the extent of not appearing broken, but autocomplete is a
JavaScript feature and picking without it is not supported in v1.

The producer control is a text input plus a filtered list over the picked group's
producers, matching the search control's interaction so there is one pattern to learn.
It stays hidden for the 93.8% of groups with a single producer.

#### 4. The autocomplete script

**File**: `pharmacy/static/pharmacy/js/autocomplete.js` (new)

**Intent**: Debounced search against the phase-2 endpoint, render suggestions, and on
pick set the hidden product id and populate the producer control from the inlined
producer list.

**Contract**: Vanilla ES2020, no build step, no dependency, loaded with `defer`.
Roughly: a ~200 ms debounce; each request tagged with a monotonically increasing
sequence number so a slow response cannot overwrite a newer one; `AbortController` on
supersede. Changing the search text after a pick clears **both** hidden inputs, so a
stale id can never be submitted alongside an edited name.

The three state transitions that set `producer_confirmed`, which is the whole reason
the field exists:

| Picked group | User action | `product` | `producer_confirmed` |
| --- | --- | --- | --- |
| one producer | nothing to choose | `default_product_id` | **`true`, set automatically** |
| several producers | picks one | that producer's `product_id` | `true` |
| several producers | leaves the field blank | `default_product_id` | `false` |

The automatic `true` in row 1 is not a shortcut: when a group has a single holder the
tiebreak had nothing to choose between, so the value is necessarily correct and asking
the user to confirm it would be a question with one answer. It covers 93.8% of groups
and is what keeps the list template a single boolean read rather than a per-item query.

Producer filtering is client-side over the already-delivered list — there is no second
endpoint and no second request.

Keyboard support: arrow keys move through suggestions, Enter picks, Escape closes.
Suggestions rendered with `textContent`, never `innerHTML` — registry names are
publisher-controlled data, and Pico gives no XSS protection.

`collectstatic` must see the new directory; `STATICFILES_DIRS` already covers
project-level `static/`, and `django.contrib.staticfiles` picks up app-level
`static/` automatically (`domowa_apteka/settings.py` comment at `STATICFILES_DIRS`).

#### 5. Add-flow tests

**File**: `pharmacy/tests/test_item_add.py` (new)

**Intent**: Cover the server side of the add flow — the JavaScript is not unit-tested,
so the view and form must be.

**Contract**: A POST with a valid product id creates an item in the requesting user's
household and redirects to the list; the item is not created in any other household;
a POST with an inactive product id is rejected with a form error and creates nothing;
a POST with a product that has zero substance links **still creates the item** and
produces a warning message; a POST with a resolved product produces a success message
naming the substances; a POST omitting `producer_confirmed` stores `False` rather than
erroring; anonymous and household-less users are redirected.

One test asserts that a member of household B cannot see an item household A just
added — the PRD Guardrail, tested at the point items first become creatable.

### Success Criteria:

#### Automated Verification:

- Full test suite passes: `uv run manage.py test`
- Type checking passes: `uv run mypy`
- `uv run manage.py collectstatic --dry-run --noinput` sees `autocomplete.js`
- The unresolved-save test fails if the view is changed to reject unresolved products
  (confirming it tests the behaviour, not just the status code)

#### Manual Verification:

- Typing `grip` shows suggestions within roughly a keystroke; picking one and saving
  puts the item on the list with its substances
- Typing `concor` and picking `Concor Cor 2,5` reveals the producer field (measured: 8
  distinct holders across 28 rows); typing part of a holder's name narrows it; saving
  records that specific row **and shows that producer on the list**
- Saving the same `Concor Cor 2,5` with the producer field left blank stores the item
  and shows **no** producer on the list — not the tiebreak default (Merck)
- A single-producer product shows its producer on the list without the field ever
  having been touched
- Picking a product with no substances saves and shows the warning message, and the
  item appears on the list in its unresolved state
- Editing the search text after a pick prevents submission rather than saving the
  previously picked product
- The flow is usable on a phone-width viewport
- Acknowledgement of a save arrives within one second (PRD NFR)

**Implementation Note**: After completing this phase and all automated verification
passes, pause here for manual confirmation from the human before proceeding.

---

## Phase 4: Delete, and end-to-end verification

### Overview

Close the loop so a mistaken entry is recoverable, then prove the north star against
real data with two accounts.

### Changes Required:

#### 1. Delete

**File**: `pharmacy/views.py`, `pharmacy/urls.py`,
`pharmacy/templates/pharmacy/item_list.html`

**Intent**: Let any member of the household remove an item — the roles are symmetric,
so "added by someone else" is not a reason to refuse.

**Contract**: `item_delete`, `household_required` and `require_POST`, taking the item
pk. Looks the item up **filtered by the requesting user's household** — so an item
belonging to another household is a 404, not a 403, and the endpoint does not confirm
that the id exists. Redirects to the list with a `messages.success`.

`require_POST` matters: a GET that mutates would let a prefetcher or a crawled link
delete a household's items. Rendered as a small POST form per row with a CSRF token,
following the logout button in `templates/base.html:22`.

#### 2. Delete tests

**File**: `pharmacy/tests/test_item_delete.py` (new)

**Intent**: Pin the authorization boundary and the method guard.

**Contract**: A member deletes their household's item; a member of another household
gets a 404 and the item survives; a member can delete an item added by a different
member of the same household; a GET to the delete URL is rejected with 405 and deletes
nothing; anonymous and household-less users are redirected.

#### 3. Navigation

**File**: `templates/base.html`

**Intent**: Make the list reachable from anywhere once logged in.

**Contract**: A `pharmacy:item_list` link in the authenticated branch of the nav,
alongside the existing household link at line 19.

### Success Criteria:

#### Automated Verification:

- Full test suite passes: `uv run manage.py test`
- Type checking passes: `uv run mypy`
- `uv run manage.py check --deploy` reports nothing new beyond the two already-parked
  items (`SECURE_SSL_REDIRECT`, HSTS — see roadmap § Parked)
- No unmigrated model changes: `uv run manage.py makemigrations --check --dry-run`

#### Manual Verification:

Against the real local snapshot (20,245 products), with two accounts in two households:

- **The north star:** type `Apap`, pick it, save — the item shows a substance set a
  household member would recognise. Repeat for `Gripex` (expected: more than one
  substance) and `Ibuprom`.
- `Xanax` offers distinct strengths rather than dozens of identical rows
- `Concor Cor 2,5` reveals the producer field, and picking a producer records that row
- A product with no substance links saves, warns, and displays as unresolved
- Member B of household A sees member A's item on their **next page load**, with no
  refresh button and no re-login
- A member of household B never sees household A's items at any URL, including a direct
  delete POST against a known item id
- Delete removes the item and the list reflects it immediately
- The whole flow works at phone width
- Save acknowledgement arrives within one second

**Implementation Note**: This phase's manual verification is the slice's actual
acceptance test — it is the first time anyone has checked whether a real brand name
resolves to a substance set a household would recognise. Record what the tried names
resolved to in the change folder, so S-03 has real examples to reason about.

---

## Testing Strategy

### Unit Tests:

- `registry/tests/test_suggestions.py` — presentation grouping, the default-product
  tiebreak in all four measured shapes, inactive exclusion, match semantics, limit.
- `pharmacy/tests/test_models.py` — the `unresolved` property in both directions,
  `PROTECT` on product, `SET_NULL` on `added_by`, and `producer_confirmed` defaulting
  to `False`.

### Integration Tests:

- `pharmacy/tests/test_item_list.py` — household scoping, resolved vs unresolved
  rendering, and (via `assertNumQueries`) that the prefetch actually holds, so a
  regression to N+1 fails CI rather than being noticed in production.
- `pharmacy/tests/test_suggestions_endpoint.py` — the JSON contract and auth boundary.
- `pharmacy/tests/test_item_add.py` — creation, household assignment, the unresolved
  save path, inactive-product rejection, message content.
- `pharmacy/tests/test_item_delete.py` — authorization boundary and the POST-only guard.
- `households/tests/test_access_control.py` — six existing assertions retargeted to
  `pharmacy:item_list`.

**Fixtures are hand-built registry rows**, not the real snapshot: CI has no 74 MB file
and F-01's suite is deliberately offline. The risk that hand-built fixtures encode a
wrong assumption is mitigated by building each one to reproduce a shape measured
against the real data during planning, and named after it in the test.

### Manual Testing Steps:

1. `uv run manage.py runserver`, log in as a member of household A.
2. Add `Apap`, `Gripex`, `Xanax 1 mg`, `Concor Cor 2,5`, and one product known to have
   no substance links; confirm each result against expectation.
3. Log in as a member of household A in a second browser profile; confirm the items
   are visible on page load.
4. Log in as a member of household B; confirm none of household A's items are visible,
   and that a hand-crafted delete POST against one of their ids returns 404.
5. Repeat the add flow at phone width.
6. Delete an item; confirm it disappears and the message appears.

## Performance Considerations

**What was measured:** `Product.objects.filter(is_active=True, name__icontains=q)[:10]`
returned in 0.5–10 ms against 20,245 active products on the **SQLite dev database**.
That is a bounded query — SQL `LIMIT 10` over raw rows. At this row count Postgres will
seq-scan an `ILIKE '%x%'` in the same order of magnitude, but that is inference, not
measurement, stated as such per `lessons.md`.

**What was not measured, and must be before anything is concluded:**
`search_presentations` has a different shape. It cannot apply the limit before it
groups, so a naive implementation fetches *every* matching row, groups in Python, then
slices — and `ibu` alone matches 138 products while a 2-character query matches
thousands. The measured number does not transfer, and this plan does not claim it does.

Phase 2 therefore measures the real function against the real 20k-row local database
with a worst-case 2-character query, and records the number. Two implementation shapes
are worth comparing at that point:

1. **Fetch-then-group in Python** — one unbounded query, grouping cost proportional to
   matches.
2. **Group in SQL, then hydrate** — `.values('name', 'strength', 'pharmaceutical_form')`
   with the slice applied in the database, then a second bounded query fetching
   producers and default products for the ≤10 chosen groups. Two bounded queries, so
   the database limits the work rather than Python.

Pick on the measurement, not in advance. If neither is fast enough, the cheapest fix is
a `name` prefix index or `pg_trgm` — but nothing is added speculatively.

The other risk is N+1 on the list view, which is why the prefetch is a contract with an
`assertNumQueries` test behind it rather than an optimization. Note that the prefetch is
easy to defeat: see "Critical Implementation Details".

Suggestion payloads are ~2 KB for 10 results with producers inlined.

## Migration Notes

One new table (`pharmacy_item`) and no changes to any existing one. The migration is
additive and reversible; nothing in `registry` or `households` is altered except the
URL name `households:item_list` → `pharmacy:item_list`, which has no persisted state
behind it.

Production already holds the registry data this slice reads
(`production-baseline.md`), so deploying is a normal `migrate` on merge with no data
step and no import run.

## Accepted limitations

Recorded here rather than left for S-03 to rediscover:

- **Salt-form variants defeat set equality.** `Sortis 20` resolves to
  `atorvastatinum` in one registry row and `atorvastatinum calcicum` in another; a
  household holding one box of each will see two different substance sets for what is,
  medically, the same drug. Merging those names would be **inferring a substance
  identity the source does not state**, which the NFR bans outright. This slice
  therefore records what the registry says and accepts that S-03's duplicate flagging
  will miss this class. Measured extent: 201 of 16,191 presentation groups (1.24%)
  disagree internally, of which the salt-variant shape is a subset.
- **The default-product tiebreak silently picks one of two defensible answers** in
  those groups when the user does not choose a producer. It is deterministic and
  reproducible; it is not "correct" in any deeper sense. `producer_confirmed` keeps
  that arbitrariness off the screen but does not remove it — the item is still linked
  to the tiebreak row, so its substances come from that row.
- **`producer_confirmed` is browser-set and trusted.** No privilege boundary is
  crossed; the worst case is a user causing a producer to display on their own list.
- **Drugs absent from the registry cannot be recorded at all in v1.** Supplements,
  foreign packaging, and anything outside the human-use subset F-01 loaded have no
  entry point. This is the accepted cost of the autocomplete-only decision.
- **Substances derived live can change under the user.** A re-import that corrects a
  product's links changes what an already-saved item resolves to, without notice. This
  is the intended behaviour of the freshness NFR, but it means the substances shown at
  add time are not a permanent record.

## References

- Roadmap item S-02: `context/foundation/roadmap.md` § Slices
- PRD FR-001, FR-002, US-01, US-03, NFRs: `context/foundation/prd.md`
- F-01's design and measured data shape:
  `context/archive/2026-08-07-registry-substance-data/plan-brief.md`
- Production registry baseline:
  `context/archive/2026-08-07-registry-substance-data/production-baseline.md`
- Recurring rules honoured here (verify before designing around a claim; resolve plan
  contradictions in the plan): `context/foundation/lessons.md`
- Household scoping pattern to follow: `households/views.py:21`,
  `households/decorators.py:10`
- Registry schema and its deliberate constraints: `registry/models.py`

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles. See `references/progress-format.md`.

### Phase 1: `pharmacy` app, `Item` model, and the list view

#### Automated

- [x] 1.1 Migration applies cleanly: `uv run manage.py migrate` — 8bc8e0e
- [x] 1.2 No model changes left unmigrated: `uv run manage.py makemigrations --check --dry-run` — 8bc8e0e
- [x] 1.3 Full test suite passes: `uv run manage.py test` — 8bc8e0e
- [x] 1.4 Type checking passes: `uv run mypy` — 8bc8e0e
- [x] 1.5 Django system checks pass: `uv run manage.py check` — 8bc8e0e
- [x] 1.6 The six retargeted access-control tests pass against `pharmacy:item_list` — 8bc8e0e

#### Manual

- [x] 1.7 Logging in still lands on `/list/` with no 404 and no redirect loop — 8bc8e0e
- [x] 1.8 An item created in the shell appears on the list with its substance names — 8bc8e0e
- [x] 1.9 An item whose product has no substance links is visibly distinct on the list — 8bc8e0e
- [x] 1.10 An item with `producer_confirmed=True` shows its producer; one with `False` does not — 8bc8e0e

### Phase 2: Presentation search and the suggestion endpoint

#### Automated

- [x] 2.1 Full test suite passes: `uv run manage.py test` — e6fc383
- [x] 2.2 Type checking passes: `uv run mypy` — e6fc383
- [x] 2.3 The tiebreak test fails when the "prefer a row with substances" preference is removed — e6fc383

#### Manual

- [x] 2.4 `search_presentations` measured against the real 20k-row database with a worst-case 2-char query, number recorded — e6fc383
- [x] 2.5 The endpoint returns sensible presentations for `grip`, `apap`, `xanax`, `concor` against the real 20k-row local database — e6fc383
- [x] 2.6 `xanax` returns distinct strengths, not 59 near-identical rows — e6fc383
- [x] 2.7 `concor cor 2,5` returns one entry carrying multiple producers — e6fc383
- [x] 2.8 Response feels instantaneous by hand — e6fc383

### Phase 3: The add flow

#### Automated

- [x] 3.1 Full test suite passes: `uv run manage.py test` — 2ffeed6
- [x] 3.2 Type checking passes: `uv run mypy` — 2ffeed6
- [x] 3.3 `uv run manage.py collectstatic --dry-run --noinput` sees `autocomplete.js` — 2ffeed6
- [x] 3.4 The unresolved-save test fails if the view is changed to reject unresolved products — 2ffeed6

#### Manual

- [x] 3.5 Typing `grip` shows suggestions promptly; picking one and saving puts the item on the list with its substances — 2ffeed6
- [x] 3.6 `Concor Cor 2,5` reveals the producer field, typing narrows it, and saving records that specific row and shows it on the list — 2ffeed6
- [x] 3.7 The same product saved with the producer field blank shows no producer on the list — not the tiebreak default — 2ffeed6
- [x] 3.8 A single-producer product shows its producer without the field being touched — 2ffeed6
- [x] 3.9 Picking a product with no substances saves, warns, and appears as unresolved on the list — 2ffeed6
- [x] 3.10 Editing the search text after a pick prevents submission rather than saving the stale product — 2ffeed6
- [x] 3.11 The flow is usable on a phone-width viewport — confirmed 2026-08-16 by the user directly at ~375px (the browser automation's `resize_window` could not do this in this environment; see measurements.md). Add flow, suggestion list, and producer picker all usable.
- [x] 3.12 Save acknowledgement arrives within one second — 2ffeed6

### Phase 4: Delete, and end-to-end verification

#### Automated

- [x] 4.1 Full test suite passes: `uv run manage.py test` — bff834e
- [x] 4.2 Type checking passes: `uv run mypy` — bff834e
- [x] 4.3 `uv run manage.py check --deploy` reports nothing new beyond the two parked items — bff834e
- [x] 4.4 No unmigrated model changes: `uv run manage.py makemigrations --check --dry-run` — bff834e

#### Manual

- [x] 4.5 North star: `Apap`, `Gripex`, and `Ibuprom` each resolve to a recognisable substance set — bff834e
- [x] 4.6 `Xanax` offers distinct strengths rather than dozens of identical rows — bff834e
- [x] 4.7 `Concor Cor 2,5` reveals the producer field, picking a producer records and displays it, and leaving it blank displays no producer — bff834e
- [x] 4.8 A product with no substance links saves, warns, and displays as unresolved — bff834e
- [x] 4.9 Member B of household A sees member A's item on their next page load — bff834e
- [x] 4.10 A member of household B never sees household A's items, including via a direct delete POST — bff834e
- [x] 4.11 Delete removes the item and the list reflects it immediately — bff834e
- [x] 4.12 The whole flow works at phone width — confirmed 2026-08-16 by the user directly at ~375px: search → pick presentation → pick producer → save → see it in the list → delete, all usable end to end. See measurements.md.
- [x] 4.13 Save acknowledgement arrives within one second — bff834e
- [x] 4.14 Resolved substance sets for the tried names recorded in the change folder — bff834e
