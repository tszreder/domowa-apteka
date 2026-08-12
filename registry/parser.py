"""Turn one `overall.xml` snapshot into typed records. No database, no network.

Every rule that touches the NFR's "never infer an identity the source does not
state" line lives here, so all of it is testable against a fixture: the
human-use filter, the placeholder denylist, and the E1 common-name fallback.

Three decisions are deliberate and load-bearing enough to state outright.

**The substance-name vocabulary is accumulated over the whole file, veterinary
products included, before the human-use filter runs.** options.md §8 defines the
fallback test as "that exact string is in the registry's own substance
vocabulary" without saying which subset it computed that over. Whole-file is the
plain reading — a veterinary product's `nazwaSubstancji` is still the registry
using that string as a substance name — and it costs one line of ordering. It
admits no veterinary product into the data; it only widens the set of strings
the fallback will accept.

**The vocabulary deliberately includes denylisted names.** `Produkt złożony`
genuinely is used as a `nazwaSubstancji`, so it genuinely passes the membership
test (options.md §8a). Filtering it out of the vocabulary would block the
fallback for the wrong reason and leave `denylist.py` load-bearing in name only.
The denylist is checked separately, and it is the only guard.

**`ParseResult.substances` carries only the names an emitted link points at**,
in whole-file first-seen order. The wider membership set stays internal. The
loader's `Substance` insert is insert-only forever, so anything extra here would
become a permanent row with no links — including the placeholders the denylist
exists to keep out of the data. The first-seen tiebreak is therefore computed
over **every `nazwaSubstancji` in the file in document order**, not over the
emitted links: when a case-collision pair straddles a veterinary product, the
spelling that survives is the first one the registry stated as a substance name
anywhere. A fallback link reuses that stored spelling rather than the product's
own `nazwaPowszechnieStosowana`, so a displayed substance name always comes from
somewhere the registry used it as a substance name.
"""

import re
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path
from typing import Any
from xml.etree.ElementTree import Element

from .denylist import DENYLISTED_SUBSTANCE_KEYS
from .models import SourceField

# A constant, so widening the filter later is a one-line change plus a
# re-import — no migration, and `Product.kind` keeps the filter auditable.
INCLUDED_PRODUCT_KINDS = frozenset({'ludzki'})

_NAMESPACE_TEMPLATE = 'http://rejestry.ezdrowie.gov.pl/rpl/eksport-danych-v{version}'
_VERSION_IN_URL = re.compile(r'/(\d+\.\d+\.\d+)(?=/|$)')


class RegistryParseError(ValueError):
    """The file is not the snapshot we were told to expect.

    Raised loudly and early rather than half-succeeding: importing a 7.0.0
    export as though it were 6.0.0 is exactly the version-lifecycle failure
    options.md §12 risk 1 describes.
    """


@dataclass(frozen=True)
class SubstanceLinkRecord:
    """One product→substance link, mirroring `ProductSubstance`'s fields."""

    name: str
    name_key: str
    amount: str
    unit: str
    preparation_amount: str
    preparation_unit: str
    amount_description: str
    source_field: str
    # Position among *emitted* links, contiguous from 0. Dropped rows (blank or
    # denylisted names) close the gap rather than leaving a hole, so the common-
    # name fallback's single link can share the same numbering.
    source_order: int


@dataclass(frozen=True)
class ProductRecord:
    """One human-use product, mirroring `Product`'s fields plus its links."""

    registry_id: str
    name: str
    common_name: str
    strength: str
    pharmaceutical_form: str
    marketing_holder: str
    kind: str
    permit_number: str
    leaflet_url: str
    characteristics_url: str
    links: tuple[SubstanceLinkRecord, ...]


@dataclass(frozen=True)
class ParseResult:
    """Everything one snapshot yields, ready for the loader to write."""

    source_as_of: date
    products: tuple[ProductRecord, ...]
    # (name, name_key) pairs, deduplicated on name_key, in first-seen order.
    substances: tuple[tuple[str, str], ...]
    # Every product in the file, veterinary included — the denominator behind
    # the human-use share, and the honest input to a plausibility guard.
    products_in_file: int
    substance_row_links: int
    common_name_links: int
    products_without_links: int


