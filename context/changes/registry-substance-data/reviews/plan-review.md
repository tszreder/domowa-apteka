<!-- PLAN-REVIEW-REPORT -->
# Plan Review: Registry-backed product and active-substance data (F-01)

- **Plan**: `context/changes/registry-substance-data/plan.md`
- **Mode**: Deep
- **Date**: 2026-08-12
- **Verdict**: REVISE at review time → **SOUND** after triage (2026-08-13)
- **Findings**: 0 critical, 7 warnings, 2 observations — all 9 triaged, all 9 fixed in the plan
- **Triage**: F1 Fix B · F2 Fix · F3 Fix A · F4 Fix · F5 Fix A · F6 Fix · F7 Fix · F8 Fix ·
  F9 Fix (`db_index=True`). Per-finding outcomes are recorded on each `Decision:` line below.

---

## How to read this report

### What this change is, in one paragraph

The Polish national medicine registry publishes **one big XML file every day** (~74 MB)
listing every registered medicine and its active substances. This change (roadmap item
**F-01**) builds the piece that downloads that file, reads it, and copies the relevant parts
into this app's own database tables — via **one command you can re-run any time**
(`manage.py import_registry`). Nothing user-facing is built here; this is the data foundation
that the next slice (**S-02**: type a product name → see its active substances) sits on top of.

If it helps to anchor it in familiar terms: this is an **ingestion pipeline**. Extract (download
the file), transform (read the XML into records, applying the correctness rules), load (write
into tables). The difference from an ADF pipeline is that all three steps live inside the
application as Python code, and the "trigger" is a command rather than a schedule — scheduling
is deliberately deferred to the next item, F-02.

### What a plan review is

The plan has not been implemented yet. This review reads the plan as a **contract** and asks:
if someone follows this document literally, will they end up with the thing it promises? It is
looking for gaps, contradictions and unverified assumptions **before** any code is written,
because a flawed plan costs hours and a flawed review costs minutes.

**Important**: none of the findings below say the plan's approach is wrong. It's a strong plan
— zero critical findings, and it already caught its own two hardest problems. Every finding is
a **follow-through gap**: something the plan itself established but didn't carry all the way
into the phases, the tests, or the success criteria.

### The two ratings on every finding, and what they mean

| Rating | Question it answers |
|---|---|
| **Severity** (CRITICAL / WARNING / OBSERVATION) | How bad is it if this ships unaddressed? |
| **Impact** (LOW / MEDIUM / HIGH) | How much of *your* attention does the decision deserve? |

They are independent. A finding can be serious but trivial to decide (obvious one-line fix), or
mild but genuinely worth thinking about (a real trade-off with no clean answer). **Impact is
about decision effort, not danger.**

### What you can decide, per finding

For each one you can: **apply the recommended fix**, **apply the alternative fix** (where two
are offered), **fix it differently**, **skip it** (not worth it now), **accept the risk**
(understood, handle it during implementation), or **disagree** (not actually an issue).
Consciously skipping a low-impact finding is a valid outcome, not negligence. Each finding
carries a `Decision: PENDING` line, which is how `/10x-plan-review` picks up where you left off.

### Vocabulary used throughout

These terms recur in the findings. Cross-references point at existing notes in
`docs/learning/` rather than repeating them here.

