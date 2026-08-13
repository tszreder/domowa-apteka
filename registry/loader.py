"""Write a `ParseResult` to the database. Deliberately dumb.

Every rule about *what* a substance is lives in `parser.py`. This module only
decides where rows go, and it never deletes a product: S-02 will put user items
behind foreign keys to `Product`, so a delete on a routine refresh would cascade
into user data. Products missing from a snapshot are flagged inactive instead.

**The write order is load-bearing**, because steps 4 and 5 select on the date
step 2 stamps:

1. Insert the substances this snapshot references that we do not already have.
2. Upsert the products, stamping every one with this snapshot's `stanNaDzien`.
3. Build the id maps by querying, never off a `bulk_create` return value.
4. Delete and re-create the links of the products carrying this snapshot's date.
5. Flag everything else inactive.

Selecting on the date rather than on a list of product ids is what keeps steps 4
and 5 to one bound query parameter each. An `id__in=[…]` form would bind one per
product (20,187 today) against SQLite's 32,766-variable ceiling, and Django does
not chunk `__in` on the fast-delete path — a limit no test could ever see, since
the fixture holds 14 products.

**That date predicate assumes snapshot dates advance**, which the publisher's
daily export does. Importing two *different* files that share a `stanNaDzien`
would delete the links of any product absent from the second without re-creating
them. Stated rather than guarded: no realistic snapshot sequence reaches it.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

from django.db import transaction

from .models import Product, ProductSubstance, SourceField, Substance
from .parser import ParseResult

# Well under SQLite's 32,766-variable ceiling for the widest row here
# (ProductSubstance, 10 columns → 10,000 parameters per batch).
BATCH_SIZE = 1000

# Every mutable Product column. `registry_id` is deliberately absent: it is the
# conflict target, and Django rejects any overlap with `unique_fields`.
# `is_active` is deliberately present — it is what brings a withdrawn product
# back when a later snapshot lists it again.
PRODUCT_UPDATE_FIELDS = (
    'name',
    'common_name',
    'strength',
    'pharmaceutical_form',
    'marketing_holder',
    'kind',
    'permit_number',
    'leaflet_url',
    'characteristics_url',
    'last_seen_as_of',
    'is_active',
)


@dataclass(frozen=True)
class LoadStats:
    """What one load did, for the command's summary line."""

    source_as_of: date
    products_loaded: int
    products_created: int
    # Products absent from this snapshot, now flagged inactive. Cumulative, not
    # newly-flipped: the update matches every product carrying an older date,
    # including ones already inactive from an earlier run.
    products_inactive: int
    substances_created: int
    links_created: int
    links_by_source_field: dict[str, int]


def load_parse_result(result: ParseResult) -> LoadStats:
    """Persist one snapshot idempotently, in a single transaction."""
    with transaction.atomic():
        substances_created = _insert_new_substances(result.substances)
        products_created = _upsert_products(result)

        # Queried, never read off the bulk_create return value: options.md §9
        # measured PK population on in-memory SQLite and only *reasoned* that
        # Postgres matches. Two 0.02 s queries remove the dependency instead of
        # designing around an unverified engine claim.
        substance_ids = dict(Substance.objects.values_list('name_key', 'pk'))
        product_ids = dict(Product.objects.values_list('registry_id', 'pk'))

        links_by_source_field = _rebuild_links(result, product_ids, substance_ids)
        products_inactive = Product.objects.exclude(
            last_seen_as_of=result.source_as_of
        ).update(is_active=False)

    return LoadStats(
        source_as_of=result.source_as_of,
        products_loaded=len(result.products),
        products_created=products_created,
        products_inactive=products_inactive,
        substances_created=substances_created,
        links_created=sum(links_by_source_field.values()),
        links_by_source_field=links_by_source_field,
    )


def _insert_new_substances(substances: Iterable[tuple[str, str]]) -> int:
    """Insert the `name_key`s we do not have yet. Insert-only, forever.

    An `update_conflicts=True, update_fields=['name']` upsert would be
    last-write-wins on the display name, which defeats the parser's first-seen
    tiebreak: a reordered snapshot would silently flip `Sodu fluorek` to
    `sodu fluorek`. Insert-only makes first-seen-wins hold across runs, not just
    within one parse.

    `substances` arrives already deduplicated on `name_key` and in first-seen
    order (`ParseResult.substances`). Re-deriving it here by walking the links
    would break the unique constraint the first time one file holds a
    case-collision pair — the real export holds five.
    """
    existing_keys = set(Substance.objects.values_list('name_key', flat=True))
    missing = [
        Substance(name=name, name_key=name_key)
        for name, name_key in substances
        if name_key not in existing_keys
    ]
    Substance.objects.bulk_create(missing, batch_size=BATCH_SIZE)
    return len(missing)


def _upsert_products(result: ParseResult) -> int:
    """Upsert on `registry_id`, stamping this snapshot's date on every row."""
    known_ids = set(Product.objects.values_list('registry_id', flat=True))
    rows = [
        Product(
            registry_id=product.registry_id,
            name=product.name,
            common_name=product.common_name,
            strength=product.strength,
            pharmaceutical_form=product.pharmaceutical_form,
            marketing_holder=product.marketing_holder,
            kind=product.kind,
            permit_number=product.permit_number,
            leaflet_url=product.leaflet_url,
            characteristics_url=product.characteristics_url,
            last_seen_as_of=result.source_as_of,
            is_active=True,
        )
        for product in result.products
    ]
    Product.objects.bulk_create(
        rows,
        batch_size=BATCH_SIZE,
        update_conflicts=True,
        update_fields=PRODUCT_UPDATE_FIELDS,
        unique_fields=('registry_id',),
    )
    return sum(1 for product in result.products if product.registry_id not in known_ids)


def _rebuild_links(
    result: ParseResult,
    product_ids: dict[str, int],
    substance_ids: dict[str, int],
) -> dict[str, int]:
    """Replace the links of every product in this snapshot.

    Delete-then-insert rather than upsert: the through-table deliberately has no
    unique key (89 source rows across the real export repeat a substance on the
    same product at a different amount), so there is nothing to upsert *on*.
    Link rows carry no external foreign keys, so the delete cascades nowhere —
    which is what makes this safe as well as idempotent.
    """
    ProductSubstance.objects.filter(
        product__last_seen_as_of=result.source_as_of
    ).delete()

    counts = {field.value: 0 for field in SourceField}
    rows = []
    for product in result.products:
        product_pk = product_ids[product.registry_id]
        for link in product.links:
            rows.append(
                ProductSubstance(
                    product_id=product_pk,
                    substance_id=substance_ids[link.name_key],
                    amount=link.amount,
                    unit=link.unit,
                    preparation_amount=link.preparation_amount,
                    preparation_unit=link.preparation_unit,
                    amount_description=link.amount_description,
                    source_field=link.source_field,
                    source_order=link.source_order,
                )
            )
            counts[link.source_field] += 1

    ProductSubstance.objects.bulk_create(rows, batch_size=BATCH_SIZE)
    return counts
