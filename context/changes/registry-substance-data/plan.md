# Registry-backed product and active-substance data — Implementation Plan

## Overview

Build a new Django app, `registry`, that loads human-use medicinal products and their
active substances from the Polish national registry's daily `overall.xml` snapshot into
local tables, via one idempotent management command. Every substance link records **how**
it was resolved, so a downstream slice can show the user where a resolution came from and
never present an inferred link as a stated one.

This is roadmap item **F-01**. It unlocks **S-02** (the north star: type a product name,
see its active substances) and establishes the provenance rule **S-03**'s duplicate
comparison depends on.

## Current State Analysis

- **No registry code exists.** `INSTALLED_APPS` holds `django.contrib.*` plus one app,
  `households` (`domowa_apteka/settings.py:74-82`). There are no management commands
  anywhere in the repo.
- **The research is done and measured.** `context/changes/registry-substance-data/options.md`
  answers both of the roadmap's F-01 unknowns against the live registry as of 2026-08-07:
  the bulk XML is the only public interface (the JSON API returns
  `403 ACCESS_DENIED_EXCEPTION`; the incremental feed was deliberately retired by the
  publisher), so **full-snapshot replace is the only supported ingestion mode**. Parse cost
  is **9.9 s / 7 MB peak** with `iterparse` + `elem.clear()`.
- **The source data is clean.** Zero leading/trailing-whitespace defects and 5 case-only
  collisions across 4,267 distinct substance names. `.strip()` + `.casefold()` do the whole
  normalization job. This closes the open LLM question in
  `context/foundation/tech-stack.md` — **`has_ai: false` stays false**.
- **Existing patterns to follow.** `households/models.py` — typed models, explicit return
  annotations, `__str__` on every model. `households/admin.py` — one `@admin.register`
  block per model with `list_display`. `households/tests/` — a package of `test_*.py`
  modules with `TestCase` subclasses, each test method annotated `-> None`.
- **CI is strict.** `.github/workflows/deploy.yml:49` runs `uv run mypy`, and
  `pyproject.toml:22` scopes it to `["households", "domowa_apteka"]`. A new app that is not
  added to that list is silently un-type-checked while CI stays green.
- **Production ops are constrained.** `context/deployment/deploy-plan.md:248-266` records
  that `railway run` executes locally (and `DATABASE_URL` points at the unreachable
  `postgres.railway.internal`), and `railway ssh` holds a TTY so it cannot be agent-driven — and
  was never confirmed to reach this container at all (`deploy-plan.md:269-277`), which is why
  Phase 4 does not use it.
  Neither `docker` nor `psql` is on the local PATH (checked during planning), so there is no
  throwaway local Postgres available either.

## Desired End State

`uv run python manage.py import_registry --file <path>` (or, with no `--file`, against the
URL in `REGISTRY_OVERALL_URL`) populates three tables with the human-use portion of the
registry snapshot. Running it a second time on the same input leaves the database in an
identical state. Every `ProductSubstance` row carries a `source_field` value stating whether
it came from an explicit `<substancjaCzynna>` element or from the product's common name via
the vocabulary-grounded fallback. `/admin/registry/product/` lets a human search the loaded
data and cannot modify it.

Verify by: running the command twice against the test fixture and diffing the resulting
rows; running `uv run mypy` and `uv run python manage.py test`; and loading
`/admin/registry/product/` in a browser.

### Key Discoveries

- **`(product, substance)` is not unique.** 89 excess rows across 29,064 legitimately repeat
  a substance on the same product at different amounts — e.g. `Altacet` lists
  `Aluminii acetotartras` twice (`sample-products.xml:59-60`). A `unique_together` on the
  through-table would fail against real data. (options.md §3)
- **Placeholder values are used as real substance names.** `Produkt złożony` appears as a
  `nazwaSubstancji` on 28 products, `Preparat złożony` on 3, `Wyciągi alergenowe` on 4.
  Loaded as ordinary substances, every product carrying `Produkt złożony` becomes a
  full-substance-set duplicate of every other one — **78 products mutually flagged as
  identical medicines** in S-03. This is the highest-severity finding in the research: it
  produces confidently wrong output rather than a visible failure, and it exists with **no
  fallback at all**. (options.md §8a)
- **Strength is already decomposed by the source.** Amounts live in sibling attributes
  (`iloscSubstancji` + `jednostkaMiaryIlosciSubstancji`, or free-text `innyOpisIlosci`),
  never inside `nazwaSubstancji`. Only 6 of 29,064 names embed a number at all. **No string
  splitting is needed and none should be attempted.** Values are Polish-formatted with a
  decimal comma (`3,13`, `521,00 mcg`), so `float()` raises or truncates. (options.md §8b)
- **The E1 vocabulary forward-references.** Verified during planning against the fixture: the
  product whose substance row validates another product's common-name fallback can appear
  *later* in the file. `Beto 200 ZK` (product 6 of 8) needs `Metoprololi succinas` to exist
  as a substance row somewhere; in the 8-product fixture it does not, so the fallback
  correctly declines. **The fallback cannot be decided while streaming forward.**
- **The fixture cannot currently exercise two of the three highest-risk rules.** Measured
  during planning: none of the fixture's 33 substance names is denylisted, and no
  substance-less product's common name is in its vocabulary. So as it stands
  `sample-products.xml` proves the E1-*negative* path only. options.md §10's claim that it is
  ready for all edge cases is not accurate on these two points.
- **Leaflet URLs hide behind two attribute names.** Normal products carry `ulotka` +
  `charakterystyka`; parallel-import products (`typProcedury="IR"`, e.g. `Beto 200 ZK` at
  `sample-products.xml:225`) carry `ulotkaImportRownolegly` +
  `oznaczenieOpakowanImportRownolegly` instead. A plain `elem.get('ulotka')` silently returns
  `None` for that entire population.
