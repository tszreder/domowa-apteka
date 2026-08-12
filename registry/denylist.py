"""Category words the registry states where a substance name belongs.

The registry sometimes fills `nazwaSubstancji` with a *category* rather than an
identity. Measured against the live export on 2026-08-07 (options.md §8a):
`Produkt złożony` on 28 explicit substance rows, `Preparat złożony` on 3, and
`Wyciągi alergenowe` on 4. Loaded as ordinary substances they are far worse than
a gap: every product carrying `Produkt złożony` becomes a full-substance-set
duplicate of every other one, so S-03 would confidently flag 78 unrelated
medicines as identical. That is wrong output, not a visible failure.

**The vocabulary test alone cannot catch this.** `Produkt złożony` really is used
as a `nazwaSubstancji`, so it passes the E1 fallback's "is this string in the
registry's own substance vocabulary?" check. This denylist is the only thing
standing between those 60 fallback matches and the data.

**Bare category words are denied; specific descriptive names are kept** — the
latter *are* identities (options.md §8c's audit):

| Denied (generic category) | Kept (specific identity)                     |
| ------------------------- | -------------------------------------------- |
| `wyciągi alergenowe`      | `wyciągi alergenowe roztoczy kurzu domowego` |
| `produkt złożony`         | `wyciąg alergenów z pyłków traw (5 gatunków)` |
| `preparat złożony`        | `wodny wyciąg borowinowy`                     |

So membership is **exact match on the casefolded key only** — no prefix match, no
substring match, no classifier. This is the one place in F-01 where a
hand-maintained list is justified, and it is recorded as a judgement call:
options.md §8c measures its price at 0.45 pp of coverage, paid to remove a class
of confidently-wrong duplicate flags.
"""

DENYLISTED_SUBSTANCE_KEYS: frozenset[str] = frozenset(
    {
        'produkt złożony',
        'preparat złożony',
        'wyciągi alergenowe',
    }
)
