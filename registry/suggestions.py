"""Presentation grouping and the default-product tiebreak.

Pure queries over `registry`'s own models — no HTTP attached, so the rules
that decide whether this slice is correct are testable in isolation. See
the plan's "Critical Implementation Details" and "Key Discoveries" for why
these two rules (grouping, tiebreak) exist and what they must hold against.
"""

import re
from collections import defaultdict
from dataclasses import dataclass
from functools import reduce
from operator import or_

from django.db.models import Q

from .models import Product


@dataclass(frozen=True)
class Producer:
    holder: str
    product_id: int


@dataclass(frozen=True)
class Presentation:
    name: str
    strength: str
    pharmaceutical_form: str
    substances: list[str]
    default_product_id: int
    producers: list[Producer]


def _default_product(rows: list[Product]) -> Product:
    """Prefer a row with at least one substance link; tiebreak on `registry_id`.

    `registry_id` is compared as the registry's own stable string key
    (lexicographic, since it's a CharField), not as a database pk — F-01's
    loader may recreate rows, so pks are not reproducible across re-imports.
    Must not be mixed with a database-side `order_by('registry_id')`, which
    would apply the same ordering but is a different code path that could
    silently disagree with this one on a case the tests don't cover.
    """
    with_substances = [product for product in rows if product.substance_links.all()]
    candidates = with_substances if with_substances else rows
    return min(candidates, key=lambda product: product.registry_id)


def _build_presentation(rows: list[Product]) -> Presentation:
    default_product = _default_product(rows)
    substances = [link.substance.name for link in default_product.substance_links.all()]
    # One producer per *distinct holder*, not per row. `Concor Cor 2,5` is 28
    # rows across 8 holders; emitting a row each would offer 28 options the
    # user cannot tell apart — the exact flaw presentation grouping exists to
    # remove, reintroduced one level down. Worse than cosmetic: identical-
    # looking options carry different `product_id`s, and in the 1.24% of
    # groups whose rows disagree on substances they resolve to different
    # substance sets. The representative row is chosen with `_default_product`
    # so there is one tiebreak rule in this module, not two.
    rows_by_holder: dict[str, list[Product]] = defaultdict(list)
    for row in rows:
        rows_by_holder[row.marketing_holder].append(row)
    producers = sorted(
        (
            Producer(holder=holder, product_id=_default_product(holder_rows).id)
            for holder, holder_rows in rows_by_holder.items()
        ),
        key=lambda producer: producer.holder,
    )
    first = rows[0]
    return Presentation(
        name=first.name,
        strength=first.strength,
        pharmaceutical_form=first.pharmaceutical_form,
        substances=substances,
        default_product_id=default_product.id,
        producers=producers,
    )


def search_presentations(query: str, limit: int = 10) -> list[Presentation]:
    """Group active products matching `query` into pickable presentations.

    `icontains`, not `istartswith`: no measurable cost difference at this
    scale, and it matches `cor` against `Concor Cor`.

    Groups in SQL before hydrating, rather than fetching every matching row
    and grouping in Python: a naive fetch-then-group tried against the real
    20k-row database and broke outright on common short queries (`in` alone
    matches 4,246 active products) — SQLite's `prefetch_related` IN-clause
    hit `sqlite3.OperationalError: Expression tree is too large`, not just
    slow. Grouping in SQL first and slicing to `limit` there means only the
    handful of rows in the ≤`limit` chosen groups are ever hydrated. See
    the plan's "Performance Considerations".

    The chosen groups are then hydrated in a *single* OR'd query rather than
    one query per group: a per-group loop costs 1+3N statements (31 at the
    default limit), and this endpoint fires on every debounced keystroke.
    That is cheap on dev SQLite in-process but pays a round trip each in
    production Postgres. The OR stays cheap only because `limit` bounds it
    to ≤10 triples — it is not a general-purpose fetch.
    """
    query = query.strip()
    if len(query) < 2:
        return []

    keys = list(
        Product.objects.filter(is_active=True, name__icontains=query)
        .order_by('name', 'strength', 'pharmaceutical_form')
        .values_list('name', 'strength', 'pharmaceutical_form')
        .distinct()[:limit]
    )
    if not keys:
        return []

    chosen_groups = reduce(
        or_,
        (
            Q(name=name, strength=strength, pharmaceutical_form=pharmaceutical_form)
            for name, strength, pharmaceutical_form in keys
        ),
    )
    rows_by_key: dict[tuple[str, str, str], list[Product]] = defaultdict(list)
    for row in Product.objects.filter(chosen_groups, is_active=True).prefetch_related(
        'substance_links__substance'
    ):
        rows_by_key[(row.name, row.strength, row.pharmaceutical_form)].append(row)

    presentations = [_build_presentation(rows_by_key[key]) for key in keys]
    presentations.sort(key=lambda p: (_strength_sort_key(p.strength), p.name))
    return presentations


def _strength_sort_key(strength: str) -> float:
    m = re.match(r'[\d.,]+', strength)
    if m:
        try:
            return float(m.group().replace(',', '.'))
        except ValueError:
            pass
    return float('inf')