- **`bulk_create` PK population on Postgres is inferred, not measured.** options.md §9
  measured it on in-memory SQLite 3.45.1 and reasons that Postgres behaves the same. Per
  `context/foundation/lessons.md`, that stays unverified — so this plan removes the
  dependency entirely rather than designing around the claim (see Critical Implementation
  Details).

## What We're NOT Doing

- **No veterinary products.** Filtered out at parse time on the source-stated
  `rodzajPreparatu` field. 2,636 products excluded.
- **No ATC codes, no packages/GTIN.** Barcode scanning is an explicit PRD Non-Goal, and ATC
  cannot decompose a combination product into a substance set, so it cannot serve S-03.
- **No `ImportRun` / snapshot model.** Freshness lives on the product as `last_seen_as_of`.
  F-02 owns the run record and the scheduler.
- **No scheduling, no cron, no refresh automation.** That is F-02 in its entirety.
- **No autocomplete, no search index, no views, no URLs.** That is S-02.
- **No duplicate detection.** That is S-03.
- **No delta/diff pipeline.** The publisher retired the incremental feed on purpose and the
  `status` attribute is absent on all 22,823 products. There is no delta signal to consume.
- **No lemmatization or substance-name inference.** `Bisoprololi` → `Bisoprolol` would invent
  an identity the source does not state — banned by the NFR.
- **No `+`-splitting of multi-substance name strings.** 8 rows of 29,064 pack several names
  into one string, and they are not safely splittable: `Vaccinum Hepatits A+B` is genuinely
  two, but `Autologiczna frakcja… CD34+…` has `+` as part of the identifier.
- **No parsing of the product-level `moc` field.** It is free text
  (`(17,51 g + 3,276 g + 3,13 g)/butelkę`). Stored and displayable; never treated as data.
- **No `defusedxml`.** The source is a trusted government HTTPS endpoint and `iterparse` does
  not expand external entities by default on modern CPython. Recorded as a conscious decision.

## Implementation Approach

Three layers, deliberately separated so the correctness-critical logic is fully offline:

1. **Models** own the shape and the provenance fields. Nothing clever.
2. **A pure parser** turns a file path into typed records. It owns the human-use filter, the
   denylist, and the E1 fallback — i.e. **every rule that touches the NFR's "no inferring"
   line**. It has no database and no network, so all of it is testable against a fixture.
3. **A loader** takes those records and writes them. It is deliberately dumb: it never
   decides what a substance is, only where rows go.

The load is a snapshot upsert keyed on the registry's own product `id`, wrapped in one
transaction. Products absent from the snapshot are marked inactive rather than deleted,
because S-02 will put user items behind foreign keys to `Product` and a delete would cascade
into user data on a routine refresh.

## Critical Implementation Details

**Deferred fallback resolution.** The E1 fallback asks "is this product's common name used as
a substance name *somewhere in this file*?" — and the validating product may appear after the
one that needs it (verified against the fixture during planning). The parser therefore does a
single streaming pass that (a) accumulates the substance-name vocabulary and (b) sets aside
substance-less products, then resolves the set-aside products after the file is exhausted.
Do not attempt this with a forward-only decision, and do not pay for a second full pass —
options.md §8c measures only ~1,054 products needing deferral, which is trivial to hold in
memory.

**`elem.clear()` is load-bearing, not an optimization.** It is the difference between the
measured 7 MB peak and roughly 1 GB resident, which would OOM on Railway. Clear each
`produktLeczniczy` element after reading it — including the ones the human-use filter
rejects, which are otherwise the easy ones to forget.

**Do not depend on `bulk_create` returning primary keys.** Between the product upsert and the
link insert, build the id map explicitly with
`dict(Product.objects.values_list('registry_id', 'pk'))` — measured at 0.02 s in options.md
§9. This makes the loader correct on any backend and means the plan carries no unverified
engine-behaviour claim, per `context/foundation/lessons.md`.

**Case-fold merging is load-order dependent.** `name_key = name.strip().casefold()` merges the
5 known case-collision pairs (`Sodu fluorek` / `sodu fluorek`), but which verbatim `name` is
displayed depends on which row is parsed first. Pin the tiebreak explicitly — first-seen-wins
is fine — so a reordered snapshot cannot silently flip a displayed name.

**mypy will fight the parser.** Once `"registry"` is in `[tool.mypy] files`, every
`elem.get('nazwaSubstancji')` types as `str | None`. Write one typed accessor helper that
takes an element and an attribute name and returns `str` (empty string for absent), and route
every attribute read through it. The alternative is dozens of `# type: ignore` comments or a
red CI job.

**`ulotka` has a parallel-import variant.** Read `ulotka` with a fallback to
`ulotkaImportRownolegly`, and `charakterystyka` with a fallback to
`oznaczenieOpakowanImportRownolegly`. Both may be absent entirely.

**The registry URL is config, not a secret — and CI must still pass.** `AGENTS.md` forbids
hardcoding a new setting, but `.github/workflows/deploy.yml` runs `manage.py check` with no
`.env` and no secrets. The shape that satisfies both: an `os.environ.get` read in
`settings.py` with the current `6.0.0` URL as the in-code default, plus a documented
`.env.example` entry. **Stated assumption: a public government URL is configuration, not a
credential**, so shipping it as a default is acceptable and keeps CI green. The env var exists
because the version path (`6.0.0`) changes on the publisher's published schedule — 5.0.0 was
retired this way and is still served — so the switch must not require a code deploy.

**The expected XML namespace is derived from the configured URL, never pinned separately.** A
hardcoded `…-v6.0.0` namespace assert would cancel the env var above: pointing
`REGISTRY_OVERALL_URL` at a 7.0.0 path — or back at the still-served 5.0.0 — would fail every
import at the assert, which is precisely the scenario the env var exists for. So
`registry/parser.py` exposes a pure `namespace_for_url(url: str) -> str` that lifts the
`v<version>` segment out of the URL and returns
`http://rejestry.ezdrowie.gov.pl/rpl/eksport-danych-v<version>`, and `parse_registry` takes the
expected namespace as an argument rather than importing settings. The management command derives
it from whichever URL is in play (`--url` if given, else `settings.REGISTRY_OVERALL_URL`) and
passes it down, so URL and namespace cannot drift apart. The assert stays hard — a 7.0.0 file
parsed as 6.0.0 must still fail loudly. Be honest about what this buys: switching versions
becomes "point it at the new URL and find out", not "free", because a 7.0.0 export could rename
elements below the root and no namespace check can rescue that.

