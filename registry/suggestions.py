"""Presentation grouping and the default-product tiebreak.

Pure queries over `registry`'s own models — no HTTP attached, so the rules
that decide whether this slice is correct are testable in isolation. See
the plan's "Critical Implementation Details" and "Key Discoveries" for why
these two rules (grouping, tiebreak) exist and what they must hold against.
"""

from dataclasses import dataclass

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
    producers = sorted(
        (Producer(holder=row.marketing_holder, product_id=row.id) for row in rows),
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
    """
    if len(query) < 2:
        return []

    keys = (
        Product.objects.filter(is_active=True, name__icontains=query)
        .order_by('name', 'strength', 'pharmaceutical_form')
        .values_list('name', 'strength', 'pharmaceutical_form')
        .distinct()[:limit]
    )

    presentations = []
    for name, strength, pharmaceutical_form in keys:
        rows = list(
            Product.objects.filter(
                is_active=True,
                name=name,
                strength=strength,
                pharmaceutical_form=pharmaceutical_form,
            ).prefetch_related('substance_links__substance')
        )
        presentations.append(_build_presentation(rows))
    return presentations
