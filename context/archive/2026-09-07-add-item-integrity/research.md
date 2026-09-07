---
date: 2026-09-07T18:32:59+02:00
researcher: Tomasz Szreder
git_commit: fea2a2ad7404529ddff58c494c8a8b7cbb34cc02
branch: feature/add-item-integrity
repository: domowa-apteka
topic: "Add-item integrity: product identity, substance match, and resolution failure"
tags: [research, codebase, pharmacy, registry, add-item, substance-resolution, query-shape]
status: complete
last_updated: 2026-09-07
last_updated_by: Tomasz Szreder
---

# Research: Add-item integrity — product identity, substance match, and resolution failure

**Date**: 2026-09-07T18:32:59+02:00
**Researcher**: Tomasz Szreder
**Git Commit**: fea2a2ad7404529ddff58c494c8a8b7cbb34cc02
**Branch**: feature/add-item-integrity
**Repository**: domowa-apteka

## Research Question

This is `test-plan.md` §3 Phase 2 ("Add-item integrity"), covering risks #1, #3,
and #4 from the risk map. The phase goal: *prove the chosen product is the
saved product, that its substances match the source row, and that a
resolution failure is visible — including one query-shape assertion for the
one-second acknowledgement requirement.* Concretely, `/10x-research` must
ground:

- **Risk #1**: what the suggestion payload carries, what the save path
  persists out of it, and whether product identity travels as a stable
  registry key or is re-derived from the typed string.
- **Risk #3**: which source field is authoritative, how a multi-substance row
  is represented, and which values are placeholders rather than substance
  identities.
- **Risk #4**: what the save path does when resolution misses, and how an
  unresolved item is represented so later duplicate logic cannot group it.

## Summary

The add-item flow (`pharmacy/views.py:64-109`, `pharmacy/forms.py:8-24`,
`registry/suggestions.py`) is deliberately built so **product identity
travels as a stable registry primary key, never re-derived from the typed
string** — the visible search box is not a form field; a hidden
`ModelChoiceField` carries a `Product.id` set by JS the moment a suggestion is
picked, and the server resolves it by primary key, never by name. Substance
resolution is equally solid at the single-product level: `nazwaSubstancji` is
the one authoritative XML field, a denylist keeps three known placeholder
strings out of the `Substance` table (checked twice, independently), and a
multi-substance product is N real `ProductSubstance` rows, not a derived list.
Resolution failure is not swallowed: an item with zero substance links is
still saved, flagged with a distinct warning message and a distinct list-page
section, and a duplicate-classification guard (`classify()`) explicitly
refuses to compare two empty substance sets — closing exactly the "empty set
== empty set" trap the risk describes.

Three gaps survive this design and are all still open in the live code
today, not just historically:

1. **The suggestion/save path is untested end-to-end for the actual collision
   shape risk #1 describes.** When two `Product` rows share
   `(name, strength, pharmaceutical_form, marketing_holder)` but disagree on
   substance links (documented in the code's own comment as ~1.24% of groups —
   `registry/suggestions.py:58-60`), the presentation-builder's tiebreak picks
   one by `registry_id` ordering, silently. `producer_confirmed` only records
   that the user disambiguated by *manufacturer*; it cannot and does not
   record this deeper case. No test drives an actual `pharmacy:item_add` POST
   through this shape and asserts which product (and which substances) got
   persisted.
2. **`item_add` has a genuine, unguarded N+1** that re-reads
   `product.substance_links.all()` three separate times with no prefetch
   (once for the flash message, twice more inside `check_candidate`), costing
   14–17+ queries and scaling with substance count. No `assertNumQueries`
   exists for this view anywhere, unlike `item_list` and the suggestions
   endpoint, which both pin `assertNumQueries(7)`.
3. **An unresolved item and a genuinely substance-free item remain the same
   stored state** (`Item.unresolved` is a derived property reading an empty
   `substance_links` relation, by deliberate design against boolean drift on
   re-import) — mitigated only by `classify()`'s empty-set guard, never by a
   stored distinguishing fact.

