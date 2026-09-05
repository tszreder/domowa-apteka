"""Duplicate-relationship rule for household items, keyed on substance sets.

Deliberately set-keyed (`frozenset[str]` in, `Overlap` out) rather than
item-paired. The prescription-check slice — `check_candidate` below — compares
a candidate registry `Product` the household does not own against household
items; that candidate has no `Item` to pair against, so the rule deciding "are
these duplicates" must not assume an `Item` exists on either side. A convenience
`classify(item_a, item_b)` would look natural here and would be wrong — it
would force that slice to reimplement this rule against a bare `Product`,
which is how two subtly different answers to "are these duplicates?" end up
shipping in one app. `build_list_view` and `check_candidate` are the only
functions below allowed to know `Item` exists; `substance_keys` and `classify`
never do.

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
class ItemStack:
    product: Product
    representative: Item
    count: int
    producer_confirmed: bool


@dataclass(frozen=True)
class DuplicateGroup:
    items: list[Item]
    same_product: bool
    partners: dict[str, list[str]]

    @property
    def is_cluster(self) -> bool:
        return len(self.items) > 1

    @property
    def stacks(self) -> list['ItemStack']:
        by_product: dict[int, list[Item]] = {}
        order: list[int] = []
        for item in self.items:
            if item.product_id not in by_product:
                by_product[item.product_id] = []
                order.append(item.product_id)
            by_product[item.product_id].append(item)
        return [
            ItemStack(
                product=by_product[pid][0].product,
                representative=by_product[pid][0],
                count=len(by_product[pid]),
                producer_confirmed=by_product[pid][0].producer_confirmed,
            )
            for pid in order
        ]

    @property
    def substance_names(self) -> list[str]:
        if not self.items:
            return []
        return [
            link.substance.name
            for link in self.items[0].product.substance_links.all()
        ]

    @property
    def partner_names(self) -> list[str]:
        names: list[str] = []
        for labels in self.partners.values():
            for label in labels:
                if label not in names:
                    names.append(label)
        return names


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
            # Sorted, not raw set iteration: `frozenset[str]` iterates in
            # string-hash order, which Python randomises per process, so two
            # workers would render the same badge with its substances — and
            # its `partner_names` — in different orders.
            for substance_key in sorted(key_a & key_b, key=lambda k: substance_names[k]):
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


class MatchKind(Enum):
    """How one household product relates to the candidate being checked.

    `classify`'s `FULL` is split in two here, because to someone holding a
    prescription the two halves are different facts: "you already have this
    exact box" and "you have a different brand of the same thing" lead to
    different sentences on the screen and different questions for the doctor.
    Collapsing them would make the check say less than it knows.
    """

    SAME_PRODUCT = auto()
    SAME_SUBSTANCES = auto()
    SHARED_SUBSTANCE = auto()


# Strongest first. Written out rather than read off `auto()`'s values: display
# order is a product decision about which answer the user needs first, and it
# must not change silently because someone reordered the enum members.
_MATCH_ORDER = (MatchKind.SAME_PRODUCT, MatchKind.SAME_SUBSTANCES, MatchKind.SHARED_SUBSTANCE)


@dataclass(frozen=True)
class CandidateMatch:
    """One household product the candidate matched, and what its row needs.

    `items` is every box of that product the household holds, in caller order.
    A list rather than a bare count because it is the seam `S-04` reads expiry
    dates off when that slice lands, with no change to this signature;
    `pack_count` derives from it so there is never a second source of truth
    about how many boxes are at home.

    `shared` is only meaningful for `SHARED_SUBSTANCE`. The other two kinds
    leave it empty: their substance sets are identical to the candidate's by
    definition, so naming them would only list the candidate's own substances
    back at the reader.
    """

    product: Product
    kind: MatchKind
    shared: list[str]
    items: list[Item]

    @property
    def pack_count(self) -> int:
        return len(self.items)

    # The enum is what tests assert on; these exist so the template needs no
    # enum in its context, the same way `DuplicateGroup.same_product` already
    # serves `item_list.html`.
    @property
    def is_same_product(self) -> bool:
        return self.kind is MatchKind.SAME_PRODUCT

    @property
    def is_same_substances(self) -> bool:
        return self.kind is MatchKind.SAME_SUBSTANCES

    @property
    def is_shared_substance(self) -> bool:
        return self.kind is MatchKind.SHARED_SUBSTANCE


@dataclass(frozen=True)
class CandidateCheck:
    """Render-ready answer to "does the household already hold this?".

    `candidate_substances` is what the comparison actually ran on, carried so
    the screen can show it rather than assert it. The check picks at
    presentation level with no producer step, and `registry/suggestions.py`
    records that 1.24% of presentation groups contain rows that disagree on
    substances — disclosure is the mitigation for that, not a second question
    to the user.

    `resolved` being false is a refusal, not a "no" — see `check_candidate`.
    `uncomparable_count` carries the same obligation for the other side of the
    comparison: a household holding items whose own substances never resolved
    makes "nothing at home matches" overstate what we know, so the count
    travels with the verdict instead of being dropped on the floor.
    """

    candidate_substances: list[str]
    matches: list[CandidateMatch]
    uncomparable_count: int

    @property
    def resolved(self) -> bool:
        return bool(self.candidate_substances)

    @property
    def only_same_product(self) -> bool:
        """Whether identity is the entire answer.

        True when the household holds the candidate itself and nothing else
        that shares its substances. The screen reads this to drop the line
        naming the substances the comparison ran on: that line is the
        transparency mitigation for picking at presentation level, and it
        earns its place only while there is a *substance* match for it to
        explain. Answering "you already have this exact product" was settled
        by primary keys, so listing substances underneath it is noise.

        False when `matches` is empty, so a no-match verdict still shows what
        was searched for.
        """
        return bool(self.matches) and all(match.is_same_product for match in self.matches)


def check_candidate(candidate: Product, items: Iterable[Item]) -> CandidateCheck:
    """Compare one candidate product against everything the household holds.

    `items` must arrive prefetched exactly as `build_list_view` requires, and
    `candidate` with `substance_links__substance`; every read below goes
    through `.all()`, so the caller's prefetch is honoured and nothing issues a
    query per item.

    Identity is settled by `item.product_id == candidate.pk` — before, and
    independently of, any substance comparison. That is the point: a primary
    key the registry itself assigned is stronger evidence than a substance set
    we derived from it, and it still holds when that derivation failed on
    either side. So a candidate whose substances we could not establish is not
    a total refusal; it can still answer "you already have exactly this at
    home" and refuse only the substitute question, which is the part genuinely
    unanswerable. Suppressing a known fact because a weaker one is missing is
    its own kind of wrong answer.

    Every *other* relationship goes through `classify`. No set is compared
    directly here: the reason this module is set-keyed at all is so one answer
    to "are these duplicates?" ships, not two that drift apart.
    """
    candidate_keys = substance_keys(candidate)
    # Display names for the keys `substance_keys` collapsed. `name_key` is
    # unique, so this cannot disagree with itself about a substance's spelling.
    candidate_names = {
        link.substance.name_key: link.substance.name for link in candidate.substance_links.all()
    }

    order: list[int] = []
    members_by_product: dict[int, list[Item]] = {}
    for item in items:
        if item.product_id not in members_by_product:
            members_by_product[item.product_id] = []
            order.append(item.product_id)
        members_by_product[item.product_id].append(item)

    matches: list[CandidateMatch] = []
    uncomparable_count = 0
    for product_id in order:
        members = members_by_product[product_id]
        keys = substance_keys(members[0].product)
        # Counted per box, not per product, and counted whether or not the
        # candidate resolved: this is "how much of the household did the
        # substance comparison not see", which the screen owes the user next to
        # any verdict. An item that is the candidate's own product is counted
        # here too when it is unresolved — it did not take part in a substance
        # comparison either; it matched on identity.
        if not keys:
            uncomparable_count += len(members)

        shared: list[str] = []
        if product_id == candidate.pk:
            kind = MatchKind.SAME_PRODUCT
        else:
            overlap = classify(candidate_keys, keys)
            if overlap is Overlap.NONE:
                continue
            if overlap is Overlap.FULL:
                kind = MatchKind.SAME_SUBSTANCES
            else:
                kind = MatchKind.SHARED_SUBSTANCE
                # Sorted, not raw set iteration: `frozenset[str]` iterates in
                # string-hash order, which Python randomises per process, so
                # the same row would name its shared substances in a different
                # order on the next reload, or from a second worker.
                shared = sorted(candidate_names[key] for key in candidate_keys & keys)

        matches.append(
            CandidateMatch(
                product=members[0].product,
                kind=kind,
                shared=shared,
                items=members,
            )
        )

    # Stable, so `Item.Meta.ordering` (`-added_at`) survives inside each tier
    # for free — the same property `build_list_view` relies on.
    matches.sort(key=lambda match: _MATCH_ORDER.index(match.kind))
    return CandidateCheck(
        candidate_substances=sorted(candidate_names.values()),
        matches=matches,
        uncomparable_count=uncomparable_count,
    )
