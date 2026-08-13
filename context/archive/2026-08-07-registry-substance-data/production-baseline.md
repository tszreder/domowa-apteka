# Production import baseline

First and only real load, run via a temporary `railway.json` `startCommand`
addition (PR#16, reverted in a follow-up PR). Recorded here so F-02 has a
production number to compare freshness against — see plan.md Phase 4,
"Record the command's summary output".

## Run 1 (initial load)

- Snapshot `stanNaDzien`: 2026-08-13
- Source URL: `https://rejestry.ezdrowie.gov.pl/api/rpl/medicinal-products/public-pl-report/6.0.0/overall.xml`
- Products loaded: 20,245 (20,245 new)
- Products marked inactive: 0
- Substances created: 3,391 new
- Links created: 25,884
  - `substance_row`: 25,468
  - `common_name`: 416
- Elapsed: 6.0 s

## Run 2 (idempotency check, `railway redeploy`)

- Same snapshot (`stanNaDzien` 2026-08-13, publisher had not rotated the file)
- Products loaded: 20,245 (**0 new**)
- Products marked inactive: 0
- Substances created: **0 new**
- Links created: 25,884 (same distribution: 25,468 / 416)
- Elapsed: 5.9 s

Row counts and their `substance_row` / `common_name` split are identical
across both runs — the upsert is idempotent on production Postgres, not just
on SQLite in the test suite (plan.md item 4.6).

## Notes

- Both runs landed within the measured local range (~20,187 products,
  ≥95% resolved via `substance_row`/`common_name`). Local elapsed time was
  ~13 s end to end (download + parse + DB); production came in faster at
  ~6 s for the import step alone (excludes the migrate/collectstatic steps
  already in `startCommand`).
- Manually verified in `/admin/registry/product/` on production: rows
  present, and a spot-checked brand's substances matched the local fixture
  expectations.
- Elapsed time above is `import_registry`'s own reported figure (download +
  parse + DB write), not the container's total startup time.
