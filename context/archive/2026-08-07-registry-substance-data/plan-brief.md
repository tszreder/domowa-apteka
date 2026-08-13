# Registry-backed product and active-substance data — Plan Brief

> Full plan: `context/changes/registry-substance-data/plan.md`
> Research: `context/changes/registry-substance-data/options.md`
> Library docs: `context/changes/registry-substance-data/library-docs.md`

## What & Why

Roadmap item **F-01**. A local, queryable copy of product → active-substance records from the
Polish national medicinal-products registry, loaded by one repeatable command, with every
substance value traceable back to the source row it came from. Nothing downstream works
without it: S-02 (the north star — type a drug name, see its substances) has nothing to
resolve against, and S-03's duplicate flagging has nothing to compare.

## Starting Point

One app exists (`households`), plus a live Railway deploy with Postgres. No registry code, no
management commands anywhere in the repo. The research phase already measured the source
against the live registry: bulk XML is the only public interface (the JSON API 403s, the
incremental feed was retired by the publisher on purpose), the file is 73.7 MB, and a
streaming parse costs 9.9 s. (The research's 7 MB peak-memory figure measured a pass that
discarded each record; this design retains them, so Phase 2 measures the real number.)
The substance fields turned out **clean** —
zero whitespace defects, 5 case collisions across 4,267 names — which closes the open
"maybe an LLM for normalization" question in `tech-stack.md`. `has_ai: false` stays false.

## Desired End State

`manage.py import_registry` populates three tables with the ~20,187 human-use products and
their substance links. Running it twice leaves an identical database. Every link records
whether it came from an explicit `<substancjaCzynna>` element or from the product's common
name via a vocabulary-grounded fallback. A read-only Django admin lets a human search the
loaded data without being able to change it.

## Key Decisions Made

| Decision | Choice | Why (1 sentence) | Source |
| --- | --- | --- | --- |
| Ingestion mode | Full-snapshot replace | The publisher retired the incremental feed and the `status` attribute is absent on all 22,823 products — there is no delta signal to consume. | Research |
| XML parsing | stdlib `iterparse` + `elem.clear()` | Measured 9.9 s with zero new dependencies; `lxml` buys ~2× on a step that is already fast enough. `elem.clear()` is what keeps the streaming pass off the ~1 GB whole-DOM path. | Research |
| Substance-less products | E1 fallback + placeholder denylist | Lifts coverage 95.15% → 97.23%, and the +2.08 pp is 419 recognisable brands (Smecta, Differin, Nootropil); the denylist costs 0.45 pp to remove a class of confidently-wrong duplicate flags. | Plan |
| Provenance | `source_field` on every link | The product→substance link in the fallback is *our* inference, not the registry's — marking it per row is what keeps the NFR honest and lets S-02 show the user where a resolution came from. | Research |
| Registry subset | Human-use only | Veterinary products (11.5%) are noise in a household medicine cabinet; `rodzajPreparatu` is source-stated, so filtering on it is selection, not inference. | Plan |
| Withdrawn products | Keep and mark inactive | S-02 will put user items behind FKs to `Product`; deleting on a routine refresh would cascade into user data. | Plan |
| Freshness record | Per-product `last_seen_as_of` only | One column, not two: a second `source_as_of` would carry the same date on every row on every run. Keeps F-01 to a one-shot load; F-02 owns the run record and the scheduler. | Plan |
| HTTP client | Add `requests` | Better timeout/retry ergonomics, and F-02's scheduled refresh will want it anyway. | Plan |
| Product fields | Core + leaflet/SmPC URLs | Covers S-02's `Xanax`-×48 disambiguation (strength + form) at zero new tables; ATC and packages deferred, since ATC cannot decompose a combination product into a substance set. | Plan |
| Denylist location | Module constant in the app | A correctness-critical judgement call belongs in git where a PR diff shows it changing and CI pins its behaviour. | Plan |
| Admin | Read-only with search | The cheapest sanity check on a 20k-row import; an edit could not survive the next import and would break source-traceability until then. | Plan |
| Test scope | Full parser + loader suite, offline | The two rules that decide whether S-03 is correct are invisible to a count assertion — and the fixture cannot currently exercise either. | Plan |
| Production load | Temporary `startCommand`, then revert | `railway run` cannot reach the internal Postgres host, and `railway ssh` was never confirmed to reach this container; the add → deploy → confirm → **revert** shape is the one this project has already executed end to end. | Plan |

## Scope

