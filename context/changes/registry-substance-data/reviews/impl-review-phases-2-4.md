<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: Registry-backed product and active-substance data (F-01)

- **Plan**: `context/changes/registry-substance-data/plan.md`
- **Scope**: Phases 2–4 of 4 — Parser · Loader and management command · Production load
  (Phase 1 reviewed separately in `impl-review-phase-1.md`)
- **Date**: 2026-08-14
- **Verdict**: NEEDS ATTENTION
- **Findings**: 0 critical, 4 warnings, 6 observations — all 10 triaged (2026-08-14)
- **Triage**: F1 Fix A · F2 Fix A · F3 skipped · F4 fixed · F5 fixed · F6 fixed + recorded as a
  rule · F7 fixed · F8 fixed · F9 accepted as risk · F10 skipped. Per-finding outcomes are on
  each `Decision:` line below. Fixes are on `fix/registry-substance-data-review-fixes`.

## Method note

Reviewed with the skill's two sub-agents (plan drift; safety/quality/patterns) over ~1,270 lines
of new application and test code. Every automated success criterion for phases 2–4 was re-run
from scratch rather than taken from the Progress checkboxes. The two highest-value findings
(F1, F2) and the one test-quality finding (F5) were **confirmed empirically**, not reasoned
about — see the evidence blocks. The mutation check for F5 edited `registry/parser.py`
temporarily and reverted it with `git checkout`; the working tree is clean and matches
`origin/main` at `a4d885a`.

## Change scope

All three phases are **merged to `main` and deployed**. Scope taken from the four PR merge
commits; the pre-squash branch commits (`ad4edf7`, `baef9a7`) were consulted for phase
attribution and the fixture rename.

