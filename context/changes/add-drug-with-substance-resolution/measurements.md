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
- `concor cor 2,5` — collapses to **one** presentation with **8** producers, one per
  distinct holder (Allpharm, Delfarma, Forfarm, InPharm, Medezin, Merck, PharmaVitae,
  Pretium Farm).

  > **Corrected 2026-08-16 (review finding F7).** This line originally read "**28**
  > producer rows across several distinct holders" and recorded that as a success. It was
  > the symptom of a defect: 28 rows were being offered where only 8 are distinguishable,
  > so typing `del` returned four entries all reading `Delfarma` with nothing to choose
  > between them. Manual criterion 3.6 was ticked because the field *does* narrow — just
  > to duplicates. Fixed by emitting one producer per distinct holder.

## Phase 2 (revised 2026-08-16): after review findings F1 and F7

Re-measured against the same real 20,247-active-product local database after replacing the
per-group hydration loop with a single OR'd query, and after deduplicating producers by
holder.

| Metric | Before | After |
| --- | --- | --- |
| Queries per search (10 results) | 31 (1 + 3N) | **4** |
| Queries per HTTP request (incl. 3 auth) | 34 | **7** |
| Slowest sampled search (`in`, 10 results) | 20.0 ms | **15.6 ms** |
| Producers offered for `Concor Cor 2,5` | 28 | **8** |
| Largest sampled JSON payload | — | **2,685 bytes** |

The query count is now independent of the number of matched groups, which is the property
under test — `test_query_count_does_not_grow_with_the_number_of_groups` asserts one group
and ten cost the same, and `test_query_count_is_bounded` pins the absolute 7.

Both guards were mutation-checked rather than trusted green: reverting to the per-group
loop makes them fail with `34 != 7`, and reverting the holder dedup makes both new
`registry.tests.test_suggestions` cases fail. Largest producer count across the sampled
queries was 4, inside the plan's "no group has more than 10" sizing assumption; payload
stayed near the plan's ~2 KB estimate.

Caveat unchanged from the original review: these are SQLite in-process on dev. The claim
that 4 round trips beat 31 in production Postgres is inference from network latency, not a
measurement against Postgres.

## Phase 4: North-star resolution, tried live against the real database

Added through the real UI (autocomplete → pick → save) as a logged-in household member,
against the real 20,245-product local database:

| Typed | Picked | Resolved substance(s) |
| --- | --- | --- |
| `apap` | APAP — 500 mg — Tabletki | Paracetamolum |
| `gripex` | Gripex — 325 mg + 30 mg + 10 mg — Tabletki powlekane | Paracetamolum, Pseudoephedrini hydrochloridum, Dextromethorphani hydrobromidum |
| `ibuprom` | Ibuprom — 200 mg — Tabletki powlekane | Ibuprofenum |
| `grip` | Gripblocker — 500 mg — Tabletki | Acidum acetylsalicylicum |
| `concor cor 2,5` | Concor Cor 2,5 — 2,5 mg — Tabletki powlekane (Forfarm Sp. z o.o.) | Bisoprololi fumaras |
| `moviprep` | Moviprep — Proszek do sporządzania roztworu doustnego | *(none — unresolved, warned and displayed distinctly)* |

Each substance set is one a household member would recognise from the box (`Paracetamolum`
= paracetamol, `Ibuprofenum` = ibuprofen, `Bisoprololi fumaras` = bisoprolol), and Gripex's
multi-substance result matches the "more than one substance" expectation for a combination
cold remedy — confirming the north star.

Also confirmed live: a second member of the same household (`manual-a2@example.com`) saw
all of the above items on first page load, no refresh or re-login; a member of a different
household (`manual-b@example.com`) saw none of them and got a 404 on a direct delete POST
against a known item id; deleting an item removed it from the list immediately with a
confirmation message.

**Not independently confirmed in this environment:** the phone-width layout check (3.11 /
4.12) — the browser automation's `resize_window` reported success but
`window.innerWidth` never changed from the desktop size, so no real narrow-viewport
screenshot was taken. Flagged for the user to eyeball directly.

**Confirmed 2026-08-16 by the user**, directly at ~375px in devtools against the running
dev server (review finding F6): the add flow, suggestion list, and producer picker are
usable at phone width (3.11), and the full search → pick presentation → pick producer →
save → list → delete flow works end to end at that width (4.12). Both plan.md criteria
ticked.