---

## Phase 1: App scaffold, data model, and read-only admin

### Overview

Create the `registry` app and its three models, wire it into settings and the type-checker,
and give it a searchable read-only admin surface. No parsing and no network in this phase —
it ends with an empty but correct schema.

### Changes Required:

#### 1. App scaffold

**File**: `registry/` (new, via `uv run python manage.py startapp registry`)

**Intent**: Create the app package. `registry` is a separate bounded context from
`households` — reference data mirrored from an external authority, not user data.

**Contract**: Standard `startapp` layout. `registry/apps.py` sets
`default_auto_field = 'django.db.models.BigAutoField'` and `name = 'registry'`, matching
`households/apps.py`. Delete the generated `tests.py` in favour of a `registry/tests/`
package (the `households` convention).

#### 2. Models

**File**: `registry/models.py`

**Intent**: Three models holding the registry snapshot with enough provenance that any
displayed substance traces back to the source row it came from.

**Contract**:

`Substance` — the deduplicated substance vocabulary.
- `name` — `CharField(max_length=255)`, verbatim from the source (the XSD caps
  `limitedString` at 255; the longest observed name is 254 chars).
- `name_key` — `CharField(max_length=255, unique=True, db_index=True)`, the
  `.strip().casefold()` lookup key. This is the identity; `name` is the display form.

`Product` — one row per registry product, human-use only.
- `registry_id` — `CharField(max_length=32, unique=True, db_index=True)`. The registry's own
  `id` attribute; the upsert key. 22,823 distinct values observed.
- `name` — `CharField(max_length=255, db_index=True)`, `nazwaProduktu`. Indexed because S-02
  will search it and Phase 1's admin puts `search_fields` on it over ~20k rows. The flag belongs
  in the field spec, not only in this sentence — `makemigrations` reads the spec.
- `common_name` — `CharField(max_length=255, blank=True)`, `nazwaPowszechnieStosowana`.
- `strength` — `TextField(blank=True)`, `moc`. **`TextField`, not `CharField`** — observed
  values run to multi-paragraph free text (`sample-products.xml:163`).
- `pharmaceutical_form` — `CharField(max_length=255, blank=True)`,
  `nazwaPostaciFarmaceutycznej`. With `strength`, this is what S-02 disambiguates on: `Xanax`
  appears on 48 rows.
- `marketing_holder` — `CharField(max_length=255, blank=True)`, `podmiotOdpowiedzialny`.
- `kind` — `CharField(max_length=32)`, `rodzajPreparatu`. Always `ludzki` under the current
  filter; stored so the filter is auditable and can widen without a migration.
- `permit_number` — `CharField(max_length=64, blank=True)`, `numerPozwolenia`.
- `leaflet_url` / `characteristics_url` — `URLField(max_length=500, blank=True)`. See the
  parallel-import note in Critical Implementation Details.
- `last_seen_as_of` — `DateField()`, the `stanNaDzien` of the most recent snapshot containing
  this product. **This is the freshness value, and the one F-02 reads.** There is deliberately
  no second `source_as_of` column: under the loader's write rules (steps 2 and 5) it would carry
  the same date as this one on every row on every run, or silently come to mean "first snapshot
  we saw this product in" — neither of which is what this plan promises. `ParseResult.source_as_of`
  still exists as the parsed snapshot date; it is the value written *into* this column.
- `is_active` — `BooleanField(default=True)`. False once a snapshot omits the product.

`ProductSubstance` — the through-table, **deliberately without a unique constraint**.
- `product` — `ForeignKey(Product, on_delete=models.CASCADE, related_name='substance_links')`.
- `substance` — `ForeignKey(Substance, on_delete=models.PROTECT, related_name='product_links')`.
  `PROTECT`, not `CASCADE`: a substance should never disappear while links reference it.
- `amount` — `CharField(max_length=64, blank=True)`, `iloscSubstancji`. **Text, not numeric** —
  Polish decimal comma.
- `unit` — `CharField(max_length=64, blank=True)`, `jednostkaMiaryIlosciSubstancji`. Sometimes
  compound (`mg/ml`).
- `preparation_amount` / `preparation_unit` — `CharField(max_length=64, blank=True)`, the
  `iloscPreparatu` pair.
- `amount_description` — `TextField(blank=True)`, `innyOpisIlosci` free text.
- `source_field` — `CharField(max_length=32, choices=...)`, either `substance_row` or
  `common_name`. **This field is what keeps the provenance honest** and is the reason S-02 can
  show a user where a resolution came from.
- `source_order` — `PositiveSmallIntegerField()`, the 0-based position of the source element
  within its product, preserving row order for repeated substances.

**No `unique_together` on `(product, substance)`** — 89 source rows legitimately repeat.

#### 3. Settings registration

**File**: `domowa_apteka/settings.py`

**Intent**: Register the new app so its models and migrations are discovered.

**Contract**: Append `'registry'` to `INSTALLED_APPS` after `'households'`.

#### 4. Type-checker scope

**File**: `pyproject.toml`

**Intent**: Bring the new app under mypy. Without this, CI's `uv run mypy` step passes while
checking nothing in `registry/`.

**Contract**: `[tool.mypy] files` becomes `["households", "registry", "domowa_apteka"]`.

#### 5. Read-only admin

**File**: `registry/admin.py`

**Intent**: A searchable inspection surface over ~20k mirrored rows, structurally incapable
of modifying them — an edit cannot survive the next import and would break source
traceability until then.

