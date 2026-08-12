# `sample-products.xml` — what each product is here to prove

A 14-product excerpt of the real `overall.xml` export, `stanNaDzien="2026-08-07"`.
Every block is **verbatim from the live registry** — spliced in as raw text, never
re-serialized — so the file keeps the source's own attribute spelling and quoting.
`registry/tests/test_parser.py` asserts against the expectations below; the two
files move together.

Products 1–8 came from the original research excerpt (`options.md` §10).
Products 9–14 were added when it became a test fixture, because the original
eight could not exercise the denylist or the *positive* common-name fallback at
all — it proved only the negative path.

| # | Product | `id` | Kind | Links | Proves |
| - | ------- | ---- | ---- | ----- | ------ |
| 1 | Nalgesin | 100000037 | ludzki | 1 · `substance_row` | amount `275` + unit `mg` kept verbatim |
| 2 | Altacet | 100004259 | ludzki | 2 · `substance_row` | same substance twice at `1000` / `100` mg — `(product, substance)` is **not** unique |
| 3 | Peditrace | 100078163 | ludzki | 7 · `substance_row` | repeated `Zinci chloridum`; amounts only in `innyOpisIlosci` (`521,00 mcg`), decimal comma intact |
| 4 | Vaminolact | 100002591 | ludzki | 19 · `substance_row` | a wide product loses no rows |
| 5 | Parvoerysin | 100005709 | **weterynaryjny** | — | excluded from the result; its 5 substance names still widen the vocabulary |
| 6 | Beto 200 ZK | 100005193 | ludzki | 1 · `common_name` | E1 fallback **fires**, validated by product 9 further down the file; parallel-import `ulotkaImportRownolegly` read |
| 7 | ZmienićDIVENCE | 100495800 | **weterynaryjny** | — | excluded; editorial artifact in the name loaded verbatim if it ever isn't |
| 8 | Xanax | 100071994 | ludzki | 1 · `substance_row` | one of the 48 rows sharing this name in the real export |
| 9 | Beto 25 ZK | 100432015 | ludzki | 1 · `substance_row` | supplies `Metoprololi succinas` to the vocabulary **after** product 6 needs it — the forward reference |
| 10 | Cyclo 3 Fort | 100413510 | ludzki | 0 | denylist blocks an explicit `nazwaSubstancji="Produkt złożony"` row, then blocks the fallback too |
| 11 | Moviprep | 100449211 | ludzki | 0 | no substance rows at all; denylist blocks the `Produkt złożony` fallback |
| 12 | Staloral 300 | 100123277 | ludzki | 1 · `substance_row` | near-miss survives: `Wyciągi alergenowe roztoczy kurzu domowego` is kept though bare `wyciągi alergenowe` is denied |
| 13 | Addamel N | 100002792 | ludzki | 9 · `substance_row` | states `Sodu fluorek` — the first-seen spelling |
| 14 | Addamel N | 100362527 | ludzki | 9 · `substance_row` | states `sodu fluorek` — same `name_key`, and first-seen-wins keeps product 13's spelling |

Totals: **14 products in the file, 12 human-use**, 50 `substance_row` links,
1 `common_name` link, 2 products with no links, 37 distinct substances.

## Document order is part of the contract

Two orderings are load-bearing and must survive any future edit:

- **Beto 25 ZK (9) after Beto 200 ZK (6).** If the validating substance row moved
  ahead of the product that needs it, a forward-only fallback would pass and the
  deferred-resolution design would stop being under test.
- **`Sodu fluorek` (13) before `sodu fluorek` (14).** The first-seen-wins tiebreak
  has nothing to prove if the spellings swap.

Append new products at the end unless a rule needs them somewhere specific, and
keep `stanNaDzien` pinned at `2026-08-07` — a test asserts that exact date.
