# F-01 `registry-substance-data` — implementation options

Research artifact, not a plan. It answers the roadmap's two unknowns for F-01
(ingestion approach + cadence, and how messy the substance fields are) so that
`/10x-plan` can start from measured facts. Every number below was measured
against the live registry on **2026-08-07**, not inferred.

Companion file: `sample-products.xml` — an 8-product, 31 KB excerpt of the real
export covering every edge case found. It is offline test-fixture material and
the reason no test needs network access.

---

## 1. Evidence base

Reproducible with the commands in each section. Raw file was downloaded once
(74 MB, 2.7 s) and parsed locally.

| Measurement | Value |
| --- | --- |
| `overall.xml` size | 73,707,653 B (73.7 MB), **no gzip offered** |
| Download time | 2.7 s |
| Root attribute | `stanNaDzien="2026-08-07"` — i.e. regenerated same-day |
| Parse, stdlib `iterparse` + `elem.clear()` | **9.9 s, 7 MB peak Python memory** |
| Products (`produktLeczniczy`) | 22,823 — all with a distinct `id` |
| Active-substance rows | 29,064 |
| Distinct raw substance names | 4,267 |
| Products with **zero** substance rows | 1,054 (4.6%) |
| Products with an ATC code | 21,679 |
| Encoding | valid UTF-8 end to end |

Environment checks: Python 3.11.9, Django 5.2.16, SQLite 3.45.1 (≥ 3.24, so
`bulk_create(update_conflicts=True)` is available on dev SQLite *and* prod
Postgres).

---

## 2. Source-of-record findings

These close the roadmap's "bulk file, API, or scrape?" unknown outright.

**The bulk XML is the only public interface.** Probed directly:

| Endpoint | Result |
| --- | --- |
| `…/public-pl-report/6.0.0/overall.xml` | **200**, 73.7 MB |
| `…/public-pl-report/6.0.0/incremental.xml` | 404 |
| `…/public-pl-report/5.0.0/overall.xml` | 200 (previous version still up) |
| `…/public-pl-report/7.0.0/overall.xml` | 400 (does not exist yet) |
| `…/6.0.0/overall.{csv,json,xlsx}` | 404 |
| `/api/rpl/medicinal-products` (list) | 403 `ACCESS_DENIED_EXCEPTION` |
| `/api/rpl/medicinal-products/1` (detail) | 403 `ACCESS_DENIED_EXCEPTION` |

The incremental feed is not missing by accident — the publisher **retired it
deliberately**. From their own announcement (found via exa):

> planowane jest zakończenie udostępniania plików […] w formie przyrostowej i
> wyłączenie endpointów: `…/4.0.0/incremental.xml`, `…/5.0.0/incremental.xml`
> […] Rezygnacja […] podyktowana jest potrzebą zapewnienia, że publikowane
> pliki są zawsze aktualne, a w przypadku jakiejkolwiek przerwy w cyklicznym
> pobieraniu danych, nadal będą one kompletne.

Corroborated in the data: the schema's `status` attribute
(`Nowy`/`Zmodyfikowany`/`Usuniety`) is **absent on all 22,823 products** in the
overall report. There is no delta signal to consume. **Full-snapshot replace is
the only supported ingestion mode.** Do not design a diff pipeline.

**Cadence: daily.** Publisher states "Pliki są aktualizowane codziennie", and
`stanNaDzien` equalled the request date. CSV/XLSX are *reported* (in the same
announcement, not probed here) to exist only via the `registry/rpl` download
page under date-stamped filenames — no stable URL. Since the XML is
version-pinned, has a published XSD, and preserves the nested substance
structure a flat sheet cannot, this was not worth another round trip.

**No conditional GET.** The response carries no `ETag` and no `Last-Modified`,
and no `Content-Encoding`. You cannot cheaply ask "has it changed?" — you
re-download 74 MB and read `stanNaDzien`. *(F-02 note only; do not design F-02
here.)*

---

## 3. How messy is the data, really? — better than feared

| Probe | Result |
| --- | --- |
| Names with leading/trailing whitespace | **0** |
| Names differing only by case/whitespace | **5** pairs out of 4,267 (e.g. `Sodu fluorek` / `sodu fluorek`) |
| Blank substance names | 0 |
| `substancjaCzynna` element text content | never used — all data is in attributes |
| Longest substance name | 254 chars (schema caps `limitedString` at 255) |