**Contract**: `@admin.register` for `Product` and `Substance`, following
`households/admin.py`. `ProductAdmin`: `list_display` covering name, common name, strength,
form, `last_seen_as_of`, `is_active`; `search_fields` on name and common name;
`list_filter` on `is_active`. A `ProductSubstance` inline showing substance, amount, unit, and
`source_field`. Both `ModelAdmin` classes and the inline override
`has_add_permission`, `has_change_permission`, and `has_delete_permission` to return `False`.

#### 6. Migration

**File**: `registry/migrations/0001_initial.py`

**Intent**: Create the three tables.

**Contract**: Generated by `uv run python manage.py makemigrations registry` — not
hand-written. Review the generated DDL to confirm no unique constraint landed on
`(product, substance)`.

### Success Criteria:

#### Automated Verification:

- `uv run python manage.py makemigrations --check --dry-run` reports no missing migrations
- `uv run python manage.py migrate` applies cleanly
- `uv run mypy` passes with `registry` in scope
- `uv run python manage.py check` passes
- `uv run python manage.py test` passes (no new tests yet; nothing regressed)

#### Manual Verification:

- `/admin/registry/product/` and `/admin/registry/substance/` load and show empty lists
- Neither admin page offers an "Add" button, and no detail view offers Save or Delete

**Implementation Note**: After completing this phase and all automated verification passes,
pause for manual confirmation before proceeding.

---

## Phase 2: Parser

### Overview

A pure function from a file path to typed records. It owns the human-use filter, the
placeholder denylist, and the E1 common-name fallback — every rule that touches the NFR's
"never infer an identity the source does not state" line. No database, no network, fully
testable offline.

### Changes Required:

#### 1. Denylist

**File**: `registry/denylist.py`

**Intent**: Block the category words the registry sometimes states where a substance name
belongs. Without this, 78 products become mutual full-substance-set duplicates in S-03 — a
confidently wrong result, not a visible failure.

**Contract**: A module-level `frozenset[str]` of `.casefold()`ed literals:
`produkt złożony`, `preparat złożony`, `wyciągi alergenowe`. A module docstring carries the
measured row counts (28 / 3 / 4 explicit rows) and the kept-vs-denied audit from options.md
§8c — **bare category words are denied, specific descriptive names are kept**, because those
are identities: `wyciągi alergenowe roztoczy kurzu domowego` and
`wyciąg alergenów z pyłków traw (5 gatunków)` must survive. Exact-match on the casefolded
key only — no prefix matching, no substring matching, no classifier. Deliberately short and
literal; this is the one place in F-01 where a hand-maintained list is justified, and it is
recorded as a judgement call.

#### 2. Parser

**File**: `registry/parser.py`

**Intent**: Stream the XML once, emitting a product record per human-use product with its
substance links already resolved and tagged.

**Contract**: `parse_registry(path: Path, expected_namespace: str) -> ParseResult`, plus a pure
`namespace_for_url(url: str) -> str` helper (see Critical Implementation Details). The parser
imports no Django settings — the caller derives the namespace and passes it in, which is what
keeps it a pure function and keeps the namespace tied to the configured URL.

Two `@dataclass(frozen=True)` record types mirroring the model fields — a product record and
a substance-link record (name plus the amount fields, `source_field`, and `source_order`).
`ParseResult` carries the products, the `source_as_of` date from the root `stanNaDzien`, the
substance vocabulary, and counts for the plausibility guard and command output.

**`ParseResult.substances` is an ordered, `name_key`-deduplicated sequence** of `(name, name_key)`
pairs in first-seen order. The parser is already accumulating this vocabulary for the E1
fallback, so carrying it out costs nothing — and it is the only place the first-seen-wins
tiebreak can be applied correctly. Without it the loader must re-derive the set by walking every
link, where (a) an un-deduplicated batch violates `Substance.name_key`'s unique constraint the
first time one file holds a case-collision pair — the real registry has 5 — and (b) which
verbatim spelling survives falls out of whatever order the loader happened to produce, silently
defeating the pinned tiebreak.

Behaviour:
- `xml.etree.ElementTree.iterparse` with `events=('start', 'end')`, calling `elem.clear()` on
  every `produktLeczniczy` `end` event — including filtered-out ones.
- **On the first `start` event, before entering the product loop**: assert the root tag is
  `produktyLecznicze` in `expected_namespace`, and that `stanNaDzien` parses as a date. Raise
  loudly on mismatch — this is the version-lifecycle guard (options.md §12 risk 1); importing a
  7.0.0 file as though it were 6.0.0 must fail, not half-succeed. It has to be the `start`
  event: the root element's `end` event does not fire until all 73.7 MB have been streamed,
  which would both defer the guard to the very end of the run and leave `stanNaDzien`
  unavailable while every product record is being built.
- **Accumulate the substance-name vocabulary from every product in the file, veterinary
  included, before applying the human-use filter.** This is a deliberate choice and it must
  be stated in the module docstring. options.md §8 defines the fallback test as "that exact
  string is in the registry's own substance vocabulary" without saying whether it computed
  that over the whole registry or the human-use subset (§8c restricts only the products
  *counted*). Whole-registry is the plain reading — a veterinary product's `nazwaSubstancji`
  is still the registry using that string as a substance name — and it costs one line of
  ordering. It admits no veterinary product into the data; it only widens the set of strings
  the fallback will accept. The alternative (human-use-only vocabulary) is strictly more
  conservative and would yield a lower recovery count than options.md reports.
- Skip any product whose `rodzajPreparatu` is not in a module-level
  `INCLUDED_PRODUCT_KINDS = frozenset({'ludzki'})`. A constant, so widening later is a
  one-line change plus a re-import, with no migration.
- Emit one link per `<substancjaCzynna>` with a non-blank, non-denylisted `nazwaSubstancji`,
  tagged `source_field='substance_row'`, preserving order and repeats verbatim. Copy the
  amount attributes as strings; never call `float()`.