| Term | What it means here |
|---|---|
| **Parser** | The code that reads the XML file and turns it into plain Python records held in memory. No database, no network — so it can be tested offline. It owns all the correctness-critical rules. |
| **Loader** | The code that takes those records and writes them into database tables. Deliberately dumb: it decides *where rows go*, never *what a substance is*. |
| **Management command** | A named entry point you run from a terminal: `manage.py import_registry`. Roughly the role a stored procedure or a job step plays elsewhere. |
| **Snapshot load** | Every run reads the complete current file. The publisher deliberately retired their "changed rows only" feed, so there is no delta signal to consume — full reload is the only supported mode. |
| **Idempotent / upsert** | Running the same load twice leaves the database in an identical state — matched rows updated in place, new rows inserted, nothing duplicated. The `MERGE` idea. |
| **Fixture** | A small hand-picked sample XML file (~11 products) committed into the repo so automated tests run offline, in a second, without the real 74 MB file. See [`automated-testing-types-and-django-mechanics.md`](../../../../docs/learning/automated-testing-types-and-django-mechanics.md). |
| **A test that cannot fail** | If you deliberately break the rule and the test still passes, the test proves nothing. The plan gates on this explicitly (criterion 2.3). |
| **The denylist** | The registry sometimes writes a *category word* — `Produkt złożony` ("combination product") — in the field where a substance name belongs. Loaded as if it were a real substance, 78 unrelated products would appear to share an ingredient and get flagged as the same medicine. The denylist is a short, literal, exact-match list of those words. |
| **The E1 / common-name fallback** | Some products carry no substance rows at all. If such a product's "commonly used name" is a string the registry *itself* uses as a substance name somewhere else in the same file, the parser accepts it — but tags the link `source_field='common_name'` so it is never presented as something the source stated outright. |
| **`ParseResult`** | The single object the parser hands to the loader: the product records, the snapshot's as-of date, and counts. |
| **Namespace** | A version stamp written into the top of the XML (`…eksport-danych-v6.0.0`). Think of it as the contract version on an incoming feed. |
| **Environment variable** | A config value set outside the code (a Railway service variable in production), so changing it does not require a code deploy. See [`config-in-dev-vs-prod.md`](../../../../docs/learning/config-in-dev-vs-prod.md). |
| **Migration** | The generated script that creates or alters database tables to match the model classes. Generated from the *field definitions*, not from prose around them. See [`orm-models-and-sql-ddl.md`](../../../../docs/learning/orm-models-and-sql-ddl.md). |
| **`db_index=True`** | Tells Django to create a database index on that column. |
| **`bulk_create` / `batch_size`** | Insert many rows in one statement. Every value becomes a bound parameter, and database engines cap how many parameters one statement may carry — hence batching. |
| **Dev vs production database** | Local development and the test suite run on SQLite; production on Railway runs Postgres. Behaviour is *mostly* identical but not guaranteed to be. See [`database-migrations-and-dev-prod-parity.md`](../../../../docs/learning/database-migrations-and-dev-prod-parity.md). |

---

## Decision summary

Nine decisions, but they are not nine equal decisions. One is architectural; four are
near-mechanical.

| ID | In one line | Impact | The review recommends |
|---|---|---|---|
| **F1** | The only route for getting data into the live production database has never been proven to work. | 🔬 HIGH | Test the route before Phase 4 **and** write the known-working fallback into the plan (Fix A) |
| **F2** | The memory target was copied from a different experiment, so the phase gate can't pass. | 🔎 MEDIUM | Measure the real design, write the real number in both places |
| **F3** | The claim "a version change costs no deploy" is cancelled by a hard version check elsewhere in the plan. | 🔎 MEDIUM | Make the check follow the configured URL (Fix A) |
| **F4** | Four tests the plan promises have no data to run against. | 🔎 MEDIUM | Name the missing sample data, and build test variants at test time |
| **F5** | Two date columns that hold the same value forever; the next slice reads one of them. | 🔎 MEDIUM | Keep one column (Fix A) |
| **F6** | The parser doesn't hand the loader a list the loader needs, and the workaround has an unstated failure. | 🏃 LOW | Put the list on `ParseResult` |
| **F7** | The version check fires only after the whole 74 MB file has been read. | 🏃 LOW | Check it at the start of the file instead |
| **F8** | Two loader steps could approach the database's per-statement parameter ceiling. | 🏃 LOW | Filter on the snapshot date instead of a list of ids |
| **F9** | A column described as indexed isn't specified as indexed. | 🏃 LOW | Add the flag, or drop the claim |

---

## Verdicts

The review scores the plan on five dimensions. Plain-language version of each question in the
right-hand column.