Names are Latin INN forms in grammatical case (`Acidum zoledronicum`,
`Naproxenum natricum`, `Bisoprololi fumaras`). 482 contain a comma, 361 a
parenthesis, 761 a digit — mostly vaccines and allergen extracts, which are
legitimately long descriptive names, not dirt.

**The consequence:** normalization beyond `strip()` + case-folding is
unnecessary. Lemmatizing `Bisoprololi` → `Bisoprolol` would be *inferring an
identity the source does not state* — exactly what the NFR bans.

**This closes an open question in `context/foundation/tech-stack.md`**, which
records "a candidate non-user-facing LLM for normalizing messy registry fields
is possible but uncommitted, so no AI flag is set." The fields are not messy:
zero whitespace defects and 5 case collisions across 4,267 names. `.strip()` and
`.casefold()` do the entire job. **No LLM is needed for F-01**, and the
`has_ai: false` flag should stay false.

Two real messiness signals worth knowing:

- 89 **excess** rows across 29,064 are a repeat of a substance name already
  listed on the same product (e.g. `Altacet` lists `Aluminii acetotartras` twice
  at different amounts). 89 is the surplus count, not the number of rows
  involved. Either way: **`(product, substance)` is not unique** — this
  constrains the through-table design (§ 7).
- At least one product name carries an editorial artifact: `ZmienićDIVENCE`
  ("Zmienić" = "to change"). Load it verbatim; do not clean it.

---

## 4. Decision A — which subset of the registry?

Not previously on the roadmap's list, but it changes S-02's autocomplete quality.

| `rodzajPreparatu` | Count |
| --- | --- |
| `ludzki` (human) | 20,187 |
| `weterynaryjny` (veterinary) | 2,636 (11.5%) |

2,632 vet products also carry species/withdrawal-period data. Filtering on a
**source-stated field** is selection, not inference — the NFR permits it.

- **A1 — load human only.** Drops 11.5% noise from a household-medicine
  autocomplete. Risk: a household genuinely may keep a pet's medicine.
- **A2 — load everything, filter at query time.** Keeps the door open; costs
  nothing at 22.8k rows. **Recommended** — store `rodzajPreparatu`, let S-02
  decide the default filter.

## 5. Decision B — XML parsing

| Option | Cost | Verdict |
| --- | --- | --- |
| **B1 `xml.etree.ElementTree.iterparse` + `elem.clear()`** | **measured 9.9 s / 7 MB**, zero new deps | **Recommended** |
| B2 `lxml.etree.iterparse` | ~2–3× faster; adds a compiled wheel + `uv.lock` churn | Not worth it — B1 is already 10 s |
| B3 `xmlschema` (validate against the XSD) | validates, but slow and memory-hungry over 74 MB | No. Assert on the root tag + `stanNaDzien` instead |
| B4 `ET.parse()` whole-DOM | ~1 GB+ resident | **No** — would OOM on Railway |

B1's measurement is the whole argument: 9.9 s and 7 MB is not a problem worth a
dependency. The `elem.clear()` call is what makes it 7 MB instead of ~1 GB — it
is load-bearing, not an optimization.

XXE/billion-laughs: the source is a trusted government HTTPS endpoint and
`iterparse` does not expand external entities by default on modern CPython.
`defusedxml` is defensible but not required here; note the decision either way.

**Windows footnote:** open the file with an explicit `encoding='utf-8'` and set
`PYTHONIOENCODING=utf-8` when printing Polish to a console. The default cp1252
console encoding mangles output (hit twice during this research) — a cosmetic
trap that reads like data corruption but isn't.

## 6. Decision C — fetching

- **C1 — stream to a temp file, then parse.** Retryable, inspectable, lets you
  keep the file for debugging. **Recommended.**
- **C2 — parse straight off the response stream.** No temp file, but a mid-parse
  network blip aborts a half-applied load.
- Client: **stdlib `urllib.request` (zero new deps)** vs `requests` (nicer
  retries/timeouts, one new dep). The project has no HTTP client today. Either
  is defensible; `urllib` keeps the dependency count honest for a one-shot load.
- The command must accept a **local file path** as an alternative to the URL —
  that is what makes it testable and re-runnable offline.