- Set aside products that ended with zero links, then after the file is exhausted resolve
  each: if its `nazwaPowszechnieStosowana` casefolds into the vocabulary **and** is not
  denylisted, emit one link tagged `source_field='common_name'`; otherwise leave it with no
  links. See Critical Implementation Details for why this cannot be decided inline.
- Route every attribute read through the typed accessor helper (Critical Implementation
  Details), and read `ulotka` / `charakterystyka` with their parallel-import fallbacks.

#### 3. Fixture re-homing and extension

**File**: `registry/tests/fixtures/sample-products.xml`

**Intent**: Make the research fixture a test asset, and close the two gaps that stop it
proving the rules that decide whether S-03 is correct.

**Contract**: Move (via `git mv`) `context/changes/registry-substance-data/sample-products.xml`
here — data files under `context/` read as planning artifacts, and a `tests/fixtures/` path
avoids the `loaddata` semantics a Django `fixtures/` directory would claim. Reference it as
`Path(__file__).parent / 'fixtures' / 'sample-products.xml'`.

Then add products, drawn verbatim from the real export, so the fixture covers:
- **E1 fallback firing** — a human-use product carrying `Metoprololi succinas` as a real
  `<substancjaCzynna>` row, which makes `Beto 200 ZK`'s common-name fallback resolve.
  Measured during planning: without this the fixture proves only the negative path.
- **Denylist blocking an explicit substance row** — a human-use product whose
  `<substancjaCzynna>` has `nazwaSubstancji="Produkt złożony"`.
- **Denylist blocking a fallback** — a human-use product with zero substance rows and
  `nazwaPowszechnieStosowana="Produkt złożony"`.
- **A near-miss that must survive** — a product whose substance name is
  `Wyciągi alergenowe roztoczy kurzu domowego`, proving the denylist is exact-match.
- **A case-collision pair** — two human-use products carrying the same substance name in
  different case: `Sodu fluorek` on the earlier product, `sodu fluorek` on the later one (the
  real collision, taken verbatim from the live export). **Document order is part of the
  fixture's contract here** — `Sodu fluorek` must come first, because it is the form the tests
  assert survives. Measured during planning: the fixture's 33 existing `nazwaSubstancji` values
  contain no case collision at all, so without this pair three separate rules are unprovable —
  case-fold merging, the first-seen-wins tiebreak, and the loader's within-batch dedup.

Update the fixture's own header comment (or a sibling `README.md`) with the resulting
per-product expectations, since the tests assert against them.

#### 4. Parser tests

**File**: `registry/tests/test_parser.py`

**Intent**: Pin every measured edge case, so a future change that breaks one fails CI.

**Contract**: `TestCase` subclasses following `households/tests/` conventions (each method
annotated `-> None`). Cases:
- `Nalgesin` → exactly one link; name, amount `275`, unit `mg` verbatim.
- `Altacet` → **two links with the same substance name** and different amounts, both retained
  with distinct `source_order`. This is the non-uniqueness guard.
- `Vaminolact` → 19 links.
- `Peditrace` → 7 links including a repeated `Zinci chloridum`; amounts arrive only in
  `amount_description` as `521,00 mcg`, retained as a string with the comma intact.
- `Parvoerysin` and `ZmienićDIVENCE` → absent from the result entirely (veterinary).
- `Beto 200 ZK` → one link tagged `source_field='common_name'` once the vocabulary contains
  `Metoprololi succinas`.
- The denylisted-substance-row product → parsed, but with zero links.
- The denylisted-common-name product → parsed, with zero links.
- `Wyciągi alergenowe roztoczy kurzu domowego` → survives; assert explicitly against the
  denylist's bare `wyciągi alergenowe` entry.
- Case-folding: two names differing only in case collapse to one `name_key`, and the
  first-seen verbatim form is the one retained.
- Root-tag / namespace assertion raises when `expected_namespace` disagrees with the file. With
  the namespace now an argument, this needs no second XML file — pass the fixture a 7.0.0
  namespace and assert it raises. Every other case here passes the fixture's own 6.0.0 namespace
  literal explicitly.
- `namespace_for_url()` returns the 6.0.0 namespace for the current URL and a 7.0.0 namespace for
  a 7.0.0 URL, and raises on a URL with no recognisable version segment. It is new public API and
  the whole version-lifecycle guard rests on it.
- `stanNaDzien` is parsed to the expected date.

### Success Criteria:

#### Automated Verification:

- `uv run python manage.py test registry.tests.test_parser` passes
- `uv run mypy` passes with no `type: ignore` comments added to `registry/parser.py`
- Every test above fails when its rule is deliberately inverted (spot-check the denylist and
  the `source_field` tagging — a test that cannot fail is not a test)
- `git log --follow registry/tests/fixtures/sample-products.xml` shows the move, not a
  delete-plus-add

#### Manual Verification:

- Parse the real 73.7 MB `overall.xml` once locally and confirm the human-use product count
  lands near the 20,187 measured in options.md §4, and that **at least 95% of human-use
  products resolve to at least one substance, with the common-name fallback recovering
  several hundred**. Deliberately a range, not the 97.23% headline: that figure assumed a
  vocabulary scope options.md never stated (see the parser contract), so an exact-match
  criterion could not distinguish a bug from a definitional difference.
- Peak memory **during the streaming pass**, before the retained records dominate, stays in the
  single-digit MB range. This, and only this, is what confirms `elem.clear()` is doing its job
- **Total** peak, including the fully materialized `ParseResult`, is measured and written into
  the Performance Considerations paragraph. Expect tens of MB: this design deliberately retains
  ~20,187 product records plus ~29,064 link records instead of discarding them. options.md §1's
  7 MB measured a pass that counted and discarded each record, so it describes neither figure
  for the parser this phase builds — do not carry it forward as a gate