| Commit | Phase | Files |
| --- | --- | --- |
| `66922aa` (#15) | 1–3 | `registry/{denylist,parser,loader}.py`, `registry/management/commands/import_registry.py`, `registry/tests/{test_parser,test_loader}.py`, `registry/tests/fixtures/{sample-products.xml,README.md}`, `domowa_apteka/settings.py`, `.env.example`, `pyproject.toml`, `uv.lock` |
| `49cd195` (#16) | 4 | `railway.json` — temporary import in `startCommand` |
| `69c7e8f` (#17) | 4 | `railway.json` reverted, `production-baseline.md` added |
| `a4d885a` (#18) | 4 | Progress checkboxes + `change.md` status |

**Nothing planned is missing, and no "What We're NOT Doing" boundary is crossed.** Verified
absent: `ImportRun`/snapshot model, views, urls, ATC/GTIN reads, `+`-splitting, `moc` parsing,
lemmatization, delta pipeline, `defusedxml`, any scheduling. Veterinary exclusion is enforced at
`parser.py:172` and asserted in both test modules.

Housekeeping, outside the findings: `context/foundation/roadmap.md:44` still lists F-01 as
`in-progress` while `change.md` says `implemented`. That is `/10x-archive`'s job, not a defect
in this work.

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| Plan Adherence | PASS |
| Scope Discipline | PASS |
| Safety & Quality | WARNING |
| Architecture | PASS |
| Pattern Consistency | WARNING |
| Success Criteria | WARNING |

## Success criteria

Every automated criterion was re-executed for this review.

| ID | Criterion | Result |
| --- | --- | --- |
| 2.1 | `test registry.tests.test_parser` | PASS — part of 39 registry tests, OK |
| 2.2 | `mypy`, no `type: ignore` in `parser.py` | PASS — 35 files clean; the only `type: ignore` string in the app is inside a docstring at `parser.py:325` |
| 2.3 | Denylist / `source_field` tests fail when inverted | PASS — independently re-confirmed by the sub-agent tracing both mutation paths |
| 2.4 | Fixture move, not delete-plus-add | PASS on the branch — `ad4edf7` records `{context/changes/… => registry/tests/fixtures}/sample-products.xml`. See F3 note: the squash-merge flattened it to an `A` on `main` |
| 2.5 | Real file → ~20,187 human-use products, ≥95% resolved | **UNRECORDED** — see F3 |
| 2.6 | Streaming-pass peak in single-digit MB | **NOT MEASURED AS WRITTEN** — see F3 |
| 2.7 | Total peak measured and written into the plan | PASS — the 30.1 / 27.7 / 2.5 MB table is in Performance Considerations |
| 3.1 | `test registry` | PASS — 39 tests OK |
| 3.2 | `test` (whole suite) | PASS — 72 tests OK |
| 3.3 | `mypy` | PASS — no issues, 35 files |
| 3.4 | `manage.py check` | PASS — no issues |
| 3.5 | `uv sync --locked` | PASS — 26 packages, no drift |
| 3.6 | Import twice → identical row counts | PASS — re-ran against a scratch DB: 12 products / 37 substances / 51 links; second run 0 new, identical 50/1 split |
| 3.7–3.9 | Live-URL timing · 3 brands in admin · temp file removed | UNRECORDED — see F3 |
| 4.1 | CI `check` on the PR | PASS — all 7 runs for #15–#18 succeeded |
| 4.2 | `deploy` completes, healthcheck green | PASS |
| 4.3 | Production import in the local range | PASS — `production-baseline.md`: 20,245 products, 25,884 links (25,468/416), 6.0 s |
| 4.4–4.5 | Production admin rows · brand spot-check | Asserted in `production-baseline.md` prose only — see F3 |
| 4.6 | Second production run reports identical counts | PASS — both runs recorded with counts |
| 4.7 | `railway.json` reverted and redeployed | PASS — verified independently: `49cd195` matched the planned shape exactly, `69c7e8f` restored it byte-identically, and the file on disk carries no import |

Phase 4 §1 also verified: every phase landed through a PR (#15–#18); nothing was pushed
directly to `main`.

## Findings

### F1 — A truncated or malformed snapshot escapes as a raw traceback, and the plausibility guard never runs

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality
- **Location**: `registry/management/commands/import_registry.py:116-120`, `registry/parser.py:57`
- **Detail**: `RegistryParseError` subclasses `ValueError` (`parser.py:57`), but
  `xml.etree.ElementTree.ParseError` subclasses **`SyntaxError`**. So the `except
  RegistryParseError` at `import_registry.py:119` does not catch it.

  `MIN_EXPECTED_PRODUCTS` exists specifically to catch this case — its own comment says
  "far above anything a truncated download would yield" (`import_registry.py:21-26`). But a
  truncated transfer almost always yields **invalid XML**, not valid XML with few products, so
  the likeliest truncation takes the unhandled path and the guard is never reached. Same for an
  HTML error page served with HTTP 200; nothing checks `Content-Type` before parsing.

  **Confirmed empirically** — fixture truncated to 20 KB, passed via `--file`:

  ```
  File "registry/parser.py", line 156, in parse_registry
      for event, elem in events:
  xml.etree.ElementTree.ParseError: unclosed token: line 198, column 12
  ```

  Nothing is written (the parse precedes the transaction), so there is no data-safety
  consequence — the cost is an operator staring at a traceback instead of the intended
  one-line refusal, and a guard that does not do the job it was written for.
- **Fix A ⭐ Recommended**: Wrap the `iterparse` loop in `parse_registry` and re-raise
  `ET.ParseError` as `RegistryParseError`.
  - Strength: Fixes it at the source. The parser already owns `RegistryParseError` for the
    namespace and `stanNaDzien` asserts, so "this file is not the snapshot we were told to
    expect" stays one exception type for every caller — the command today, F-02's scheduler
    tomorrow.
  - Tradeoff: Two extra lines in the parser; none material.
  - Confidence: HIGH — the MRO was checked, and the failure was reproduced end to end.
  - Blind spot: None significant.
- **Fix B**: Catch `ET.ParseError` alongside `RegistryParseError` in `_import`.
  - Strength: One line, no parser change.
  - Tradeoff: Leaks an ElementTree type into the command layer, and the next caller of
    `parse_registry` repeats the mistake.
  - Confidence: HIGH.
  - Blind spot: None significant.
- **Decision**: FIXED via Fix A — `parser.py` gained a `_stream_events(path)` generator that
  re-raises `ET.ParseError` as `RegistryParseError`; `parse_registry` streams through it, so both
  `_read_root` and the product loop are covered by one wrapper. Added
  `OfflinePathTests.test_truncated_snapshot_fails_as_a_command_error` (20 KB-truncated fixture
  built at test time via the existing `write_variant` plumbing). Verified: the truncated file now
  exits with `CommandError: … is not well-formed XML: unclosed token: line 198, column 12`;
  40 tests OK; mypy clean. **Mutation-checked** — reverting `parse_registry` to the bare
  `ET.iterparse` call makes the new test fail, so it is not a test that cannot fail.

### F2 — Re-importing an older snapshot rewinds freshness and deactivates live products, silently

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality
- **Location**: `registry/loader.py:46-58`, `:91-93`, `:145`
- **Detail**: `PRODUCT_UPDATE_FIELDS` includes `last_seen_as_of`, and the upsert stamps it
  unconditionally. Nothing compares the incoming `stanNaDzien` with what is already stored, so
  loading an older file rewinds the column the plan designates as **the** freshness value and
  the one F-02 reads (`plan.md`, Phase 1 § 2). Step 5 then deactivates every product that exists
  today but is absent from the older file.

  The loader's docstring anticipates the *equal-date* variant (`loader.py:23-26`) but not the
  *earlier-date* one, which is both more reachable and worse. It is reachable through the
  project's own documented workflow: `--keep-download` exists to leave snapshots on disk, and
  Phase 2's manual verification tells you to hand-fetch `overall.xml` and pass it via `--file`.
  Sharper still — `REGISTRY_OVERALL_URL` exists precisely so someone can repoint at a different
  version path, and the plan records that **5.0.0 is still served**. If 5.0.0's `stanNaDzien`
  lags 6.0.0's, the single env-var change the variable was created for is enough to trigger
  this. That is the documented reconfiguration path, not an operator slip.

  **Confirmed empirically** on a scratch DB. Loaded a `2026-08-20` snapshot (12 products, all
  active), then loaded a `2026-08-07` snapshot with one product removed:

  ```
  Registry snapshot 2026-08-07
    products loaded:    11 (0 new)
    products inactive:  1
  → 11 of 12 products rewound from last_seen_as_of 2026-08-20 to 2026-08-07
  → DEACTIVATED: 100362527 Addamel N, last_seen_as_of 2026-08-20
  ```

  Note the shape of the corruption: `Addamel N` is now flagged withdrawn while carrying a
  `last_seen_as_of` **newer** than every active product. The command reported success. Fully
  recoverable by re-importing the current snapshot, and nothing surfaces that it happened.
- **Fix A ⭐ Recommended**: Refuse a snapshot older than
  `Product.objects.aggregate(Max('last_seen_as_of'))` unless an explicit `--allow-older` flag is
  passed, raising `CommandError` inside the transaction.
  - Strength: Mirrors the plausibility guard's existing idiom exactly — same place, same
    exception, same rollback — so it costs no new concept. Fails loudly on the one operator
    mistake the CLI surface invites.
  - Tradeoff: One more query per run, and a flag to remember when you genuinely want to reload
    an archived snapshot.
  - Confidence: HIGH — the failure was reproduced with exact row-level effects.
  - Blind spot: An empty table (first run) must be special-cased; `Max` returns `None`.
- **Fix B**: Keep loading, but write `last_seen_as_of` forward only and skip step 5 unless the
  snapshot is the newest seen.
  - Strength: An out-of-order re-import becomes harmless rather than an error.
  - Tradeoff: `Greatest()` is not expressible in `bulk_create(update_fields=…)`, so this needs a
    different write shape for step 2 — a real change to the loader's core, against a plan that
    deliberately kept it dumb.
  - Confidence: MEDIUM — the write-shape change has not been prototyped.
  - Blind spot: Whether the resulting mixed-date table still lets step 4's date predicate stay a
    single bound parameter.
- **Decision**: FIXED via Fix A — `import_registry` gained `--allow-older` and a
  `_reject_older_snapshot()` guard that runs inside `transaction.atomic()` before
  `load_parse_result`, raising `CommandError` when `result.source_as_of` predates
  `Max(last_seen_as_of)`. `newest is None` (first run) passes, and an equal date is explicitly
  not "older" — both pinned by tests. Placed in the command rather than the loader: which
  snapshots are acceptable is policy, and the loader is deliberately dumb about policy.
  Added `SnapshotOrderTests` (3 cases: refusal leaves every date and `is_active` untouched;
  `--allow-older` overrides; same-date re-import is not treated as older). Verified: replaying
  the original scratch-DB scenario now exits with
  `CommandError: … is dated 2026-08-07, older than the 2026-08-20 already loaded …`; 43 tests
  OK; mypy clean. **Mutation-checked** — disabling the guard makes
  `test_older_snapshot_is_refused_and_changes_nothing` fail.

### F3 — Manual criteria are checked without recorded evidence, and 2.6 claims a measurement the plan says cannot be made

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Success Criteria
- **Location**: `context/changes/registry-substance-data/plan.md:877-879`, `:894-896`, `:907-911`
- **Detail**: Two distinct problems, one root.

  **2.6 is contradicted by the plan's own body.** The criterion reads "Streaming-pass peak
  memory during the real parse stays in single-digit MB." Performance Considerations — rewritten
  in the *same commit* that checked the box (`ad4edf7`) — states that the streaming pass's own
  peak "cannot be isolated from the records accumulating alongside it without instrumenting the
  parser," and offers the 2.5 MB transient-headroom figure as "the closest honest substitute."
  The prose is scrupulous; the checkbox is not. It marks as done a measurement the same commit
  says was not taken.

  **2.5's number was never written down.** The criterion is "~20,187 human-use products, **≥95%
  resolved**." The plan records 20,245 human-use products, and `production-baseline.md` records
  25,884 links split 25,468 / 416 — but links are not products-with-links, so the resolution
  percentage the criterion turns on appears nowhere. It can be *inferred* to ~96.9% from
  options.md §8c's deferral count, and that inference is exactly the problem: an inferred number
  is not a measurement.

  Same shape, lower stakes, for 3.7 (live-URL elapsed time), 3.8 (three brands spot-checked),
  3.9 (temp file removed), 4.4/4.5 (asserted in `production-baseline.md` prose without the
  brand or the count), and 4.7. Phase 1's review made a point of the *absence* of
  rubber-stamping when its manual boxes were correctly left unchecked; the same standard applied
  here reads differently.

  Related, and worth one line rather than its own finding: 2.4's proof ("`git log --follow`
  shows a move") is real, but lives only in `ad4edf7`, which the squash-merge left unreachable.
  On `main` the fixture shows as a plain add, and the evidence disappears at the next `git gc`.
- **Fix A ⭐ Recommended**: Reword 2.6 to name the measurement that was actually taken
  ("transient headroom above the retained `ParseResult` stays in single-digit MB — 2.5 MB
  measured"), and record 2.5's resolution percentage next to the memory table.
  - Strength: Keeps every box honestly checked, and makes the plan describe what was really
    done — which is what the next reader (F-02) will trust.
  - Tradeoff: 2.5's percentage has to come from somewhere; a `--file` re-parse of the real
    export computes it in one line from `ParseResult`, which already carries
    `products_without_links`.
  - Confidence: HIGH — both gaps are documentary, and the plan already contains the honest
    version of 2.6's reasoning.
  - Blind spot: None significant.
- **Fix B**: Uncheck 2.5 and 2.6, re-run the real-file parse, and record both numbers before
  archiving.
  - Strength: Strictly correct — no criterion stays checked on inferred evidence.
  - Tradeoff: Requires re-fetching the 74 MB export for work that is already in production.
  - Confidence: HIGH.
  - Blind spot: The publisher rotates the file daily, so the numbers will not match the ones the
    original run saw.
- **Decision**: SKIPPED — the work is already in production and the underlying measurements were
  taken; what is missing is the write-up. Recorded here rather than in the plan, so anyone
  reading the plan's Progress section should treat 2.5 and 2.6 as attested-but-unrecorded and
  come to this finding for the caveat. **Carry-forward for F-02**: 2.6's checkbox overstates
  what was measured — the plan's Performance Considerations paragraph, not the checkbox, is the
  honest record (2.5 MB transient headroom, streaming-pass peak never isolated).

### F4 — The download boundary handles only `requests` errors

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: `registry/management/commands/import_registry.py:107-114`
- **Detail**: `destination.open('wb')` and `handle.write(chunk)` sit inside the `try`, but the
  `except` clause catches only `requests.RequestException`. A disk-full or permission failure
  mid-download therefore raises `OSError` as an unhandled traceback rather than a `CommandError`
  — the same shape as F1. Two lesser notes in the same block: nothing caps the bytes written, so
  a wrong URL returning a huge body fills the disk unbounded; and `response` is not closed on the
  error path (harmless, the process exits).

  Verified as *not* a problem: temp-file cleanup is correct on every path — the `finally` at
  `:92-97` owns it, and the `NamedTemporaryFile(delete=False)` + close-then-reopen-by-path
  pattern at `:82-86` is exactly right for Windows.

  `_download` has no test coverage at all: `test_file_option_never_touches_the_network` asserts
  only that `requests.get` is *not* called.
- **Fix**: Add `OSError` to the `except` clause at `:113`, and add two tests with a mocked
  `requests.get` — `RequestException` → `CommandError`, and temp file absent after a
  mid-transfer failure.
- **Decision**: FIXED — `except (requests.RequestException, OSError)`, with the docstring stating
  why the write side of the loop is a boundary too. Added `DownloadPathTests` (3 cases: network
  failure → `CommandError`; disk failure via a patched `Path.open` → `CommandError`; no
  `registry-*.xml` left in the temp dir after a failed download), closing the coverage gap on the
  one path `--file` deliberately never exercises. 46 tests OK; mypy clean.
  **Mutation-checked** — removing `OSError` from the except clause makes
  `test_disk_failure_becomes_a_command_error` fail.

### F5 — Two parser rules are implemented, commented, and unobservable by any test

- **Severity**: 💡 OBSERVATION
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Success Criteria
- **Location**: `registry/parser.py:188`, `:166-167`
- **Detail**: `source_order` is numbered with `enumerate(kept)`, i.e. **after** the denylist
  filter, so a dropped row closes the gap rather than leaving a hole. The rule is spelled out at
  `parser.py:78-81` as load-bearing ("so the common-name fallback's single link can share the
  same numbering"). But no fixture product mixes a denylisted row with kept rows — Cyclo 3 Fort,
  the only denylisted-row product, ends with zero links — so nothing can see it.

  **Confirmed by mutation**: rewriting the comprehension to `enumerate(rows)` with the denylist
  filter moved into an `if` clause — reintroducing exactly the hole the comment forbids — left
  **all 39 tests green**. Reverted immediately; tree is clean.

  Same for the blank-name skip at `:166-167`: no fixture product carries
  `nazwaSubstancji=""`, so that branch never executes.

  This does not undercut criterion 2.3, which named the denylist and `source_field` tagging
  specifically — both of those genuinely fail when inverted. It is a rule the implementation
  added beyond the plan and did not bring a test with.
- **Fix**: Add an inline-XML test in the style of `WholeFileVocabularyTests` (the strongest test
  in the suite) for a product whose rows are `[kept, denylisted, kept]`, asserting
  `source_order == [0, 1]`; and one with a blank substance name.
- **Decision**: FIXED — added `DroppedRowNumberingTests` to `test_parser.py`, following
  `WholeFileVocabularyTests`' inline-XML pattern so the fixture's documented contract is
  untouched. Two cases: a denylisted row between two kept rows (`source_order == [0, 1]`, not
  `[0, 2]`), and a blank `nazwaSubstancji` skipped. **Mutation-checked** — restoring
  `enumerate(rows)` produces `AssertionError: Lists differ: [0, 2] != [0, 1]`, so the rule that
  was invisible to all 39 original tests is now pinned. Full suite 81 tests OK; mypy clean.

### F6 — `ParseResult.substances` is narrower than the plan's wording, deliberately and correctly

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Adherence
- **Location**: `registry/parser.py:206-210`
- **Detail**: The plan specifies `ParseResult.substances` as the whole-file vocabulary. The
  implementation filters it to names an emitted link actually references. **This resolves a
  contradiction in the plan rather than departing from it**: the loader inserts a `Substance` row
  for every key on `substances`, insert-only forever, so the literal reading would make
  `Produkt złożony` a permanent `Substance` row with zero links — defeating `denylist.py`,
  whose entire purpose is keeping those placeholders out of the data.

  The properties the plan cares about all survive: the whole-file vocabulary (veterinary
  included) still drives the E1 fallback, first-seen order is preserved by iterating
  `vocabulary.items()`, and fallback-only names still land in the tuple because
  `_resolve_deferred` updates `referenced_keys` before the filter is built. Both behaviours are
  pinned by tests (`test_parser.py:174`, `:193-196`). The drift was disclosed in `ad4edf7`'s
  commit body and is documented at `parser.py:24-34`.
- **Fix**: Correct the plan's Phase 2 § 2 wording so it describes what the code does and why —
  otherwise the next reader treats the plan as ground truth and "fixes" the code back.
- **Decision**: FIXED + ACCEPTED-AS-RULE — "A plan can contradict itself; resolve it in code
  *and* write the resolution back", appended to `context/foundation/lessons.md`. The plan's
  Phase 2 § 2 now carries a "Corrected during Phase 2 (impl-review F6)" paragraph stating the
  implemented contract (`substances` carries only referenced names) and confirming that the
  whole-file fallback vocabulary and the whole-file first-seen tiebreak both stay as designed.
  No code change — the implementation was already right.

### F7 — Three comments state things that are no longer (or never were) true

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency
- **Location**: `registry/models.py:95-96`, `registry/loader.py:38-40`, `.env.example:44-47`
- **Detail**:
  1. `models.py:95-96` describes `source_order` as "0-based position of the source element
     within its product" — stale since `parser.py:188` renumbers contiguously over kept rows
     (F5). A dropped row means the stored number is *not* the source position.
  2. `loader.py:38-40` justifies `BATCH_SIZE = 1000` against "the widest row here
     (ProductSubstance, 10 columns → 10,000 parameters)". `ProductSubstance` binds **9**
     columns; the widest row is the `Product` upsert at **12** (`registry_id` + 11 update
     fields) → 12,000 per batch. The conclusion is unaffected (12,000 ≪ 32,766, ≪ Postgres's
     65,535) but the arithmetic names the wrong model.
  3. `.env.example:44-47` says the parser "derives it from whichever URL is in play" without
     naming `namespace_for_url()`, which the plan asked for explicitly. `settings.py:77` does
     name it, so this is cosmetic.
- **Fix**: Three one-line comment edits.
- **Decision**: FIXED — all three corrected. `models.py`'s `source_order` comment now says
  "position among this product's *emitted* links … not the source element's index" and states
  why; `loader.py`'s `BATCH_SIZE` comment now names the `Product` upsert at 12 columns as the
  widest row; `.env.example` now names `registry.parser.namespace_for_url()`. Comment-only, so
  `makemigrations --check` still reports no changes. 81 tests OK; mypy clean.

### F8 — The parser computes the guard's stated input and the loader's cross-check, and nothing consumes either

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Architecture
- **Location**: `registry/parser.py:109-114`, `registry/management/commands/import_registry.py:126`
- **Detail**: `ParseResult.products_in_file` is documented as "the honest input to a plausibility
  guard", but the guard reads `stats.products_loaded` (human-use only). `products_in_file`,
  `substance_row_links`, `common_name_links` and `products_without_links` are referenced only in
  `parser.py` and `test_parser.py`; `LoadStats` carries none of them and `_rebuild_links`
  recomputes its own `links_by_source_field` independently.

  Two consequences. A docstring claims a role the code does not implement. And the parser
  produces exactly the numbers that would cross-check the loader's write — if the loader silently
  dropped a link, nothing would notice. A third, smaller: a complete file whose
  `rodzajPreparatu` vocabulary changed would abort with "looks like a truncated snapshot", the
  wrong diagnosis.
- **Fix**: Carry `products_in_file` through to `LoadStats` and report it, or drop the
  docstring's claim. `products_without_links` is also what criterion 2.5 (F3) needs.
- **Decision**: FIXED — `LoadStats` now carries `products_in_file` and `products_without_links`,
  and the summary prints `products in file: N (all kinds)` plus
  `resolved: N of M (x.x%)`. The guard's refusal names the full-file count and says outright
  that a low human-use count against a full file means the filter stopped matching, not a
  truncated download. The parser docstring's "honest input to a plausibility guard" claim is
  replaced with what the field is actually used for.

  **This partly closes F3 going forward**: criterion 2.5's resolution share now falls out of any
  ordinary run instead of having to be reconstructed. Two tests added
  (`SummaryOutputTests.test_summary_reports_the_resolution_share`,
  `test_refusal_names_the_full_file_count_so_the_cause_is_diagnosable`). Worth recording: the
  first test initially asserted `11 of 12` on my assumption and **failed** — the real figure is
  `10 of 12 (83.3%)`, which `fixtures/README.md` independently documents as "2 products with no
  links". The code was right and the assertion was wrong. 83 tests OK; mypy, `check` and
  `makemigrations --check` all clean.

### F9 — `bulk_create` bypasses field validation, so two constraints are SQLite-tolerant and Postgres-fatal

- **Severity**: 💡 OBSERVATION
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality
- **Location**: `registry/loader.py:130-157`
- **Detail**: `bulk_create` does not call `full_clean()`, so nothing enforces `max_length`.
  SQLite ignores VARCHAR length; Postgres raises `DataError: value too long for type character
  varying(255)`. `Product.name` / `marketing_holder` / `pharmaceutical_form` / `Substance.name`
  are 255, `permit_number` 64, the URLs 500. Today's snapshot fits — the 20,245-product
  production run proves it — but a longer value in a future export aborts the whole import.

  Second instance: if the export ever emits two `produktLeczniczy` sharing an `id` within one
  1000-row batch, Postgres rejects `INSERT … ON CONFLICT DO UPDATE` with "cannot affect row a
  second time"; SQLite tolerates it. The parser does not deduplicate on `registry_id`.

  Both fail loudly and roll back completely — no half-applied state — which is why this is an
  observation. It is worth recording because it is precisely the shape `lessons.md` rule 2 is
  about: a green local SQLite run is not evidence the Postgres import will succeed, and this
  plan otherwise went to real lengths to avoid depending on engine equivalence.
- **Fix**: Accept and record. Do **not** truncate over-long values to fit — a shortened
  substance name is an identity the source does not state, which is the NFR line the denylist
  and `source_field` design exist to protect and which the plan bans outright ("No lemmatization
  or substance-name inference"). If a real overflow ever appears, widen the column in a
  migration and re-import; the failure is loud, atomic, and the snapshot is re-runnable.
- **Decision**: ACCEPTED AS RISK — no code change. The justification: both failures are loud and
  roll back completely, so the worst case is a failed import rather than wrong data, and the
  snapshot is re-runnable the moment the column is widened. Truncating to fit was explicitly
  rejected as the wrong trade — it would put an identity the source never stated into the
  database, which is the line the whole provenance design exists to hold. **Carry-forward for
  F-02**: when the scheduled refresh starts running unattended, a `DataError` on a widened field
  is one of the failure modes its alerting has to surface, because nothing in local SQLite CI
  will ever reproduce it.

### F10 — Phase 4's branches dropped the AGENTS.md type prefix

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency
- **Location**: PRs #16, #17, #18
- **Detail**: `AGENTS.md` states branches spell the type out — `feature/`, `fix/`, `chore/`,
  `refactor/`, `docs/` — followed by the change-id. Phase 1–3's branch complied
  (`feature/registry-substance-data`). Phase 4's three did not:
  `registry-substance-data-prod-import`, `registry-substance-data-prod-import-revert`,
  `registry-substance-data-close-out`. The commit *subjects* all used `chore(...)` correctly, so
  this is the branch half of the convention only, and the branches are already merged and gone.
- **Fix**: Nothing to fix retroactively — note it so the next change's branches carry
  `chore/`.
- **Decision**: SKIPPED — the branches are merged and deleted; there is nothing to rename. Noted
  for the next change. This review's own fixes are on `fix/registry-substance-data-review-fixes`,
  which follows the convention.

## Post-triage verification

Re-run after F1, F2, F4, F5, F7 and F8 were applied, on
`fix/registry-substance-data-review-fixes`:

| Check | Result |
| --- | --- |
| `manage.py test` | PASS — 83 tests OK (was 72; +11 from this triage) |
| `mypy` | PASS — no issues, 35 source files |
| `manage.py check` | PASS — no issues |
| `makemigrations --check --dry-run` | PASS — "No changes detected" (the `models.py` edit was comment-only) |
| `uv sync --locked` | PASS — 26 packages, no drift |
| Truncated-file scenario (F1) | Now `CommandError: … is not well-formed XML: unclosed token` instead of a traceback |
| Older-snapshot scenario (F2) | Now `CommandError: … is dated 2026-08-07, older than the 2026-08-20 already loaded …`; replayed against the same scratch DB that originally reproduced the corruption |

Every fix that added a test was **mutation-checked** — the fix reverted, the new test observed to
fail, the fix restored. That covers F1, F2, F4 and F5. Applying that discipline is what caught
the one place my own assertion was wrong rather than the code (F8's `10 of 12`, not `11 of 12`).

## Checked and held — suspicions that did not survive

Recorded so they are not rediscovered as findings later. Each was traced to code, and several
were verified by running something rather than reading.

- **Plausibility guard inside the transaction** — yes. `_import`'s `atomic()` at `:122` wraps
  `load_parse_result`, whose own `atomic()` becomes a savepoint; the `CommandError` propagates
  out of the outer block and rolls back all three tables, substances included.
- **SQL parameter ceiling on the link delete** — the docstring's "one bound parameter" claim
  holds. Captured SQL: `DELETE FROM registry_productsubstance WHERE id IN (SELECT … INNER JOIN
  registry_product … WHERE last_seen_as_of = ?)` — one statement, one parameter, no `id__in`
  list, and the same shape on Postgres.
- **`KeyError` on `substance_ids[link.name_key]`** — cannot occur. `_resolve_deferred` runs at
  `parser.py:201` *before* `substances` is built at `:206`, so every fallback key is in
  `referenced_keys` before the filter. The ordering is load-bearing and correct.
- **`NamedTemporaryFile` on Windows** — correct as written; `delete=False` plus close-then-reopen
  by path is the right pattern, and the `finally` covers every failure path.
- **N+1 queries** — none. The admin inline carries `select_related('substance')` (the Phase 1
  review's F5 fix), and the loader builds both id maps with two `values_list` queries.
- **`batch_size`** — present on all three `bulk_create` calls.
- **Injection / authz / secrets** — no untrusted input reaches the URL or file path;
  `REGISTRY_OVERALL_URL` is public government data with an `os.environ` read, an in-code
  default, and a documented `.env.example` entry, exactly as `AGENTS.md` requires.
- **XML entity expansion** — `iterparse` does expand *internal* entities on CPython 3.11, so a
  hostile `--file` could exhaust memory. External entities and DTD retrieval are safe, so there
  is no XXE file-read or SSRF. The plan's "no `defusedxml`" decision stands on its threat model
  (trusted government HTTPS endpoint, operator-supplied local files); noting only that the
  plan's stated rationale covers external entities and not internal ones.
- **Pattern compliance** — no substantive mismatches. Every function, method and test method
  carries annotations including `-> None`, matching `households`; module structure, error
  handling, settings convention and `pyproject.toml` scoping all follow the established shape.
- **Concurrency** — two simultaneous imports could both read `existing_keys` before either
  inserts, producing an `IntegrityError` on `Substance.name_key`. Correct outcome (one rolls
  back), single-operator today. Recorded for whoever adds F-02's scheduler.