## Detailed Findings

### Risk #1 — Product identity through the suggestion and save path

**Suggestion endpoint.** `pharmacy/urls.py:11` routes `suggestions/` to
`pharmacy/views.py:42-61` (`product_suggestions`), which returns JSON with
`name, strength, form, substances, default_product_id, producers` per
presentation — each `producers` entry carrying `holder` + `product_id`
(pinned by `pharmacy/tests/test_suggestions_endpoint.py:52-55`). The grouping
and tiebreak logic lives in `registry/suggestions.py`:

- `Presentation`/`Producer` dataclasses (`registry/suggestions.py:20-33`).
- `search_presentations` groups active products by
  `(name, strength, pharmaceutical_form)` in SQL, then by `marketing_holder`
  within a group (`registry/suggestions.py:83-133`).
- `_default_product` (`registry/suggestions.py:36-48`): prefers a row with at
  least one substance link, tiebreaks on `registry_id` (the registry's own
  string key, lexicographic — explicitly *not* database pk, since re-imports
  don't reproduce pks).
- `_build_presentation`'s own comment (`registry/suggestions.py:54-61`) states
  the residual risk directly: producers are emitted one per distinct holder,
  not per row, "and in the 1.24% of groups whose rows disagree on substances
  they resolve to different substance sets."

**Form and save path.** `pharmacy/forms.py:8-24` (`ItemAddForm`): `product`
is a `ModelChoiceField` with `widget=HiddenInput`; `producer_confirmed` is a
`BooleanField` with `widget=HiddenInput`. `Meta.fields = ('product',
'producer_confirmed')` — there is no name field on the form or on `Item` at
all. The visible free-text `#product-search` input in
`pharmacy/templates/pharmacy/item_form.html:16-31` is not part of the form;
only the two hidden fields (plus a display-only `search_text`) are posted.
`pharmacy/views.py:64-109` (`item_add`): `ItemAddForm(request.POST)` →
`ModelChoiceField.clean` resolves `product` by primary key against
`Product.objects.filter(is_active=True)` — a pk lookup, never a re-query by
name. `search_text` (line 104) is read only to re-populate the form on
validation failure; it is never assigned to the model.

**Client-side wiring.** `pharmacy/static/pharmacy/js/autocomplete.js:37-64`
(`pickPresentation`) sets the hidden `product` field to
`presentation.default_product_id` the instant a suggestion is picked; if the
presentation has more than one producer, the `producer-select` `change`
handler (`autocomplete.js:66-75`) overwrites that value with the chosen
`producer.product_id`. Per the archived plan
(`context/archive/2026-08-14-add-drug-with-substance-resolution/plan.md`
§Phase 3.4, shipped 3.10), editing the search text after a pick clears both
hidden fields, so a stale id can never be submitted alongside edited text.

**Models.** `pharmacy/models.py:15-51` (`Item`): `product` is a `ForeignKey`
to `registry.Product` (`on_delete=PROTECT`); no name/strength/form is stored
on `Item` — substances are always read live through
`item.product.substance_links`. `registry/models.py:40-64` (`Product`):
`registry_id` (unique string, the registry's own stable key) versus Django's
auto-increment `id` — it is the auto `id` that is actually passed through the
hidden field and JSON payload, not `registry_id`.

**Test coverage gap.** `pharmacy/tests/test_item_add.py` exercises the save
path with exactly one product per test; it proves household scoping,
`producer_confirmed` handling, and that an inactive product id is rejected —
but never posts an id chosen from a two-row-same-name group and checks which
row got saved. The collision fixture that *does* exist
(`registry/tests/test_suggestions.py:80-97,151-167` — the "Sortis 20" shape:
two rows, same name/strength/form/holder, disagreeing substances) lives
entirely inside `registry`, one layer below `pharmacy:item_add`. **No test
anywhere combines a name/strength/form/manufacturer collision with an actual
`item_add` POST and an assertion on the persisted `Item.product_id` /
resulting substances.**

### Risk #3 — Substance resolution correctness

**Authoritative source field.** `registry/parser.py:166` reads the
`nazwaSubstancji` XML attribute on each `<substancjaCzynna>` element,
iterated per product at `registry/parser.py:165` via
`elem.iter(substance_tag)` (`substance_tag = {ns}substancjaCzynna`,
`registry/parser.py:145`). Amount/unit companion fields: `iloscSubstancji`,
`jednostkaMiaryIlosciSubstancji`, `iloscPreparatu`,
`jednostkaMiaryIlosciPreparatu`, `innyOpisIlosci`
(`registry/parser.py:181-185`).

There is a secondary, explicitly *inferred* path: when a product has zero
substance rows, `nazwaPowszechnieStosowana` (the product's "common name",
`registry/parser.py:317`) is used as a fallback substance name only if that
exact casefolded string independently appears as a `nazwaSubstancji` value
elsewhere in the file (`_resolve_deferred`, `registry/parser.py:263-310`).
This inferred link is tagged `SourceField.COMMON_NAME`, distinct from the
authoritative `SourceField.SUBSTANCE_ROW` (`registry/models.py:11-23`) — the
data model itself records provenance, so an inferred link is never presented
as a directly-stated fact.

**Multi-substance representation.** Not a list field on `Product` — N linked
rows. `ParseResult.ProductRecord.links: tuple[SubstanceLinkRecord, ...]`
(`registry/parser.py:98`), one `SubstanceLinkRecord` per kept row
(`registry/parser.py:175-190`), persisted as the `ProductSubstance`
through-model (`registry/models.py:67-105`) — `ForeignKey` to `Product`
(CASCADE) and `ForeignKey` to `Substance` (PROTECT), deliberately **without**
a unique constraint on `(product, substance)`: 89 real rows repeat a
substance at a different amount (confirmed by the "Altacet" fixture,
`registry/tests/test_parser.py:66-73`).

**Denylist filtering.** `registry/denylist.py:32-38` defines
`DENYLISTED_SUBSTANCE_KEYS = {'produkt złożony', 'preparat złożony', 'wyciągi
alergenowe'}`, exact-match on casefolded key — no prefix/substring matching
(a near-miss like `wyciągi alergenowe roztoczy kurzu domowego` correctly
survives, per `DenylistTests`, `registry/tests/test_parser.py:235-265`).
Applied at parse time, in two independent places: explicit rows
(`registry/parser.py:174`, filtered before links are built) and the
common-name fallback (`registry/parser.py:287`). This was not always the
case — see Historical Context below for the near-miss where a first version
of the loader contract would have inserted a permanent zero-link `Substance`
row for a denylisted placeholder.

Important nuance: the denylist does **not** keep these strings out of the
internal `vocabulary` accumulator (`registry/parser.py:170`, unconditional
`setdefault`, built file-wide including denylisted and veterinary-product
names) — only out of emitted `links`, and therefore out of
`ParseResult.substances` (`registry/parser.py:207-211`) and the `Substance`
table (`registry/loader.py:118-139` inserts only from `result.substances`).
The module and denylist docstrings state this is intentional — checked twice
because a vocabulary-only filter would let the fallback path reintroduce a
denylisted name. `registry/loader.py` and `registry/admin.py` (fully
read-only — `has_add_permission` returns `False` everywhere,
`registry/admin.py:58-79`) never construct `Substance`/`ProductSubstance`
rows independently of `ParseResult`, so there is no second path around either
check.

**Call path into pharmacy.** `pharmacy/duplicates.py:35-47`
(`substance_keys`) reads `product.substance_links.all()` into a
`frozenset[str]` of `name_key`. Used by `build_list_view`
(`pharmacy/duplicates.py:160`, backing `pharmacy/views.py:34`'s `item_list`)
and `check_candidate` (`pharmacy/duplicates.py:333,352`, backing
`pharmacy/views.py:94`). `Item.product` (`pharmacy/models.py:29-33`) is the
sole join point between `pharmacy` and `registry` — `households/models.py`
has no direct link to registry data.

**Test coverage.** `registry/tests/test_parser.py` plus
`registry/tests/fixtures/README.md` cover the multi-substance case
explicitly (Vaminolact: 19 links; Altacet: repeated substance at different
amounts; Peditrace: 7 links with free-text amount). The fixture is verbatim
XML spliced from the live registry, not synthetic, with expected counts
documented and cross-checked (`registry/tests/fixtures/README.md:3-5`) — no
test found anywhere whose expected value is merely "whatever the parser
currently outputs."

**Residual gap.** `products_without_links` (used to find unresolved items)
conflates "genuinely undocumented by the registry" with "denylist-blocked" —
a household item on a denylisted-only product looks identical to one the
registry simply never documented. Not currently a proven bug, but a sharp
edge for any future logic that treats "0 links" as a data-quality signal to
act on.

### Risk #4 — Resolution-failure handling and the query-shape gate

**Save-path behaviour on a lookup miss.** There is no try/except anywhere in
`item_add` (`pharmacy/views.py:64-109`) — confirmed by grep across
`pharmacy/` (the only `try`/`except` hits are in an unrelated template
filter). That's structural, not an oversight: resolution is a read of
already-imported rows (`item.product.substance_links.all()`), not a live
lookup that can raise. The item is saved (line 73) **before** substances are
read at all (lines 74-76); an empty result branches to
`messages.warning(...)` instead of `messages.success(...)` (lines 77-87), and
the request still redirects to `item_list` exactly like the success path —
confirmed directly by reading `pharmacy/views.py:64-109` and pinned by
`pharmacy/tests/test_item_add.py:115-126`
(`test_unresolved_product_still_creates_item_and_warns`).

**Representation of "unresolved."** `Item.unresolved`
(`pharmacy/models.py:53-61`) is a derived property: `not
self.product.substance_links.all()`. There is no stored field. This is a
deliberate choice recorded in the archived plan
(`context/archive/2026-08-14-add-drug-with-substance-resolution/plan.md:208-210`):
*"'Unresolved' is derived, never stored ... a stored boolean would silently
drift out of date the first time a re-import adds links to a product a user
already saved."* Consequence: an unresolved item and a genuinely
substance-free item are the *same stored state* today — precisely the
ambiguity `test-plan.md`'s risk-response row for #4 calls out. Two mitigating
facts: (a) in this domain there is arguably no real "substance-free human
medicine" — the registry's own parser treats zero links as a data/parsing
gap, not a fact, so the conflation may be lower-stakes than it looks; (b) the
schema still gives no way to *prove* that if it's ever wrong.

**Duplicate-grouping guard.** `pharmacy/duplicates.py:50-64` (`classify`)
returns `Overlap.NONE` whenever either side's substance set is empty, checked
*before* the equality test — its own docstring names the exact failure this
prevents: `frozenset() == frozenset()` is `True` in Python, so without the
guard every unresolved item would classify as a full duplicate of every
other unresolved item. `build_list_view` additionally partitions
resolved/unresolved items before grouping (`pharmacy/duplicates.py:140-202`),
and `check_candidate` counts unresolved items separately via
`uncomparable_count` rather than silently matching them
(`pharmacy/duplicates.py:311-395`). This guard was mutation-tested when it
was written — see Historical Context.

**What the user actually sees.** Success: a green message naming the
substances (`pharmacy/views.py:78-81`). Resolution failure: a yellow warning
(`pharmacy/views.py:83-87`), then on the list page a distinct "Nie udało się
ustalić substancji" section (`pharmacy/templates/pharmacy/item_list.html:38-47`)
with a "Dodaj ponownie" recovery link instead of a substance list
(`pharmacy/templates/pharmacy/_item_row.html:25-26`). A genuine
zero-substance product (if one exists) would render identically — no UI
distinguishes the two cases, consistent with them being the same stored
state.

**Existing test.** `pharmacy/tests/test_item_add.py:115-126` is the only
add-flow test for this scenario; it asserts the `Item` *is* persisted and a
warning message is present — not merely an HTTP 200. No test in this file
exhibits the "assert 200 and nothing else" anti-pattern the test plan warns
against.

**Query-shape assertion — the "one query-shape assertion" Phase 2 must add.**
Every existing `assertNumQueries` usage in the repo:
`pharmacy/tests/test_item_list.py:128,329,468` (`assertNumQueries(7)`,
guarding `item_list`'s prefetch contract) and
`pharmacy/tests/test_suggestions_endpoint.py:138` (`assertNumQueries(7)`).
`pharmacy/tests/test_product_check.py:452-464` deliberately *avoids*
`assertNumQueries`, instead comparing `CaptureQueriesContext` counts at two
household sizes, with an explicit rationale: a hardcoded literal would pass
without ever observing whether the count actually depends on household size.

**No `assertNumQueries` guard exists for `item_add`.** Direct code reading
confirms a genuine, unguarded N+1: `item.product.substance_links.all()` is
read three separate times with no caching or prefetch —
`pharmacy/views.py:75` (for the flash message), then
`pharmacy/duplicates.py:333` and `:337` again inside `check_candidate`'s
`substance_keys(candidate)` call and its own follow-up read for display
names. `ItemAddForm`'s queryset (`pharmacy/forms.py:8-24`) has no
`select_related`/`prefetch_related`, unlike `ProductCheckForm`
(`pharmacy/forms.py:45-48`), which explicitly prefetches
`substance_links__substance` for exactly this reason. Empirically measured
against the test DB: 14 queries for a resolved product with 1 substance and
an empty household, flat at 16 once ≥1 other item exists (confirming
`other_items` at `pharmacy/views.py:88-93` is itself correctly
prefetched/scoped and does not grow with household size), and 17 with 2
substances. **The count scales with substance count** — a naive
`assertNumQueries` pinned today would either encode this bug as a fixed
number or need the N+1 fixed first (e.g. prefetching `item.product`'s
substance links once and reusing the result for both the message and
`check_candidate`) before a flat, substance-count-independent count can be
asserted.

## Code References

- [`pharmacy/views.py#L64-L109`](https://github.com/tszreder/domowa-apteka/blob/fea2a2ad7404529ddff58c494c8a8b7cbb34cc02/pharmacy/views.py#L64-L109) — `item_add`: save-before-resolve ordering, no try/except, N+1 substance reads
- [`pharmacy/views.py#L42-L61`](https://github.com/tszreder/domowa-apteka/blob/fea2a2ad7404529ddff58c494c8a8b7cbb34cc02/pharmacy/views.py#L42-L61) — `product_suggestions` JSON contract
- [`pharmacy/forms.py#L8-L24`](https://github.com/tszreder/domowa-apteka/blob/fea2a2ad7404529ddff58c494c8a8b7cbb34cc02/pharmacy/forms.py#L8-L24) — `ItemAddForm`: hidden pk-based `product` field, no name field
- [`pharmacy/forms.py#L45-L48`](https://github.com/tszreder/domowa-apteka/blob/fea2a2ad7404529ddff58c494c8a8b7cbb34cc02/pharmacy/forms.py#L45-L48) — `ProductCheckForm`'s prefetch, contrast with `ItemAddForm`
- [`pharmacy/models.py#L15-L61`](https://github.com/tszreder/domowa-apteka/blob/fea2a2ad7404529ddff58c494c8a8b7cbb34cc02/pharmacy/models.py#L15-L61) — `Item` model, `unresolved` derived property
- [`pharmacy/duplicates.py#L35-L64`](https://github.com/tszreder/domowa-apteka/blob/fea2a2ad7404529ddff58c494c8a8b7cbb34cc02/pharmacy/duplicates.py#L35-L64) — `substance_keys`, `classify`'s empty-set guard
- [`pharmacy/duplicates.py#L311-L353`](https://github.com/tszreder/domowa-apteka/blob/fea2a2ad7404529ddff58c494c8a8b7cbb34cc02/pharmacy/duplicates.py#L311-L353) — `check_candidate`, the second and third substance-link reads
- [`registry/suggestions.py`](https://github.com/tszreder/domowa-apteka/blob/fea2a2ad7404529ddff58c494c8a8b7cbb34cc02/registry/suggestions.py) — presentation grouping, `_default_product` tiebreak, and the code's own comment naming the 1.24% disagreeing-rows case (`L54-L61`)
- [`registry/models.py#L11-L64`](https://github.com/tszreder/domowa-apteka/blob/fea2a2ad7404529ddff58c494c8a8b7cbb34cc02/registry/models.py#L11-L64) — `Product`, `SourceField`, `ProductSubstance`
- [`registry/parser.py#L145-L211`](https://github.com/tszreder/domowa-apteka/blob/fea2a2ad7404529ddff58c494c8a8b7cbb34cc02/registry/parser.py#L145-L211) — authoritative field read, link building, `ParseResult.substances` filtering
- [`registry/parser.py#L263-L317`](https://github.com/tszreder/domowa-apteka/blob/fea2a2ad7404529ddff58c494c8a8b7cbb34cc02/registry/parser.py#L263-L317) — common-name fallback (`_resolve_deferred`)
- [`registry/denylist.py`](https://github.com/tszreder/domowa-apteka/blob/fea2a2ad7404529ddff58c494c8a8b7cbb34cc02/registry/denylist.py) — placeholder-substance denylist, exact-match, checked twice
- [`registry/loader.py#L118-L139`](https://github.com/tszreder/domowa-apteka/blob/fea2a2ad7404529ddff58c494c8a8b7cbb34cc02/registry/loader.py#L118-L139) — loader inserts only from `result.substances`
- [`pharmacy/static/pharmacy/js/autocomplete.js#L37-L75`](https://github.com/tszreder/domowa-apteka/blob/fea2a2ad7404529ddff58c494c8a8b7cbb34cc02/pharmacy/static/pharmacy/js/autocomplete.js#L37-L75) — pick/producer-select client wiring of the hidden `product` field
- [`pharmacy/tests/test_item_add.py#L115-L126`](https://github.com/tszreder/domowa-apteka/blob/fea2a2ad7404529ddff58c494c8a8b7cbb34cc02/pharmacy/tests/test_item_add.py#L115-L126) — `test_unresolved_product_still_creates_item_and_warns`
- [`registry/tests/test_suggestions.py#L80-L167`](https://github.com/tszreder/domowa-apteka/blob/fea2a2ad7404529ddff58c494c8a8b7cbb34cc02/registry/tests/test_suggestions.py#L80-L167) — the existing "Sortis 20" collision fixture, one layer below `item_add`
- [`pharmacy/tests/test_item_list.py#L128`](https://github.com/tszreder/domowa-apteka/blob/fea2a2ad7404529ddff58c494c8a8b7cbb34cc02/pharmacy/tests/test_item_list.py#L128) — existing `assertNumQueries(7)` pattern to follow
- [`pharmacy/tests/test_product_check.py#L452-L464`](https://github.com/tszreder/domowa-apteka/blob/fea2a2ad7404529ddff58c494c8a8b7cbb34cc02/pharmacy/tests/test_product_check.py#L452-L464) — why this test deliberately avoids `assertNumQueries` in favour of a two-size comparison

## Architecture Insights

- **Derive, never copy, across the registry boundary.** Both `Item.unresolved`
  and every substance read in `pharmacy` go live through `product.
  substance_links`, never a cached/copied value — an explicit NFR-driven
  choice so a re-import can't leave a stale substance shown, but it also
  means every substance-touching code path is a potential N+1 unless the
  caller prefetches, and nothing currently enforces that discipline for
  `item_add`.
- **Identity settled by pk before any substance comparison.**
  `check_candidate`'s docstring (`pharmacy/duplicates.py:319-327`) states the
  principle directly: `item.product_id == candidate.pk` is checked
  independently of substance comparison, because a primary key the registry
  assigned is stronger evidence than a derived substance set — and this
  still gives a useful answer when substance resolution has failed on either
  side. The same "pk is the identity, substances are a derived fact"
  discipline is what makes the risk #1 hidden-field design sound.
  Consistency check: risk #1's fix (stable pk) and risk #4's mitigation
  (identity survives resolution failure) share this one architectural
  decision.
- **Provenance is a first-class field, not a comment.** `SourceField`
  (`registry/models.py:11-23`) distinguishes a directly-stated substance link
  from an inferred one at the data-model level — this is what lets the
  common-name fallback exist at all without becoming indistinguishable from
  authoritative data.
- **Denylist-as-safety-net is checked at every emission point, not once at a
  chokepoint.** Two independent checks (explicit rows, fallback path) rather
  than one shared filter — the module docstring states this was a deliberate
  reaction to a near-miss (see Historical Context) where a single vocabulary
  filter would have been insufficient.
- **Guard placement matters more than the guard's existence.** `classify`'s
  empty-set check is placed *before* the equality test specifically because
  Python's `frozenset() == frozenset()` is vacuously `True` — a lesson this
  project already learned once (mutation-tested when written, see below) and
  a pattern worth re-checking anywhere else two sets are compared for
  equality with "empty" as a real, reachable state.

## Historical Context (from prior changes)

- `context/archive/2026-08-14-add-drug-with-substance-resolution/plan.md`
  (S-02, archived 2026-08-19) — the origin of this whole flow.
  - Confirms the hidden pk field design, and that editing the search text
    after a pick clears the hidden `product` id and `producer_confirmed`
    together, so a stale id can never ride along with edited text
    (§Phase 3.4, shipped 3.10).
  - **Accepted, still-open limitation**: the default-product tiebreak
    (prefer a row with substance links, else lowest `registry_id`) is
    explicitly flagged as "one of two defensible answers, not correct" —
    salt-form variants (e.g. `atorvastatinum` vs `atorvastatinum calcicum`)
    defeat substance-set equality in 201/16,191 groups (1.24%). Merging them
    was ruled out as "inferring an identity the source doesn't state." This
    is the same 1.24% figure `registry/suggestions.py:58-60`'s own comment
    still cites today — **never revisited by a later change**.
  - Confirms risk #4's guardrail was a deliberate PRD-driven design from the
    start ("a lookup failure is never silent"), not a later patch.
  - Review finding **F7**: an earlier draft offered one producer option *per
    row* rather than per distinct holder, which would have offered 28
    indistinguishable options for one product (`Concor Cor 2,5` across 8
    real holders) — found and fixed before archiving.
- `context/archive/2026-08-07-registry-substance-data/` (F-01, archived
  2026-08-14) — the origin of the denylist.
  - `options.md` §8a: identified `Produkt złożony` (28 rows + 22 via
    fallback), `Preparat złożony` (3), `Wyciągi alergenowe` (4) as literal
    substance-name values that, if loaded verbatim, would make 78 products
    mutually "duplicates" of each other on a fake shared substance.
  - **Near-miss caught during implementation** (impl-review F6, corrected
    2026-08-16): the loader's first vocabulary-accumulation contract would
    have inserted a permanent zero-link `Substance` row for every name
    reaching the internal vocabulary — including denylisted placeholders.
    Narrowed so `ParseResult.substances` only carries names an emitted,
    non-denylisted link actually points at. This is the incident behind
    `context/foundation/lessons.md`'s "a plan can contradict itself" entry
    — resolved, not open.
  - Two parser rules ("common-name fallback actually firing", "denylist
    blocking anything") were initially unobservable by the 8-product test
    fixture; both gaps were closed within the same change by extending the
    fixture with dedicated cases — resolved, not open.
- `context/archive/2026-08-24-duplicate-flagging-on-list/` (S-03, archived
  2026-08-25) — origin of `classify`'s empty-set guard, named there as
  preventing "the exact outcome US-03's acceptance criteria forbid," and
  mutation-tested at authoring time (reordering the guard made
  `classify(frozenset(), frozenset())` return `FULL`; confirmed to fail;
  reverted). No mutation-dead or unfalsifiable test was found there regarding
  product identity — the one correction on record was a test-design fix (an
  originally-planned test case was unrepresentable because `name_key` has a
  unique constraint; replaced with an equivalent representable case).
- `context/archive/2026-09-05-ux-audit-and-flow-fixes/` (S-06, archived
  2026-09-06) — four shipped fixes directly on this flow: **F-14** (picking
  no suggestion produced the wrong field's error and wiped typed input —
  fixed with a client-side submit gate), **F-16** (resolved substances
  weren't shown until after saving despite being in the API response already
  — fixed with a preview), **F-19** (two suggestions could look identical —
  same name/strength/form, different holder, e.g. `APAP` vs `Apap` — fixed by
  adding holder to the suggestion label), **F-27** (unresolved items were a
  dead end with no retry path — fixed with a recovery link). All shipped;
  none reopen a risk #1/#3/#4 gap.
- `context/foundation/roadmap.md` — S-02's "Unknown 1" (the autocomplete
  disambiguation question) is answered by the archived plan above but is
  **never struck through as resolved** in the roadmap document itself,
  unlike other resolved unknowns in the same table. A documentation
  bookkeeping gap, not a functional one — worth a one-line roadmap edit but
  not a Phase 2 test target.

## Related Research

- `context/foundation/test-plan.md` §2 (Risk Map, rows #1/#3/#4) and §3
  (Phase 2 row) — the governing document this research answers into.
- `context/changes/testing-coverage-truth-pass/` (Phase 1, not started as of
  this writing) — once that phase produces its risk-to-test map, it will be
  the place to check whether any *existing* assertion claiming to protect
  risks #1/#3/#4 can actually fail; this research does not duplicate that
  audit, it grounds what Phase 2 needs to build new.

## Open Questions

These are decisions for `/10x-plan`, not settled here:

1. **Is the "Sortis 20" collision shape (same name/strength/form/holder,
   disagreeing substances — the 1.24% case) in scope for Phase 2, or is it an
   accepted limitation like the archived plan already treats the
   cross-product salt-form case?** The two are related but distinct: the
   1.24% figure in the archived plan is about *duplicate-detection* set
   equality across different products (risk #7 / Phase 5 territory); the
   `registry/suggestions.py` tiebreak gap is about *which single product* a
   presentation resolves to *before* the user's own manufacturer choice even
   applies (risk #1 / this phase). If Phase 2 decides this is in scope, the
   fixture already exists one layer down
   (`registry/tests/test_suggestions.py:151-167`) and needs only to be driven
   through an actual `item_add` POST with a persistence assertion. If
   out of scope, it should be recorded as an accepted limitation the same way
   the salt-form case already is, so a future reader doesn't rediscover it as
   new.
2. **Should the `item_add` N+1 be fixed before or as part of writing the
   query-shape assertion?** A `assertNumQueries` pinned against today's
   behaviour would encode a count that scales with a product's substance
   count — the same anti-pattern `test_product_check.py` was deliberately
   written to avoid. The cheap fix (read `item.product.substance_links.all()`
   once, into a local variable, and pass the result to both the message
   builder and `check_candidate` instead of re-querying) looks small enough
   to be in scope for this phase rather than deferred.
3. **Does risk #4 need a stored distinguishing fact, or is the derived
   property plus `classify`'s guard sufficient protection?** The archived
   plan rejected a stored boolean specifically to avoid drift on re-import.
   Phase 2 should decide whether the existing guard is the intended
   permanent answer (in which case the test to write is: prove the guard
   holds, via mutation, the same way it was proven when written) or whether
   the test-plan's risk-response wording ("must not be the same stored
   state") implies a schema change is actually wanted.