- **Note**: `requests` and `REGISTRY_OVERALL_URL` do not land until Phase 3, so fetch
  `overall.xml` by hand for these two checks (browser or `curl`) and pass it via `--file`

**Implementation Note**: After completing this phase and all automated verification passes,
pause for manual confirmation before proceeding.

---

## Phase 3: Loader and management command

### Overview

Fetch (or read) the snapshot, hand it to the parser, and write the result in one transaction.
The loader makes no decisions about what a substance is — it only decides where rows go.

### Changes Required:

#### 1. HTTP dependency

**File**: `pyproject.toml` / `uv.lock`

**Intent**: Add the HTTP client for the download path.

**Contract**: `uv add requests` — never hand-edit `uv.lock`, and never pip. CI runs
`uv sync --locked` and Railway's build runs `uv sync --locked --no-dev`, so a drifted lock
fails both. Add `types-requests` to the dev group so mypy has stubs.

#### 2. Settings and env template

**Files**: `domowa_apteka/settings.py`, `.env.example`

**Intent**: Make the registry URL configurable, so the publisher's next version bump is a
variable change rather than a code deploy.

**Contract**: `REGISTRY_OVERALL_URL = os.environ.get('REGISTRY_OVERALL_URL', <6.0.0 URL>)`,
placed with the other environment reads. A documented `.env.example` entry in the style of the
existing ones, explaining that the `6.0.0` path segment is version-pinned by the publisher and
that 5.0.0 was retired on a published schedule. See Critical Implementation Details for why an
in-code default is correct here and does not violate `AGENTS.md`.

**No second setting for the namespace.** The expected namespace is derived from this URL by
`namespace_for_url()` at call time. The `.env.example` note must say so explicitly — otherwise
the next person pins a namespace constant somewhere and reintroduces exactly the drift this
avoids.

#### 3. Loader

**File**: `registry/loader.py`

**Intent**: Persist a `ParseResult` idempotently, without ever deleting a product a user's
saved item might reference.

**Contract**: `load_parse_result(result: ParseResult) -> LoadStats`, inside one
`transaction.atomic()`.

Ordering:
1. Insert `Substance` rows for the `name_key` values on `result.substances` **not already
   present** — read the existing keys, diff against that ordered, pre-deduplicated sequence, and
   `bulk_create` only the missing ones. **The loader must not re-derive the vocabulary by
   walking links**; `ParseResult` carries it precisely so the within-batch dedup and the
   first-seen order are decided in one place (Phase 2 § 2). **Do not update `name` on
   conflict.** An `update_conflicts=True, update_fields=['name']` upsert would be
   last-write-wins on the display name, which directly defeats the first-seen-wins tiebreak
   pinned in Critical Implementation Details: a reordered snapshot would silently flip
   `Sodu fluorek` to `sodu fluorek`. Insert-only makes first-seen-wins hold across runs, not
   just within one parse.
2. Upsert `Product` rows keyed on `registry_id`, updating every mutable field plus
   `last_seen_as_of = result.source_as_of` and `is_active=True`. After this step every product
   in this snapshot carries the snapshot's date — which is what steps 4 and 5 select on.
3. Build both id maps explicitly with `values_list(...)` — see Critical Implementation
   Details. **The loader must not read PKs off the `bulk_create` return value.**
4. Delete the `ProductSubstance` rows for the products in this snapshot with
   `ProductSubstance.objects.filter(product__last_seen_as_of=result.source_as_of).delete()`,
   then `bulk_create` the new links. Link rows carry no external foreign keys, so nothing
   cascades; this is what makes the load idempotent despite the through-table having no unique
   key. **Select on the date stamped in step 2, never on a list of product ids** — an
   `id__in=[…]` form binds one query parameter per product (20,187 today) and Django does not
   chunk `__in` on the fast-delete path. Measured in this environment (Python 3.11.9 /
   SQLite 3.45.1): `SQLITE_LIMIT_VARIABLE_NUMBER` is 32,766, so the id-list form works today
   with ~38% headroom and **no test can see the ceiling** — the fixture holds ~11 products. The
   date predicate binds one parameter regardless of snapshot size, so the limit stops applying
   rather than being chunked around.
5. Mark products **not** present in this snapshot as `is_active=False` with
   `Product.objects.exclude(last_seen_as_of=result.source_as_of).update(is_active=False)`,
   leaving `last_seen_as_of` at its previous value — which is exactly what makes that column the
   record of when the product was last seen. Never delete. Same single-parameter reasoning as
   step 4.

Pass `batch_size` to every `bulk_create` — SQLite has a query-variable limit.

#### 4. Management command

**File**: `registry/management/commands/import_registry.py`

**Intent**: The roadmap's "one repeatable command".

**Contract**: `BaseCommand` with `--file <path>` (parse a local file) and `--url <url>`
(override the setting). With neither, use `settings.REGISTRY_OVERALL_URL`. The local-file path
is what makes the command testable and re-runnable offline.

Download path: `requests.get(url, stream=True, timeout=...)`, `raise_for_status()`, streamed
to a `tempfile.NamedTemporaryFile` in chunks, then parsed from that path — not off the live
response, so a mid-parse network blip cannot leave a half-applied load. Clean up the temp file
unless a `--keep-download` flag is passed.

**Plausibility guard**: before the transaction commits, assert the parsed human-use product
count exceeds a floor. Below it, raise `CommandError` and let the transaction roll back.
Without this, a truncated download looks like a successful load of 300 products (options.md
§12 risk 3).

**The floor must be injectable, or it breaks every test.** A module constant alone
(comfortably below the measured 20,187 — 10,000 is sensible) would make *every* loader test
fail, because the fixture holds ~11 products. Expose it as `--min-products N` defaulting to
the constant: tests pass `--min-products 1` for the normal cases, and the guard's own test
passes a deliberately high value against the fixture. Applying the guard only on the URL path
would also avoid the collision, but leaves it untested on the path the tests actually
exercise — do not do that.

