# Measurements taken during implementation

## Phase 2: `search_presentations` against the real 20,245-row local database

**Naive fetch-then-group (initial implementation) broke outright**, not just slow: a
worst-case 2-character query (`in`, matching 4,246 active products) raised
`sqlite3.OperationalError: Expression tree is too large (maximum depth 1000)` from
`prefetch_related`'s `IN (...)` clause over thousands of ids. This is the risk the plan's
"Performance Considerations" flagged as unmeasured, confirmed real. Fixed by switching to
the plan's second implementation shape — group in SQL (`.values_list(...).distinct()`,
sliced to `limit` there), then hydrate only the rows in the ≤10 chosen groups.

After the fix, timed via `manage.py shell` (5 runs each, warm):

| Query | Raw matches | Presentations | min/mean/max ms |
| --- | --- | --- | --- |
| `in` (worst case found) | 4,246 | 10 | 20.0 / 20.3 / 20.6 |
| `grip` | — | 10 | 12.6 / 12.6 / 12.8 |
| `apap` | — | 10 | 12.2 / 12.3 / 12.4 |
| `xanax` | — | 10 | 14.4 / 14.4 / 14.4 |
| `concor` | — | 10 | 16.2 / 16.7 / 17.2 |

Confirmed again end-to-end through the JSON endpoint in a logged-in browser session
(network + view + JSON parse): `concor cor 2,5` — 13 ms; `in` — 32 ms, 200 OK, 10 results
(previously a 500).

Well inside the PRD's one-second NFR even at the worst case found in a scan of common
2-character substrings (`in`, `ro`, `or`, `ta`, `en`, `ar`, `ra`/`an` all >2,600 raw
matches).

### Spot-checked query correctness

- `grip` — 10 sensible presentations (Aspirin Antigrip Hot, Choligrip, Coldrex variants,
  Gripblocker variants), each with its real substances.
- `apap` — 10 sensible presentations, all `Paracetamolum`-based except `APAP intense`
  (`Ibuprofenum` + `Paracetamolum`).
- `xanax` — distinct strengths as separate presentations (0,25 mg / 0,5 mg / 1 mg / 2 mg /
  250 mcg / 500 mcg / SR variants), not 59 near-identical rows.
- `concor cor 2,5` — collapses to **one** presentation with **28** producer rows across
  several distinct holders (Allpharm, Delfarma, Forfarm, InPharm, ...).
