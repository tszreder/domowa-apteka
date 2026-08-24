"""Duplicate-relationship rule for household items, keyed on substance sets.

Deliberately set-keyed (`frozenset[str]` in, `Overlap` out) rather than
item-paired. The planned prescription-check slice compares a candidate
registry `Product` the household does not own against household items; that
candidate has no `Item` to pair against, so the rule deciding "are these
duplicates" must not assume an `Item` exists on either side. A convenience
`classify(item_a, item_b)` would look natural here and would be wrong — it
would force that slice to reimplement this rule against a bare `Product`,
which is how two subtly different answers to "are these duplicates?" end up
shipping in one app. `build_list_view` is the only function below allowed to
know `Item` exists; `substance_keys` and `classify` never do.

Mirrors `registry/suggestions.py`'s shape: pure query/grouping functions, no
HTTP attached, so the rules that decide whether this slice is correct are
testable in isolation.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum, auto

from registry.models import Product

from .models import Item


class Overlap(Enum):
    FULL = auto()
    PARTIAL = auto()
    NONE = auto()


def substance_keys(product: Product) -> frozenset[str]:
    """Deduplicated identity set for `product`'s active substances.

    Reads `product.substance_links.all()` — the same prefetch-safe path
    `Item.unresolved` uses; any `.filter()`/`.exists()`/`.count()` here would
    issue a query per product and reintroduce N+1. Keyed on
    `Substance.name_key`, not `name`: a comparison on display form would
    split a merged spelling pair and miss a real duplicate. The `frozenset`
    collapses the intentional `(product, substance)` repeats a product can
    carry at different amounts (no unique constraint on that pair —
    `registry/models.py`'s `ProductSubstance`).
    """
    return frozenset(link.substance.name_key for link in product.substance_links.all())


def classify(a: frozenset[str], b: frozenset[str]) -> Overlap:
    """FULL on equality, PARTIAL on non-empty intersection, else NONE.

    Either side empty always returns NONE, checked before the equality test:
    `frozenset() == frozenset()` is `True` in Python, so without this guard
    every unresolved item would classify as a full duplicate of every other
    unresolved item — the exact silent grouping US-03 forbids.
    """
    if not a or not b:
        return Overlap.NONE
    if a == b:
        return Overlap.FULL
    if a & b:
        return Overlap.PARTIAL
    return Overlap.NONE


@dataclass(frozen=True)
class DuplicateGroup:
    """One row the list renders: a full-duplicate cluster, or a single item.

    `same_product` only means something when `is_cluster` is true — it is
    the answer to "same-product repeat, or true zamienniki (different
    products, same substances)". `partners` maps a shared substance's
    display name to the product names it was matched against, for items in
    *other* groups whose sets partially overlap this one's.
    """

    items: list[Item]
    same_product: bool
    partners: dict[str, list[str]]

    @property
    def is_cluster(self) -> bool:
        return len(self.items) > 1


@dataclass(frozen=True)
class ItemListView:
    """Render-ready shape for the household item list."""

    groups: list[DuplicateGroup]
    unresolved: list[Item]


def _product_names(items: list[Item]) -> list[str]:
    names: list[str] = []
    for item in items:
        name = item.product.name
        if name not in names:
            names.append(name)
    return names


def build_list_view(items: Iterable[Item]) -> ItemListView:
    """Partition, cluster, and cross-annotate `items` for rendering.

    `items` must already be prefetched
    (`select_related('product')` + `prefetch_related('product__substance_links__substance')`)
    and iterated in the caller's intended display order. This function does
    not re-query or re-sort by `added_at`: a group's position is simply the
    position of the first — i.e. newest, given `Item.Meta.ordering` — item
    that introduces its substance set, so the newest-first feel survives
    grouping for free.

    Partial-overlap partners are computed between groups, not between raw
    items: members of one group share an identical substance set by
    definition, so pairing raw items would emit the same badge once per
    member instead of once per group.
    """
    resolved: list[Item] = []
    unresolved: list[Item] = []
    keys_by_item: dict[int, frozenset[str]] = {}
    for item in items:
        keys = substance_keys(item.product)
        keys_by_item[item.pk] = keys
        (resolved if keys else unresolved).append(item)

    order: list[frozenset[str]] = []
    members_by_key: dict[frozenset[str], list[Item]] = {}
    for item in resolved:
        key = keys_by_item[item.pk]
        if key not in members_by_key:
            members_by_key[key] = []
            order.append(key)
        members_by_key[key].append(item)

    substance_names: dict[str, str] = {}
    for item in resolved:
        for link in item.product.substance_links.all():
            substance_names.setdefault(link.substance.name_key, link.substance.name)

    partners: dict[frozenset[str], dict[str, list[str]]] = {key: {} for key in order}
    for i, key_a in enumerate(order):
        for key_b in order[i + 1 :]:
            if classify(key_a, key_b) is not Overlap.PARTIAL:
                continue
            labels_a = _product_names(members_by_key[key_a])
            labels_b = _product_names(members_by_key[key_b])
            for substance_key in key_a & key_b:
                name = substance_names[substance_key]
                partners[key_a].setdefault(name, []).extend(labels_b)
                partners[key_b].setdefault(name, []).extend(labels_a)

    groups = [
        DuplicateGroup(
            items=members_by_key[key],
            same_product=len({item.product_id for item in members_by_key[key]}) == 1,
            partners=partners[key],
        )
        for key in order
    ]
    return ItemListView(groups=groups, unresolved=unresolved)