def namespace_for_url(url: str) -> str:
    """Derive the expected XML namespace from the configured export URL.

    The namespace is never pinned separately. A hardcoded `…-v6.0.0` assert
    would cancel out `REGISTRY_OVERALL_URL`: pointing it at a 7.0.0 path — the
    whole reason the setting exists — would then fail every import at the
    assert. Deriving it here keeps URL and namespace from drifting apart.
    """
    match = _VERSION_IN_URL.search(url)
    if match is None:
        raise RegistryParseError(
            f'No version segment (e.g. /6.0.0/) in registry URL: {url!r}. '
            'The expected XML namespace is derived from it and cannot be guessed.'
        )
    return _NAMESPACE_TEMPLATE.format(version=match.group(1))


def parse_registry(path: Path, expected_namespace: str) -> ParseResult:
    """Stream `path` once, emitting one record per human-use product.

    `expected_namespace` comes from `namespace_for_url()` at the call site, so
    this stays a pure function of its arguments — it reads no Django settings.
    """
    events = ET.iterparse(path, events=('start', 'end'))
    source_as_of = _read_root(events, expected_namespace)

    product_tag = f'{{{expected_namespace}}}produktLeczniczy'
    substance_tag = f'{{{expected_namespace}}}substancjaCzynna'

    # name_key -> first-seen verbatim spelling, in document order.
    vocabulary: dict[str, str] = {}
    referenced_keys: set[str] = set()
    products: list[ProductRecord] = []
    # Indices into `products` whose fallback cannot be decided yet: the
    # validating substance row may still be ahead of us in the file.
    deferred: list[int] = []
    products_in_file = 0
    substance_row_links = 0

    for event, elem in events:
        if event != 'end' or elem.tag != product_tag:
            continue
        products_in_file += 1

        # Vocabulary first, human-use filter second. Reversing these silently
        # narrows the set of strings the fallback will accept.
        rows = []
        for row in elem.iter(substance_tag):
            name = _attr(row, 'nazwaSubstancji').strip()
            if not name:
                continue
            name_key = name.casefold()
            vocabulary.setdefault(name_key, name)
            rows.append((name, name_key, row))

        if _attr(elem, 'rodzajPreparatu') in INCLUDED_PRODUCT_KINDS:
            kept = [row for row in rows if row[1] not in DENYLISTED_SUBSTANCE_KEYS]
            links = tuple(
                SubstanceLinkRecord(
                    name=name,
                    name_key=name_key,
                    # Copied as strings, never float()ed: the source is
                    # Polish-formatted ('3,13'), so float() raises or truncates.
                    amount=_attr(row, 'iloscSubstancji'),
                    unit=_attr(row, 'jednostkaMiaryIlosciSubstancji'),
                    preparation_amount=_attr(row, 'iloscPreparatu'),
                    preparation_unit=_attr(row, 'jednostkaMiaryIlosciPreparatu'),
                    amount_description=_attr(row, 'innyOpisIlosci'),
                    source_field=SourceField.SUBSTANCE_ROW,
                    source_order=order,
                )
                for order, (name, name_key, row) in enumerate(kept)
            )
            referenced_keys.update(link.name_key for link in links)
            substance_row_links += len(links)
            products.append(_product_record(elem, links))
            if not links:
                deferred.append(len(products) - 1)

        # Including the products the filter rejected: those are the easy ones to
        # forget, and this call is the difference between the measured single-
        # digit MB streaming peak and roughly 1 GB resident.
        elem.clear()

    common_name_links = _resolve_deferred(products, deferred, vocabulary, referenced_keys)

    return ParseResult(
        source_as_of=source_as_of,
        products=tuple(products),
        substances=tuple(
            (name, name_key)
            for name_key, name in vocabulary.items()
            if name_key in referenced_keys
        ),
        products_in_file=products_in_file,
        substance_row_links=substance_row_links,
        common_name_links=common_name_links,
        products_without_links=sum(1 for product in products if not product.links),
    )