| Dimension | Verdict | The question it asks |
|-----------|---------|----------------------|
| End-State Alignment | WARNING | Follow every phase in order — do you actually end up with what the plan promised? |
| Lean Execution | PASS | Is there anything here that could be deleted without losing the end state? |
| Architectural Fitness | PASS | Does this fit how the rest of the codebase is already built? |
| Blind Spots | WARNING | What did the plan not think about — failures, rollback, cost, testing gaps? |
| Plan Completeness | WARNING | Is it specific enough to hand over without the implementer having to guess? |

**Overall: REVISE** — needs targeted fixes, not a rethink. Nothing here questions the approach.

**After triage (2026-08-13): SOUND.** All three WARNING dimensions were warnings because of
findings that have now been fixed in `plan.md` — End-State Alignment via F3, Blind Spots via
F1/F2/F8, Plan Completeness via F4/F5/F6/F7/F9. The verdicts above are preserved as they stood
at review time.

## Grounding

Before judging the plan's ideas, the review checked its **facts** — every file path it claims
to touch, every symbol and config key it names, and the actual contents of the sample XML.
Everything checked out, which is why no finding below is "the plan got a fact wrong".

9/9 paths ✓, 7/7 symbols ✓, brief↔plan ✓

- `pyproject.toml:22` — `files = ["households", "domowa_apteka"]` ✓
- `.github/workflows/deploy.yml:49` — `uv run mypy` ✓
- `domowa_apteka/settings.py:74-82` — `INSTALLED_APPS` holds `django.contrib.*` + `households` only ✓
- No `management/` directory anywhere in the repo ✓
- Fixture root namespace `http://rejestry.ezdrowie.gov.pl/rpl/eksport-danych-v6.0.0` + `stanNaDzien="2026-08-07"` ✓
- `sample-products.xml:59-60` Altacet repeats `Aluminii acetotartras` at 1000/100 mg ✓; `:163` Parvoerysin multi-paragraph `moc` ✓; `:225` Beto 200 ZK `typProcedury="IR"` with `ulotkaImportRownolegly` + `oznaczenieOpakowanImportRownolegly` and `<substancjeCzynne />` ✓
- Fixture holds 33 distinct `nazwaSubstancji` values, none denylisted, no `Metoprololi succinas` — the plan's Key Discoveries about the fixture are accurate ✓
- options.md §4 recommended A2 (load everything, filter at query time); the plan takes A1 (human-use only) and reconciles it by storing `kind` so the filter can widen without a migration — a recorded decision, not drift ✓

Overall read: a strong plan. Zero criticals, genuinely measured research, and it already
self-caught its two hardest problems (the forward-referencing E1 vocabulary; the fixture's
inability to exercise the denylist). Every finding below is a follow-through gap on something
the plan itself established — not a disagreement with its approach.

## Findings

### F1 — Phase 4's only production path was never verified to work