**Hard repo rule:** the URL cannot be a hardcoded constant. Per AGENTS.md, add an
`os.environ` read in `settings.py` **plus** a documented `.env.example` entry.
This doubles as the mitigation for the version-lifecycle risk (§ 10): 5.0.0 is
still up and 6.0.0 replaced it on a published schedule, so `6.0.0` in the path
*will* need changing without a code deploy.

## 7. Decision D — data model

The outcome demands "product → active-substance **sets**" and traceability.

- **D1 — `Product` + `Substance` + through-table.** Set comparison for S-03
  becomes a DB operation; substance names are stored once. **Recommended.**
- D2 — `Product` with a JSON list of substances. Fewer tables; pushes every
  overlap query into Python. Poor fit for S-03's partial-duplicate matching.
- D3 — one flat row per product-substance. Trivial load, worst queries.

Within D1, the constraint from § 3 bites: **the through-table cannot be unique
on `(product, substance)`** — 89 excess rows legitimately repeat. Two ways out:

- **D1a — keep every source row verbatim** (no unique constraint), carrying
  `iloscSubstancji` / `jednostkaMiary…` / `innyOpisIlosci`. S-03 then compares
  `DISTINCT` substance sets. Preserves provenance exactly. **Recommended.**
- D1b — collapse to distinct `(product, substance)`. Simpler, but silently
  discards 89 source rows, which cuts against "traceable back to the source row".

**Substance identity — where the no-guessing line sits.** Key on the source
string. Store `name` verbatim (`max_length=255`, matching the XSD) plus a
`name_key = name.strip().casefold()` used only for lookup/dedup. Case-folding is
*reformatting* (allowed, and it merges exactly the 5 known collisions);
lemmatizing Latin inflection is *inferring* (banned).

**Provenance fields** that satisfy "traceable back to the source row it came
from": registry `id` (stable, 22,823 distinct), `numerPozwolenia`,
`source_as_of` (from `stanNaDzien`), and the source URL + schema version.

## 8. Decision E — the substance-less products (1,054)

The most consequential finding, and it changes what S-02/S-03 can promise.

Of the 1,054 products with no `substancjaCzynna` row, **1,047 still carry a
non-empty product-level `nazwaPowszechnieStosowana`** (common name). But not
every value is a substance name: 229 say `Homeopatyczny produkt leczniczy`, 60
say `Produkt/Preparat złożony`. Those are categories.

A **source-grounded test** separates them: does the value appear as a
`nazwaSubstancji` somewhere else in the registry?

| Tier | Rule | Products left unresolved |
| --- | --- | --- |
| **E0** | No fallback. Only explicit `substancjaCzynna` rows count. | **1,054** |
| **E1** | Fall back to `nazwaPowszechnieStosowana` **only if that exact string is in the registry's own substance vocabulary** (499 qualify). | **555** |
| E2 | Accept any non-empty common name. | **7** — but imports 548 values of mixed quality, incl. `Produkt immunostymulujący`. |

**Be precise about what E1 is, because it decides how the NFR applies.** The
vocabulary test attests that the *string* is one the registry itself uses as a
substance name. It does **not** attest that this product contains that
substance: the source says "this product's commonly-used name is X", never "X is
an active substance of this product". **That product→substance link is our
inference, not the registry's** — and it is exactly the relation the NFR guards.
E1 is not inference-free; it is inference with a source-attested vocabulary and
a conservative filter. E2 is the same inference with no filter at all.