Write a summary to stdout: source as-of date, products loaded, products marked inactive,
links by `source_field`, and elapsed time. Use `self.stdout.write`, not `print`.

#### 5. Loader tests

**File**: `registry/tests/test_loader.py`

**Intent**: Prove the load is idempotent and non-destructive — the two properties a one-shot
command hides until its second run.

**The three variant inputs below are produced at test time**, not committed: read the fixture's
text, mutate a copy in memory (drop one `<produktLeczniczy>` block; rewrite one `moc` attribute;
swap the two `Sodu fluorek` / `sodu fluorek` products), write it to a `tempfile`, and pass that
via `--file`. Do not commit three near-copies of the fixture — they drift from the main file and
from each other, and the main fixture is the single source of truth for the documented
per-product expectations.

**Contract**: `TestCase` subclasses. Cases:
- Run the command against the fixture; assert product, substance, and link counts, and that
  `source_field` values are distributed as the fixture expects.
- **Run it twice; assert the second run leaves identical row counts and identical product
  primary keys** (proving upsert, not insert-duplicate).
- Re-run against a reduced fixture omitting one product; assert that product is
  `is_active=False`, still present, with `last_seen_as_of` unchanged — and that its links
  survive.
- Re-run against a fixture where a product's strength changed; assert the field updated.
- Assert `Substance` rows are shared, not duplicated, across products using the same name.
- Assert a re-run with a fixture where a case-collision pair appears in the opposite order
  leaves the stored `Substance.name` unchanged — first-seen-wins holds across runs.
- Assert `--min-products` above the fixture's count raises `CommandError` and leaves the
  database untouched. Every other loader test passes `--min-products 1`.
- Assert `--file` never touches the network (no `requests` import path exercised).

### Success Criteria:

#### Automated Verification:

- `uv run python manage.py test registry` passes
- `uv run python manage.py test` passes (whole suite, no regressions in `households`)
- `uv run mypy` passes
- `uv run python manage.py check` passes
- `uv sync --locked` succeeds, confirming `uv.lock` and `pyproject.toml` agree
- Running `import_registry --file <fixture>` twice produces identical row counts

#### Manual Verification:

- Run `import_registry` against the live URL locally; total elapsed time is in the same order
  as the ~13 s measured in options.md §11
- Spot-check three recognisable brands in `/admin/registry/product/` — one resolved via an
  explicit substance row, one via the common-name fallback, one legitimately unresolved — and
  confirm `source_field` reads correctly for each
- Confirm the temp file is removed after a successful run

**Implementation Note**: After completing this phase and all automated verification passes,
pause for manual confirmation before proceeding.

---

## Phase 4: Production load

### Overview

Get the data into production Postgres. This phase is **manual and user-driven** — the tooling
constraint is documented, not incidental.

### Changes Required:

#### 1. Merge to main

**Intent**: Ship the app, models, migration, and command to production.

**Contract**: Open a PR from the feature branch, let the `check` job pass, merge. The merge
triggers `railway up`, and `migrate --noinput` in `railway.json`'s `startCommand` creates the
three tables on production Postgres. Per `AGENTS.md`, never push code to `main` directly.

#### 2. One-off production import

**Intent**: Populate the tables. Also the first — and, absent a local Postgres, only —
exercise of the upsert path on Postgres rather than SQLite.

**Contract**: The temporary-`startCommand` shape from
`context/deployment/deploy-plan.md:256-266` — the one this project has already executed end to
end, for `createsuperuser`. It needs no shell and no TTY:

1. Temporarily add `(python manage.py import_registry || true)` to `startCommand` in
   `railway.json`, ahead of the existing `migrate` + gunicorn chain. The `|| true` is what keeps
   a redeploy from crashing the container if the import fails; the import's own plausibility
   guard and single transaction are what protect the data.
2. Deploy, and confirm the command's summary output in the Railway logs.
3. **Revert `railway.json` and redeploy.** Not optional — left in place, every container restart
   re-downloads 74 MB and re-imports.

`railway run` will not work: it executes locally with variables injected, and `DATABASE_URL`
points at `postgres.railway.internal`, unreachable from a laptop
(`context/deployment/deploy-plan.md:250-254`).

**`railway ssh` is deliberately not the documented path.** It holds a TTY, and this project's
own deploy record shows it was abandoned mid-attempt and never confirmed to reach this
container — the SSH key it left behind is marked "safe to remove"
(`deploy-plan.md:269-277`). Making it the route would put an unverified platform capability on
the only path to the end state, which is the mirror image of the first accepted rule in
`context/foundation/lessons.md`. A human is free to try it interactively as a shortcut; the plan
does not depend on it.

On the healthcheck: the import measured ~13 s locally, gunicorn starts after it in the `&&`
chain, and `railway.json` permits `healthcheckTimeout: 300`. Raise the timeout for the single
deploy that carries the import if the margin looks tight. Production import duration is
unmeasured — 13 s is a laptop number.

Record the command's summary output (product count, links by `source_field`, elapsed time) in
this change folder, so F-02 has a production baseline to compare against.

### Success Criteria:

#### Automated Verification:

- The GitHub Actions `check` job passes on the PR
- The `deploy` job completes and the Railway healthcheck stays green

#### Manual Verification:

- `import_registry` completes on production without error, and its reported product count is
  in the same range as the local run
- `/admin/registry/product/` on the production domain returns loaded rows
- A recognisable brand searched in production admin shows the same substances it showed
  locally
- Running the import a second time on production reports the same counts — idempotency
  confirmed on Postgres, not just SQLite
- `railway.json` is reverted to its normal `startCommand` and redeployed, and the logs of a
  subsequent restart show no import running

---

## Testing Strategy

### Unit Tests (`registry/tests/test_parser.py`)

Every rule that touches the NFR lives in the parser, so this is where the correctness-critical
coverage sits: the denylist (both the blocks and the near-miss survivals), the E1 fallback and
its `source_field` tagging, repeated substances on one product, decimal-comma amounts kept as
text, veterinary exclusion, case-fold merging with a pinned tiebreak, and the namespace
assertion.