- **Severity**: ⚠️ WARNING
- **Impact**: 🔬 HIGH — architectural stakes; think carefully before deciding
- **Dimension**: Blind Spots
- **Location**: Phase 4 § 2 — One-off production import
- **Detail**: Phases 1–3 build and test everything **on your laptop**. Phase 4 is the step where
  the data actually lands in the live production database — without it, the feature exists but
  the deployed app has empty tables. The plan gives exactly one route for that step: run
  `railway ssh` to open a shell **inside the running production container**, then run the import
  command from in there.

  The problem: nobody has ever confirmed `railway ssh` reaches this container. The project's own
  deployment notes record that this route was attempted once (when creating the admin user), was
  **abandoned**, and a different technique was used instead — one that needs no shell at all:
  temporarily add the command to the container's startup line, deploy, confirm in the logs,
  then revert. Those notes end with "Reuse this shape for any future one-off management command."

  The plan rejects that known-working technique on the grounds that "it runs on every container
  start, so every restart would re-download 74 MB". That objection is true only if you *leave it
  in permanently* — the documented shape is add → deploy → confirm → revert, exactly once. The
  second objection (the platform's health check would be left waiting) is also measurable rather
  than theoretical: the import measured ~13 s, the web server starts right after it, and the
  health-check timeout is configurable up to 300 s.

  So the plan has made an **unverified capability the single path** to the end state, while
  ruling out the one path this project has actually executed end to end. The project's first
  recorded recurring rule is "verify a platform limitation before registering it as a risk" —
  this is that rule's mirror image.
  - Evidence: `context/deployment/deploy-plan.md:269-277` (the SSH key was "created while trying
    to reach the container, then made redundant by the `startCommand` workaround", kept only "if
    a human intends to use `railway ssh` interactively"); `:256-266` (the four-step technique
    that did work, and the instruction to reuse it); `railway.json` allows
    `healthcheckTimeout: 300`; import measured ~13 s in options.md §11;
    `context/foundation/lessons.md` rule 1.
- **Fix A ⭐ Recommended**: Before Phase 4 starts, actually run `railway ssh` once and confirm it
  reaches the container — make that an explicit precondition in the plan. Then also write the
  temporary-startup-line technique into Phase 4 as the documented fallback, with its objection
  corrected (it is a revert-after-use step, not a permanent edit).
  - Strength: Costs one interactive command before the phase begins. If it works you keep the
    cheap path; if it doesn't, the fallback is the one this repo has already executed
    successfully on this exact service.
  - Tradeoff: Phase 4 gains a precondition step and a branch, so the document is slightly longer.
  - Confidence: HIGH — the deploy notes supply both the reason to doubt and the ready-made
    fallback; nothing new is being invented here.
  - Blind spot: Whether the SSH key still exists — the deploy notes mark it "safe to remove", so
    it may already be gone.
- **Fix B**: Drop `railway ssh` from the plan entirely and make the temporary-startup-line
  technique the primary path.
  - Strength: One path instead of two, already proven once on this exact service, and it needs
    no terminal session and no interactive shell — so it can be driven start to finish without a
    human holding a connection open.
  - Tradeoff: Two extra deploys (add, then revert), and a revert you must not forget — leaving it
    in really would re-download 74 MB on every container restart.
  - Confidence: HIGH that the mechanism works; MEDIUM that a ~13 s import behaves the same on
    Railway's disk and network as on a laptop.
  - Blind spot: Import duration in production is unmeasured — the only number that exists is the
    local 13.1 s budget.
- **Decision**: FIXED via Fix B — `railway ssh` removed from the plan; Phase 4 § 2 now documents
  the three-step temporary-`startCommand` shape (add → deploy → confirm → **revert**) as the
  only path, with the healthcheck margin and the unmeasured production duration stated. New
  success criterion + Progress 4.7 gate the revert.

### F2 — Memory criterion measures a parser the plan doesn't build

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Blind Spots
- **Location**: Phase 2 Manual Verification / Progress 2.6 / Performance Considerations
- **Detail**: Phase 2 has a sign-off checkbox: "peak memory during that parse stays in the
  single-digit MB range", and the Performance section repeats the headline figure "peak Python
  memory is 7 MB".

  That 7 MB came from the research script — but **that script read each product, counted it and
  threw it away**. The design in this plan does the opposite: `parse_registry()` builds and
  *keeps* roughly 20,187 product records plus 29,064 substance-link records, packages them all
  into one `ParseResult`, and hands the whole thing to the loader. Holding ~50,000 records in
  memory costs tens of MB, not single digits — so the checkbox, as written, **cannot pass**, and
  it will look like a failure of the code rather than a mismatched target.

  The familiar version of this: measuring throughput while streaming rows one at a time, then
  quoting that number for a job that materialises the entire result set first.

  Worth separating out, because it's easy to conflate: `elem.clear()` — the call that releases
  each XML element after it's been read — is still essential and still doing its job. Without it
  the whole 74 MB document stays in memory as a parsed tree (roughly 1 GB) and the production
  container runs out of memory. It's just no longer the *only* thing determining peak usage, so
  a single number can no longer prove it's working.
  - Evidence: options.md §1 describes the discard-pass it measured. The plan's own Phase 2 § 2
    contract materialises `ParseResult` and Phase 3 § 3 consumes it whole. At a conservative few
    hundred bytes per record (13 string fields per product, 8 per link) plus the ~4,267-entry
    substance vocabulary, peak lands in the tens of MB.
- **Fix**: During Phase 2, measure the design that is actually being built and write the real
  number into **both** places (the criterion / Progress item 2.6 **and** the Performance
  Considerations paragraph). Split the criterion in two: the streaming portion stays single-digit
  MB — that is what proves `elem.clear()` works — while total peak, including the retained
  `ParseResult`, stays under the newly measured budget.
  - Strength: Keeps the architecture the plan argues for, and replaces an inherited number with
    one measured against the real thing.
  - Tradeoff: The quotable "7 MB" headline leaves the plan.
  - Confidence: HIGH — options.md §1 states plainly that it measured a discard pass.
  - Blind spot: Switching to a streaming design that yields records one at a time looks like the
    obvious alternative, but saves less than it appears: loader step 1 needs the complete
    substance list up front, and step 3 needs the complete product-id map, so most of the data
    comes back into memory anyway.
- **Decision**: FIXED — Phase 2 Manual Verification now demands two separately measured figures
  (streaming-pass peak, which is what proves `elem.clear()`; total peak with the materialized
  `ParseResult`). Progress 2.6 split into 2.6/2.7; Performance Considerations rewritten and the
  inherited 7 MB retired.

### F3 — The namespace assert cancels the env var it's paired with

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: End-State Alignment
- **Location**: Critical Implementation Details ↔ Phase 2 § 2 parser contract
- **Detail**: The download URL contains a version number: `…eksport-danych-v6.0.0/…`. The
  publisher retires versions on a published schedule — 5.0.0 went that way and is still being
  served. The plan's stated reason for putting that URL in an **environment variable** is exactly
  this: "the switch must not require a code deploy" — you change a setting in the hosting
  platform, restart, done. The risk register in `plan-brief.md` accordingly records the
  version-lifecycle risk as *mitigated*.

  But Phase 2's parser also hard-checks the version stamp written inside the file, requiring it
  to be exactly `…eksport-danych-v6.0.0`, and refuses anything else. So the moment you point the
  environment variable at a 7.0.0 URL — or roll back to the still-served 5.0.0 — **every import
  fails at that check**. For the precise scenario the environment variable was justified by, it
  mitigates nothing. It only covers the URL's host or path moving *within* 6.0.0.

  To be clear about what is and isn't wrong: **the check itself is right.** Reading a 7.0.0 file
  as though it were 6.0.0 should fail loudly rather than half-succeed with silently wrong data.
  What's wrong is the claim written around it, and a risk that is recorded as handled when it
  isn't.
- **Fix A ⭐ Recommended**: Make the expected version stamp follow the configured URL, so the two
  can never disagree — either read the version out of the URL's path segment, or add a second
  environment variable for the namespace right next to the URL one, so they're changed together.
  - Strength: The check stays strict, and the "no deploy needed" claim becomes true.
  - Tradeoff: It buys you the *chance* to switch without a deploy, not a guarantee — a 7.0.0 file
    could still rename elements deeper inside, so it becomes "point it at the new URL and find
    out" rather than "free".
  - Confidence: MEDIUM — 6.0.0's shape is measured; 7.0.0's is unknowable until it exists
    (options.md §2: 7.0.0 currently returns an error).
  - Blind spot: Whether a future 7.0.0 export keeps the same element names for products and
    substances.
- **Fix B**: Leave the check pinned to 6.0.0 and correct the wording instead — state plainly that
  a version bump costs a URL change **plus** a namespace change **plus** re-reading the new
  schema, i.e. a code deploy, and that the environment variable covers host/path moves only.
  - Strength: Zero code change — a documentation edit.
  - Tradeoff: The version-lifecycle risk loses its recorded mitigation and goes back to being an
    open risk you carry knowingly.
  - Confidence: HIGH — nothing to verify.
  - Blind spot: None significant.
- **Decision**: FIXED via Fix A — the namespace is derived from the configured URL, not pinned.
  `registry/parser.py` gains a pure `namespace_for_url(url) -> str`; `parse_registry` takes
  `expected_namespace` as an argument (keeping the parser settings-free) and the command derives
  it from `--url` or `settings.REGISTRY_OVERALL_URL`. No second env var. The plan now states
  plainly that this buys the *chance* to switch versions without a deploy, not a guarantee.

### F4 — Fixture work doesn't produce the data four planned tests need

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Plan Completeness
- **Location**: Phase 2 § 3 (fixture) ↔ Phase 2 § 4 and Phase 3 § 5 test lists
- **Detail**: The automated tests run against `sample-products.xml` — a small committed sample of
  the real export, so tests need no internet and no 74 MB file. A test can only check a rule if
  the sample **contains data that triggers that rule**.

  The plan already spotted that the current sample can't exercise two of its highest-risk rules,
  and adds four products to fix exactly those. Good. But four *other* tests it promises still
  have nothing to run against:

  - **The case-folding test.** Two substance names differing only in capitalisation must merge
    into one entry, and the spelling seen first must be the one displayed. The sample's 33
    distinct substance names contain no such pair — the real-world one (`Sodu fluorek` /
    `sodu fluorek`) isn't among them, and the four additions don't add one.
  - **Three loader tests need input files nobody creates**: "a reduced fixture omitting one
    product" (to prove a withdrawn product is marked inactive rather than deleted), "a fixture
    where a product's strength changed" (to prove updates land), and "a fixture where a
    case-collision pair appears in the opposite order" (to prove the first-seen spelling survives
    a re-run). The plan never says whether these are extra committed XML files or built on the
    fly when the test runs.

  Why this matters more than it sounds: a test with no data doesn't fail loudly — it quietly gets
  dropped during implementation, or someone invents a hand-made file on the spot. And these
  particular rules are the ones that decide whether a substance name a user sees can silently
  flip between two spellings from one import to the next.
  - Evidence: verified directly against the fixture's 33 `nazwaSubstancji` values and against the
    plan's own extension list in Phase 2 § 3.