def _read_root(events: Iterator[tuple[str, Any]], expected_namespace: str) -> date:
    """Consume the root's `start` event and validate it. Returns `stanNaDzien`.

    It has to be the `start` event. The root's `end` event does not fire until
    all 73.7 MB have been streamed, which would defer the version guard to the
    very end of the run and leave `stanNaDzien` unavailable while every product
    record was being built.
    """
    try:
        event, root = next(events)
    except StopIteration as exc:
        raise RegistryParseError('Registry file is empty — no root element.') from exc

    expected_tag = f'{{{expected_namespace}}}produktyLecznicze'
    if event != 'start' or root.tag != expected_tag:
        raise RegistryParseError(
            f'Expected root element {expected_tag!r}, found {root.tag!r}. '
            'The file is not the export version this URL claims to serve.'
        )

    raw_as_of = _attr(root, 'stanNaDzien')
    try:
        return date.fromisoformat(raw_as_of)
    except ValueError as exc:
        raise RegistryParseError(
            f'Root stanNaDzien is not a date: {raw_as_of!r}.'
        ) from exc


def _resolve_deferred(
    products: list[ProductRecord],
    deferred: list[int],
    vocabulary: dict[str, str],
    referenced_keys: set[str],
) -> int:
    """Apply the E1 fallback to the products that ended with no links.

    This cannot be decided while streaming forward: the product whose substance
    row validates another product's common name may appear later in the file
    (`Beto 200 ZK` needs `Beto 25 ZK`, which follows it). options.md §8c
    measures only ~1,054 products needing deferral, so holding them costs
    nothing.

    Be precise about what the fallback is, because it decides how the NFR
    applies: the vocabulary attests that the *string* is one the registry uses
    as a substance name. It never attests that this product contains that
    substance. That link is our inference — which is why it is tagged
    `common_name` rather than passed off as stated fact.
    """
    resolved = 0
    for index in deferred:
        product = products[index]
        name_key = product.common_name.strip().casefold()
        if not name_key or name_key in DENYLISTED_SUBSTANCE_KEYS:
            continue
        name = vocabulary.get(name_key)
        if name is None:
            continue
        products[index] = replace(
            product,
            links=(
                SubstanceLinkRecord(
                    name=name,
                    name_key=name_key,
                    amount='',
                    unit='',
                    preparation_amount='',
                    preparation_unit='',
                    amount_description='',
                    source_field=SourceField.COMMON_NAME,
                    source_order=0,
                ),
            ),
        )
        referenced_keys.add(name_key)
        resolved += 1
    return resolved


def _product_record(elem: Element, links: tuple[SubstanceLinkRecord, ...]) -> ProductRecord:
    return ProductRecord(
        registry_id=_attr(elem, 'id'),
        name=_attr(elem, 'nazwaProduktu'),
        common_name=_attr(elem, 'nazwaPowszechnieStosowana'),
        strength=_attr(elem, 'moc'),
        pharmaceutical_form=_attr(elem, 'nazwaPostaciFarmaceutycznej'),
        marketing_holder=_attr(elem, 'podmiotOdpowiedzialny'),
        kind=_attr(elem, 'rodzajPreparatu'),
        permit_number=_attr(elem, 'numerPozwolenia'),
        # Parallel-import products (typProcedury="IR") carry the leaflet under a
        # different attribute name entirely. A plain elem.get('ulotka') returns
        # None for that whole population.
        leaflet_url=_attr(elem, 'ulotka') or _attr(elem, 'ulotkaImportRownolegly'),
        characteristics_url=(
            _attr(elem, 'charakterystyka')
            or _attr(elem, 'oznaczenieOpakowanImportRownolegly')
        ),
        links=links,
    )


def _attr(elem: Element, name: str) -> str:
    """Read one attribute as `str`, empty when absent.

    Every attribute in this export is optional in practice, so `elem.get()`
    types as `str | None` and mypy rejects passing it anywhere a `str` is
    wanted. Routing every read through here is what keeps `parser.py` free of
    `# type: ignore`.
    """
    value = elem.get(name)
    return value if value is not None else ''