### Integration Tests (`registry/tests/test_loader.py`)

Idempotency (run twice → identical state), upsert-on-re-run, withdrawn marking without
deletion, substance sharing across products, and the plausibility guard rolling back.

### Manual Testing Steps

1. Run `import_registry --file registry/tests/fixtures/sample-products.xml`; confirm the
   summary output matches the fixture's documented expectations.
2. Run it again; confirm counts are unchanged.
3. Run `import_registry` against the live URL; confirm elapsed time and counts are in the
   measured range.
4. In `/admin/registry/product/`, search a brand resolved by an explicit substance row, one
   resolved by the common-name fallback, and one unresolved; confirm `source_field` is correct
   for each and that no Add/Save/Delete affordance exists.
5. After the production import, repeat step 4 against the production domain.

## Performance Considerations

The measured budget is ~13.1 s end to end: 2.7 s download, 9.9 s parse, ~0.5 s of database
work (options.md §11). The parse dominates by roughly 20×, so the database timings —
measured on in-memory SQLite and certain to be slower on networked Postgres — do not change
the shape.

Peak Python memory has **two components that must not be conflated**. Measured in Phase 2 with
`tracemalloc` over the real 73.9 MB export (`stanNaDzien=2026-08-12`, 22,885 products, 20,245
human-use), parsed in 6.3 s:

| Figure | Measured |
| --- | --- |
| Total peak | **30.1 MB** |
| Retained immediately after the call | 27.7 MB — the fully materialized `ParseResult` |
| Transient headroom (peak − retained) | **2.5 MB** — everything the streaming pass costs above the records it is accumulating |

The 2.5 MB is what confirms `elem.clear()` is doing its job: without it the retained element
tree alone would run to roughly 1 GB. The parser returns a materialized result, so the
streaming pass's own peak cannot be isolated from the records accumulating alongside it without
instrumenting the parser — this decomposition is the closest honest substitute, and it is
discriminating for the thing that matters. options.md §1's 7 MB figure measured a pass that
discarded each record after counting it, so it describes neither number for this design.

No caching, no indexing beyond the model-level `db_index` flags, and no query optimization is
in scope; S-02 owns autocomplete performance and the NFR's one-second acknowledgement.

## Migration Notes

There is no existing data to migrate — these are new tables. The re-import path is the
migration story: because the source is a full daily snapshot, adding a field later costs a
nullable `AddField` plus one parser line plus a 13-second re-run, with **no backfill
problem**. Today's file carries today's complete truth for every field, including ones never
stored. Fields deliberately skipped now (ATC codes, packages/GTIN) can be added later at a
new-table cost of well under an hour each, with no data loss in the interim.

## References

- Research: `context/changes/registry-substance-data/options.md` (measured 2026-08-07)
- Library docs: `context/changes/registry-substance-data/library-docs.md`
- Roadmap item: `context/foundation/roadmap.md` § F-01
- Model / admin / test conventions: `households/models.py`, `households/admin.py`,
  `households/tests/`
- Production one-off command constraints: `context/deployment/deploy-plan.md:248-266`
- Recurring rules applied: `context/foundation/lessons.md` (verify engine-behaviour claims
  before designing around them)

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles. See `references/progress-format.md`.

### Phase 1: App scaffold, data model, and read-only admin

#### Automated

- [x] 1.1 `makemigrations --check --dry-run` reports no missing migrations — f9d370b
- [x] 1.2 `manage.py migrate` applies cleanly — f9d370b
- [x] 1.3 `mypy` passes with `registry` in scope — f9d370b
- [x] 1.4 `manage.py check` passes — f9d370b
- [x] 1.5 `manage.py test` passes with nothing regressed — f9d370b

#### Manual

- [x] 1.6 Both registry admin pages load and show empty lists — f9d370b
- [x] 1.7 No Add button, and no Save or Delete on any detail view — f9d370b

### Phase 2: Parser

#### Automated

- [x] 2.1 `manage.py test registry.tests.test_parser` passes
- [x] 2.2 `mypy` passes with no `type: ignore` added to `registry/parser.py`
- [x] 2.3 Denylist and `source_field` tests fail when their rule is deliberately inverted
- [x] 2.4 `git log --follow` on the fixture shows a move, not a delete-plus-add

#### Manual

- [x] 2.5 Hand-fetched real `overall.xml` parses to ~20,187 human-use products, ≥95% resolved
- [x] 2.6 Streaming-pass peak memory during the real parse stays in single-digit MB
- [x] 2.7 Total peak with the materialized `ParseResult` measured and written into the plan

### Phase 3: Loader and management command

#### Automated

- [ ] 3.1 `manage.py test registry` passes
- [ ] 3.2 `manage.py test` passes across the whole suite
- [ ] 3.3 `mypy` passes
- [ ] 3.4 `manage.py check` passes
- [ ] 3.5 `uv sync --locked` succeeds
- [ ] 3.6 Running `import_registry --file <fixture>` twice produces identical row counts

#### Manual

- [ ] 3.7 Live-URL run completes in the same order as the measured ~13 s
- [ ] 3.8 Three brands spot-checked in admin, one per resolution path, `source_field` correct
- [ ] 3.9 Temp file removed after a successful run

### Phase 4: Production load

#### Automated

- [ ] 4.1 GitHub Actions `check` job passes on the PR
- [ ] 4.2 `deploy` job completes and the Railway healthcheck stays green

#### Manual

- [ ] 4.3 `import_registry` completes on production with a product count in the local range
- [ ] 4.4 Production `/admin/registry/product/` returns loaded rows
- [ ] 4.5 A brand searched in production admin shows the same substances as locally
- [ ] 4.6 A second production run reports identical counts — idempotency confirmed on Postgres
- [ ] 4.7 `railway.json` reverted and redeployed; a restart's logs show no import running