Supporting evidence *for* the inference (not proof it isn't one): where a product
has exactly one substance row, `nazwaPowszechnieStosowana` matches it exactly in
14,800 of 17,696 cases (83.6%).

**E1 needs a denylist — the vocabulary test alone leaks placeholders.** Checked
against real rows: `Produkt złożony` ("compound product") is itself used as a
`nazwaSubstancji` on 28 products, so it *passes* the vocabulary test. 60 of the
499 E1 recoveries resolve to `Produkt złożony` / `Preparat złożony`, and
`Wyciągi alergenowe` leaks the same way. Clean recovery is **~439, not 499**.
See § 8a — this is not only an E1 problem.

**If E1 is adopted it must be recorded per-row** — an explicit `source_field`
marker distinguishing "explicit substance row" from "derived from product common
name" — so S-02 can show the user where a resolution came from and S-03 can
weight it. That marker is what keeps the provenance honest. E1 is otherwise
deliberately conservative: it leaves real substances like `Medroxyprogesteronum`
and `Tolkaponum` unresolved because they never appear as a substance row
anywhere. That under-recovery is the correct failure direction for a
duplicate-detection app.

## 8a. The placeholder-substance trap — affects S-03 even with **no** fallback

The registry sometimes states a *category* where a substance name belongs, in an
ordinary `substancjaCzynna` row:

| Value used as `nazwaSubstancji` | Explicit rows | + via E1 fallback |
| --- | --- | --- |
| `Produkt złożony` | 28 | 50 |
| `Preparat złożony` | 3 | 10 |
| `Wyciągi alergenowe` | 4 | — |

If these become ordinary `Substance` rows, then **every product carrying
`Produkt złożony` becomes a full-substance-set duplicate of every other one** —
78 products mutually flagged as identical medicines. That is a correctness bug in
S-03's headline feature, and it exists at E0 too; the fallback only widens it.

Mitigation: a small, explicit, **documented** denylist of non-substance values,
applied at load time, with those products treated as unresolved rather than
matched. This is a judgement call and should be recorded as one — it is the one
place in F-01 where a hand-maintained list is justified. Keep it short and
literal; do not generalise it into a classifier.

## 8b. Strength and multiplicity — the source has already decomposed both

Worth stating plainly because it removes two jobs people expect to do.

**Strength is a separate attribute, not embedded in the name.** `nazwaSubstancji`
carries only the name; the amount lives in sibling attributes:

| Field | Populated |
| --- | --- |
| `iloscSubstancji` (amount) | 24,065 (82.8%) |
| `jednostkaMiaryIlosciSubstancji` (unit) | 24,044 (82.7%) |
| `iloscPreparatu` / `…Preparatu` (per-preparation basis) | 2,002 (6.9%) |
| `innyOpisIlosci` (free-text amount) | 4,671 (16.1%) |
| no quantity information at all | 200 (0.7%) |

Only **6 of 29,064** substance names embed a number+unit at all (e.g.
`Ammonii hydroxidum (96g/l)`), and even those populate the amount fields too.
**So: no string-splitting is needed, and none should be attempted.** Three traps:

- **Decimal comma.** Values are Polish-formatted: `3,13`, `17,51`. A naive
  `float()` raises or silently truncates. Store as text, or normalise the
  separator deliberately and record that you did.
- **The unit field is sometimes compound** (`mg/ml`, `mg/g`), so the
  per-preparation ratio is encoded in the unit on some rows and in the separate
  `iloscPreparatu` pair on others. Two shapes for one concept.
- **Never parse the product-level `moc`.** It is free text:
  `(17,51 g + 3,276 g + 3,13 g)/butelkę`, `nie mniej niż 40 j.m. toksoidu
  tężcowego…`. Fine to display, unusable as data.

**Multi-substance products are already split by the source** — one
`<substancjaCzynna>` element each (2,901 products have 2, 742 have 3, max 46).
The exception is **8 rows out of 29,064** that pack several into one string, and
they are *not* safely splittable on `+`:

| Genuinely multiple | `+` is part of the identifier |
| --- | --- |
| `Vaccinum Hepatits A+B` | `Autologiczna frakcja… CD34+…` |
| `Estradiolum, Estradiolum + Dydrogesteronum` (Femoston) | `szczep CAL10 Sm+/Rif+/Ssq-…` |
| `Premiks witaminowy A + D3 (500/50)` | |

Splitting on `+` would corrupt the second column. At 8 rows (0.03%), load them
verbatim and accept them as unresolved-ish; do not write a splitter.

## 8c. Coverage — what fraction of human-use drugs resolve to a substance?

The headline number for F-01. Restricted to the **20,187 `ludzki` (human-use)
products**; veterinary excluded.

| Method | Products | Share |
| --- | --- | --- |
| **A — explicit `substancjaCzynna` row(s)** | 19,208 | **95.15%** |
| **C — E1 fallback (common name in substance vocabulary)** | 419 | **+2.08%** |
| **Resolved (A + C)** | **19,627** | **97.23%** |
| B — has substance rows, but all are denylisted placeholders | 31 | 0.15% |
| D — fallback blocked by the § 8a denylist | 60 | 0.30% |
| E — common name present but not in the vocabulary | 466 | 2.31% |
| F — no substance row and no common name | 3 | 0.01% |
| **Unresolved (B + D + E + F)** | **560** | **2.77%** |

Read across the options:

- **E0 (no fallback at all): 95.15%.** Already good enough to ship.
- **E1 + denylist: 97.23%.** The fallback is worth **+2.08 pp** — 419 products,
  and they are disproportionately recognisable brands (`Smecta`, `Differin`,
  `Concor 5`, `Nootropil`), so the felt improvement in S-02 exceeds the
  percentage.
- **Without the denylist: 97.68%** — but the extra 0.45 pp is the placeholder
  matches of § 8a, which actively corrupt S-03. **The denylist costs 0.45 pp of
  coverage to remove a class of confidently-wrong duplicate flags.** Take that
  trade.

The residual 2.77% is dominated by category E (2.31%): products whose common name
is a real but unique description — radiopharmaceuticals, allergen extracts,
immunostimulants (`Staloral`, `PoltechDMSA`, `Luivac`). These are genuinely
outside a household medicine cabinet's normal contents, so the effective coverage
for realistic user input is higher than 97.23%.

**Denylist audit.** The list stays narrow on purpose — it blocks bare category
words only. Specific descriptive names are kept, because they *are* identities:

| Denied (generic category) | Kept (specific identity) |
| --- | --- |
| `wyciągi alergenowe` (4 rows) | `wyciągi alergenowe roztoczy kurzu domowego` |
| `produkt złożony` (28 rows) | `wyciąg alergenów z pyłków traw (5 gatunków)` |
| `preparat złożony` (3 rows) | `wodny wyciąg borowinowy` |

## 9. Decision F — load strategy

22,823 products + 29,064 links is small. The real question is **what happens to
rows that vanish from tomorrow's snapshot**, because S-02 will put user items
behind FKs to `Product`.

- **F1 — upsert via `bulk_create(update_conflicts=True, unique_fields=['registry_id'], update_fields=[…])`**, then mark products absent from this snapshot as withdrawn (`last_seen_as_of` / `is_active`) rather than deleting them. Available on both SQLite 3.45 and Postgres. FK-safe, provenance-preserving. **Recommended.**

  **PK caveat — checked, and it holds.** The two-step (upsert products, then
  write link rows) needs product PKs after step one, and Django documents that
  `bulk_create` does not populate PKs on every backend. Measured on this
  project's actual versions (SQLite 3.45.1 / Django 5.2.16):
  `bulk_create(update_conflicts=True)` **does** return objects with `pk` set,
  including for the conflicting rows that were updated rather than inserted —
  i.e. it works on a re-run, which is the case that matters. Postgres behaves
  the same (both backends support `RETURNING`). Even so, a
  `dict(Product.objects.values_list('registry_id', 'pk'))` lookup between the
  steps costs **0.02 s** and removes the backend dependency entirely — cheap
  insurance, recommended.
- **F2 — `delete()` all + `bulk_create`.** Simplest and matches the snapshot
  semantics, but **cascades into user data** the moment S-02 exists. A trap;
  reject explicitly so nobody rediscovers it later.
- F3 — staging table + swap. Correct but over-engineered for 22.8k rows and F-01's
  "one-shot load, not a pipeline" scope.

For the through-table, D1a's lack of a unique key means per-product
**delete-and-recreate links** inside the transaction is the clean move — link
rows have no external FKs, so nothing cascades.

Wrap the load in a single `transaction.atomic()` so a mid-file failure leaves the
previous snapshot intact. Use `batch_size` on `bulk_create` (SQLite has a
variable limit). The command must be **idempotent**: running it twice on the same
file must be a no-op.

## 10. Decision G — placement and repo obligations

- **New Django app `registry`**, not an addition to `households`. Different
  bounded context: `households` is user data, this is reference data.
- Management command → `registry/management/commands/import_registry.py`, giving
  the roadmap's "one repeatable command".
- **Add `"registry"` to `[tool.mypy] files` in `pyproject.toml`** (currently
  `["households", "domowa_apteka"]`) or the new app silently escapes type checking.
- Any new dependency goes through **`uv add`** — the CI `check` job runs
  `uv sync --locked` and a drifted lock fails Railway's build too.
- **Tests must run offline.** `sample-products.xml` in this folder is ready for
  that: 8 products covering single-substance, 19-substance, duplicate-substance
  rows, veterinary, substance-less-with-fallback, substance-less-with-nothing,
  and a `Xanax` row from the 48 that share that name. It lives here as research
  evidence; **when it becomes a test fixture, `/10x-plan` should re-home it under
  the `registry` app** — data files under `context/` read as planning artifacts.

---

## 11. Recommended combination

Bulk `overall.xml` 6.0.0 (only option) → URL from env → stream to temp file →
stdlib `iterparse` + `clear()` → `Product` / `Substance` / link tables with
verbatim source rows → snapshot upsert keyed on registry `id`, withdrawn-marking
instead of deletion → `stanNaDzien` stored as `source_as_of` → E1 vocabulary-
grounded fallback **plus the § 8a placeholder denylist**, both marked per row →
one idempotent management command.

Measured budget, all four parts measured separately:

| Step | Time |
| --- | --- |
| Download 73.7 MB | 2.7 s |
| Parse, `iterparse` + `clear()` | 9.9 s (7 MB peak memory) |
| Upsert 22,823 products + map PKs | 0.24 s |
| Insert 29,064 link rows | 0.29 s |
| **Total** | **≈ 13.1 s** |

DB timings are in-memory SQLite; on-disk SQLite and networked Postgres will be
slower, but the parse dominates by ~20×, so the shape holds. Comfortable on
Railway either way.

## 12. Risks

1. **Version lifecycle.** `6.0.0` is in the URL; 5.0.0 was retired on a published
   schedule and is still served today. Env-var config (§ 6) means the switch is
   a variable change, not a deploy. Assert the root tag's namespace on parse and
   fail loudly rather than importing garbage.
2. **Scope creep**, the roadmap's own stated hazard. F-01 is a one-shot load.
   Scheduling belongs to F-02; autocomplete indexing belongs to S-02.
3. **Silent partial import.** Assert a plausible product count before committing
   the transaction — a truncated download otherwise looks like a successful load
   of 300 products.
4. **`(product, substance)` non-uniqueness** (§ 3) will break a naive
   `unique_together` in migration, discovered only against real data. It is in
   `sample-products.xml`, so a test will catch it.
5. **Placeholder substances silently poisoning duplicate detection** (§ 8a) —
   the highest-severity finding here, because it produces confidently wrong
   output in S-03 rather than a visible failure.

## 13. Open questions for the user

1. **Vet products** — load all 22,823 and filter in the UI (A2, recommended), or
   ingest human-only (A1)?
2. **Substance-less fallback** — E0 (1,054 unresolved, no inference at all),
   **E1** (555 unresolved; infers the product→substance link but only for
   vocabulary-attested strings, and marks every such row; recommended), or E2
   (7 unresolved, same inference with no filter)? This is the one decision where
   the NFR's "no guessing" rule actually has teeth — see § 8 for why E1 is not
   inference-free.
3. **HTTP client** — stdlib `urllib` (zero deps) or add `requests`?
4. **Do withdrawn products stay visible?** Recommendation is to keep and mark
   them, which S-02/S-03 must then account for.
5. **The placeholder denylist (§ 8a)** — do you accept a short hand-maintained
   list of non-substance values (`Produkt złożony`, `Preparat złożony`,
   `Wyciągi alergenowe`, …)? Without it S-03 will flag 78 unrelated products as
   full duplicates of each other. Recommendation: yes, kept literal and short.

## 14. By-products for later items

- **F-02's unknown is largely answered:** there is no ETag/Last-Modified, so
  freshness cannot come from HTTP. `stanNaDzien` is the registry's own as-of
  date and is the right thing to persist and surface — an app-side value, which
  is what the roadmap already argued for.
- **S-02's disambiguation unknown has a shape:** `Xanax` appears on 48 rows,
  `Bibloc` 41, `Diuver` 39. Autocomplete must disambiguate on `moc` (strength) +
  `nazwaPostaciFarmaceutycznej` (form), both present on every product.
- **PRD Open Question 3 is resolved:** bulk XML file, published daily, no API,
  no incremental feed by publisher decision.