**In scope:** a `registry` Django app; `Product` / `Substance` / `ProductSubstance` models and
migration; a pure offline parser owning the human-use filter, denylist, and fallback; an
idempotent `import_registry` command with fetch-or-`--file`; read-only admin; a full offline
test suite; one production load.

**Out of scope:** scheduling and refresh automation (F-02); autocomplete, views, URLs (S-02);
duplicate detection (S-03); ATC codes and packages/GTIN; any delta pipeline; lemmatization or
any inference of a substance identity the source does not state; splitting multi-substance
name strings; parsing the free-text `moc` field.

## Architecture / Approach

Three layers, separated so the correctness-critical logic is fully offline and fully testable:

```
overall.xml ──(requests, stream to temp file)──► parser.py ──► loader.py ──► 3 tables
   or --file                                     [pure]        [dumb]
                                          human-use filter
                                          denylist
                                          E1 fallback + source_field tagging
```

The parser owns every rule that touches the NFR's "never infer an identity the source does not
state" line, and has no database or network. The loader makes no decisions about what a
substance *is* — only where rows go. The write is a snapshot upsert keyed on the registry's own
product `id`, in one transaction, with absent products marked inactive rather than deleted.

## Phases at a Glance

| Phase | What it delivers | Key risk |
| --- | --- | --- |
| 1. Scaffold + models + admin | `registry` app, three models, migration, read-only admin, mypy scope | A `unique_together` on `(product, substance)` looks right and fails only against real data — 89 source rows legitimately repeat |
| 2. Parser | Pure file → records, with denylist and fallback; extended fixture; parser tests | The E1 fallback forward-references, so it cannot be decided while streaming; and the fixture as shipped cannot exercise the denylist at all |
| 3. Loader + command | `import_registry`, idempotent upsert, withdrawn marking, plausibility guard; loader tests | A truncated download looks like a successful load of 300 products without the plausibility guard |
| 4. Production load | Data in production Postgres, verified | Manual and user-driven — the temporary `startCommand` must be reverted, or every container restart re-imports 74 MB |

**Prerequisites:** none — F-01 has no roadmap prerequisites. Phase 4 needs the ability to merge
a PR and read Railway deploy logs; no shell and no TTY.
**Estimated effort:** ~3–4 sessions. Phase 2 is the largest (the test suite is likely bigger
than the production code); Phase 4 is ~15 minutes of mostly waiting.

## Open Risks & Assumptions

- **Version lifecycle.** `6.0.0` is in the URL and 5.0.0 was retired on a published schedule.
  Mitigated by the env var (a variable change, not a deploy) plus a hard namespace assertion
  whose expected value is **derived from the configured URL** by `namespace_for_url()`, so the
  two cannot drift apart. This buys the *chance* to switch versions without a deploy, not a
  guarantee — a 7.0.0 export could still rename elements below the root.
- **Assumption: the registry URL is configuration, not a credential.** It ships as an in-code
  default so CI's `manage.py check` passes with no `.env`, with the env var as the override.
  This is a deliberate reading of `AGENTS.md`'s no-hardcoded-settings rule, stated rather than
  assumed.
- **`bulk_create` PK behaviour on Postgres is unverified** — the research measured it on
  SQLite and inferred parity. The plan removes the dependency entirely (explicit id map,
  0.02 s) rather than designing around an unverified claim, per `lessons.md`.
- **The fallback's vocabulary scope was never stated by the research.** options.md defines the
  test as "in the registry's own substance vocabulary" without saying whether that means the
  whole registry or the human-use subset. The plan takes the whole-registry reading and says
  so; the 97.23% headline coverage figure may have assumed either, so the phase-2 check is a
  range rather than an exact match.
- **Leaflet URLs are stored unverified.** They point at the same `/api/rpl/` host that returns
  403 on its other endpoints; whether `/leaflet` is separately public was never probed.
  Storing them is safe, relying on them is not.
- **The denylist is a hand-maintained judgement call.** Kept short and literal by design, with
  the kept-vs-denied audit documented next to it. It will not catch a placeholder value nobody
  has seen yet.
- **Scope creep is the roadmap's own named hazard for F-01.** The "What We're NOT Doing" list
  in the plan is unusually long on purpose.

## Success Criteria (Summary)

- One command loads the registry into local tables, and running it twice changes nothing.
- Any substance shown for a product can be traced to the source row it came from, and rows
  resolved by inference are marked as such rather than presented as stated fact.
- The data is live in production Postgres, so S-02 has something real to resolve against.