- **Fix**: Name the specific case-collision pair to add to the main sample, and specify that the
  three loader variants are produced **at test time** by editing a copy of the sample's text in
  memory (or as small purpose-built inline XML snippets) — not as three hand-authored full-size
  files.
  - Strength: Makes tests the plan has already committed to actually runnable, and keeps one
    sample file as the single source of truth.
  - Tradeoff: Generating a variant in test code is slightly more code than committing a second
    static file.
  - Confidence: HIGH — verified directly against the fixture's contents.
  - Blind spot: None significant. (Three hand-maintained near-copies would drift apart from the
    main sample over time — that's the failure mode this avoids.)
- **Decision**: FIXED — the fixture extension list gains a fifth item: the real `Sodu fluorek` /
  `sodu fluorek` pair, with document order pinned as part of the fixture's contract. Phase 3 § 5
  now specifies the three loader variants are built at test time by mutating a copy of the
  fixture text into a `tempfile`, not committed as near-copies.

### F5 — `source_as_of` and `last_seen_as_of` are the same value forever

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Plan Completeness
- **Location**: Phase 1 § 2 (Product model) ↔ Phase 3 § 3 (loader steps 2, 5)
- **Detail**: The Product table gets two date columns:

  - `source_as_of` — "the date stamped on the snapshot this row came from"
  - `last_seen_as_of` — "the date of the most recent snapshot that still contained this product"

  This is the familiar audit-column pair: one records when a row *first* appeared, the other when
  it was *last* confirmed. The trouble is the plan defines two columns but only one write rule.
  Loader step 2 says it updates "every mutable field plus `last_seen_as_of`" — without saying
  whether `source_as_of` counts as mutable. Both readings are unsatisfying:

  - **If it does count**: every row gets both columns set to the same date on every run — because
    products present in the snapshot get both updated, and products absent from it get neither
    (step 5 explicitly leaves `last_seen_as_of` alone). One of the two columns carries no
    information, ever.
  - **If it doesn't**: `source_as_of` silently comes to mean "the first snapshot we ever saw this
    product in" — which contradicts the plan's own scope note that freshness lives on the product
    as `source_as_of`.

  Whoever implements it will pick one, and **F-02 — the scheduled refresh, the very next roadmap
  item — inherits that guess** when it answers "is this data stale?".
- **Fix A ⭐ Recommended**: Keep one column. Drop `source_as_of`, use `last_seen_as_of` as the
  freshness value, and update the two prose sections ("What We're NOT Doing" and Desired End
  State) that currently name the other one.
  - Strength: Removes a column that carries no information under either reading. `last_seen_as_of`
    already means freshness and already has clear write rules in loader steps 2 and 5.
  - Tradeoff: Two prose sections need editing.
  - Confidence: HIGH — the redundancy follows from the plan's own step definitions, not from any
    assumption about the data.
  - Blind spot: F-02 isn't designed yet. If it turns out to want both "first seen" and "last
    seen", Fix B is the better shape.
- **Fix B**: Keep both columns, with explicit and different write rules — `source_as_of` written
  once when the row is first inserted and never touched again, `last_seen_as_of` updated on every
  snapshot that contains the product — and state which of the two F-02's freshness check reads.
  - Strength: Preserves a genuine "first seen" date, which a full-snapshot source can never
    reconstruct once it's lost.
  - Tradeoff: "Write once on insert, never update" is an extra rule in the loader and an extra
    test to prove it, and nothing in this change or the next one actually reads it.
  - Confidence: HIGH — mechanically simple either way.
  - Blind spot: Whether anything downstream will ever read the first-seen date.
- **Decision**: FIXED via Fix A — `source_as_of` dropped from the `Product` model.
  `last_seen_as_of` is named as the freshness value F-02 reads, with the reasoning recorded so
  nobody re-adds the column. Ripple edits applied: "What We're NOT Doing", the admin
  `list_display`, and loader step 2 (`last_seen_as_of = result.source_as_of`).
  `ParseResult.source_as_of` survives as the in-memory parsed snapshot date.

### F6 — `ParseResult` doesn't carry the vocabulary loader step 1 consumes

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Completeness
- **Location**: Phase 2 § 2 (ParseResult) ↔ Phase 3 § 3 (loader step 1)
- **Detail**: The parser hands the loader one object, `ParseResult`. The plan specifies it as
  carrying the products, the snapshot date, and some counts. But the loader's very first step is
  "insert the substance names that aren't in the table yet" — and there is **no list of substance
  names on `ParseResult`**, so the loader has to rebuild it by walking through every product's
  links.

  That's not just extra work; it leaves two things unspecified that will bite:

  1. The rebuilt list must be **de-duplicated on the lowercase key within the batch**. Otherwise
     the batch insert violates the "one row per substance key" uniqueness rule the first time a
     single file contains two names differing only in capitalisation — and the real file contains
     5 such pairs.
  2. **Which spelling survives that de-duplication *is* the "first one seen wins" rule** the plan
     pins elsewhere. It can't be left to whatever order the loader's rebuild happens to produce,
     or the name a user sees can flip between imports.

  Triage note: F4 is a prerequisite. The sample file cannot currently produce a within-batch
  collision at all, so this fix isn't provable by a test until F4 adds one.
- **Fix**: Have the parser put an ordered, de-duplicated substance list on `ParseResult` — it is
  already building exactly that list while it streams — and have loader step 1 compare against it
  directly instead of reconstructing it.
- **Decision**: FIXED — `ParseResult.substances` added to the Phase 2 § 2 contract as an ordered,
  `name_key`-deduplicated sequence of `(name, name_key)` in first-seen order, with both failure
  modes recorded. Loader step 1 diffs against it and is explicitly forbidden from re-deriving the
  vocabulary by walking links. Now test-provable, since F4 adds the collision pair.

### F7 — The version guard fires last, after the whole file is streamed

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Completeness
- **Location**: Phase 2 § 2 — parser contract, bullets 1 and 2
- **Detail**: The parser reads the XML incrementally, and the plan specifies it should listen only
  for **"element finished"** events. The catch: the outermost element — the one carrying both the
  version stamp and the snapshot date — only "finishes" at the very end of the document.

  So two things happen too late:

  - The version check the plan describes as a loud, early failure ("importing a 7.0.0 file as
    though it were 6.0.0 must fail, not half-succeed") can't fire until all 73.7 MB have already
    been read.
  - The snapshot date has the same problem, and that one is worse — every product record needs it
    while it's being built, long before the end of the file.
- **Fix**: Listen for **"element started"** events as well as "finished" ones — i.e. request
  `events=('start', 'end')` instead of the plan's "default `end` events" — and validate the
  version stamp and the snapshot date on the very first "started" event, before entering the
  product loop.
- **Decision**: FIXED — the parser contract now specifies `events=('start', 'end')`, validates the
  root tag, namespace and `stanNaDzien` on the first `start` event before the product loop, and
  records *why* the `end` event is too late (fires only after 73.7 MB, and leaves `stanNaDzien`
  unavailable while product records are built). `elem.clear()` is pinned to the `end` event.

### F8 — Loader steps 4 and 5 bind one SQL parameter per product

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Blind Spots
- **Location**: Phase 3 § 3 — loader steps 4 and 5
- **Detail**: Two loader steps operate on "all the products in this snapshot" (step 4: clear their
  old substance links) and "all the products *not* in this snapshot" (step 5: mark them inactive).

  Written the obvious way — as a list of product ids in a `WHERE id IN (…)` clause — each of
  those sends **one bound parameter per product**: 20,187 of them today. Every database engine
  caps how many parameters a single statement may carry. (Azure SQL's 2,100 is the familiar
  cousin; the number that applies here is SQLite's.) **Django does not split these two
  operations into batches automatically** — it batches inserts, but a delete or update filtered
  by an id list goes out as one statement, however long the list is.

  Measured in this environment (Python 3.11.9 / SQLite 3.45.1): the ceiling is **32,766**. 20,187
  parameters succeed; 32,767 raise `too many SQL variables`. So it works today with about 38%
  headroom — and no test will ever see it, because the sample file holds ~11 products. It would
  surface the day the registry grows past the ceiling, in production, on a routine refresh.

  Worth noting the plan already passes `batch_size` to every bulk insert **for this exact
  reason** — it just doesn't apply the same thinking two steps later.
- **Fix**: After step 2 has stamped the snapshot date onto every product in this snapshot, express
  both steps as a comparison against that date rather than as a list of ids — step 4 as
  `ProductSubstance.objects.filter(product__last_seen_as_of=source_as_of).delete()`, step 5 as
  `Product.objects.exclude(last_seen_as_of=source_as_of).update(is_active=False)`. That's one
  parameter total instead of 20,187: simpler than the id lists, and the ceiling disappears rather
  than being worked around with batching. (This works under either F5 outcome — it needs one
  snapshot-date column, not both.)
- **Decision**: FIXED — loader steps 4 and 5 now select on `last_seen_as_of = result.source_as_of`
  (set in step 2) instead of id lists, with the measured 32,766 ceiling, the "Django does not
  chunk `__in` on the fast-delete path" reason, and the "no test can see this" note recorded in
  the plan. Consistent with F5's single-column outcome.

### F9 — `Product.name` is described as indexed but the field spec isn't

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Completeness
- **Location**: Phase 1 § 2 — Product model contract
- **Detail**: The plan's prose for the product-name column says "Indexed: S-02 will search it" —
  but the field definition next to it omits `db_index=True`, unlike two other columns where the
  flag is written out explicitly.

  Database tables are generated from the **field definitions**, not from the prose around them,
  so as written no index is created — while Phase 1's admin page puts a search box over that same
  column across ~20,000 rows. The gap is silent: nothing fails, the search is just slower than
  the plan assumes.
- **Fix**: Either add `db_index=True` to the field definition, or delete the "Indexed" claim and
  let S-02 add the index once it knows the shape of the query it needs.
- **Decision**: FIXED — `db_index=True` written into the `Product.name` field spec, with a note
  that the flag belongs in the spec rather than only in the prose because `makemigrations` reads
  the spec.
