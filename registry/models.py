"""Local mirror of the Polish national medicinal-products registry.

Reference data, not user data: every row here is a copy of something the
registry stated in its daily `overall.xml` snapshot, and the import command
is free to overwrite it. Nothing in this app is user-editable.
"""

from django.db import models


class SourceField(models.TextChoices):
    """How a product→substance link was resolved.

    `SUBSTANCE_ROW` is what the registry stated outright. `COMMON_NAME` is our
    inference from the product's `nazwaPowszechnieStosowana`, accepted only when
    that exact string is used as a substance name elsewhere in the same file.
    The distinction is the whole point of the column: a resolved substance must
    never be presented as stated fact when it was inferred.
    """

    SUBSTANCE_ROW = 'substance_row', 'Explicit substance row'
    COMMON_NAME = 'common_name', 'Product common name (inferred)'


class Substance(models.Model):
    """The deduplicated active-substance vocabulary.

    `name_key` is the identity; `name` is only the display form. Which verbatim
    spelling a merged pair keeps is first-seen-wins, decided by the parser and
    preserved by the loader's insert-only write.
    """

    name = models.CharField(max_length=255)
    name_key = models.CharField(max_length=255, unique=True, db_index=True)

    def __str__(self) -> str:
        return self.name


class Product(models.Model):
    """One human-use medicinal product, keyed on the registry's own `id`."""

    registry_id = models.CharField(max_length=32, unique=True, db_index=True)
    name = models.CharField(max_length=255, db_index=True)
    common_name = models.CharField(max_length=255, blank=True)
    # TextField, not CharField: observed `moc` values run to multi-paragraph
    # free text. Displayable, never parsed.
    strength = models.TextField(blank=True)
    pharmaceutical_form = models.CharField(max_length=255, blank=True)
    marketing_holder = models.CharField(max_length=255, blank=True)
    # Always 'ludzki' under the current human-use filter. Stored so the filter
    # is auditable and can widen without a migration.
    kind = models.CharField(max_length=32)
    permit_number = models.CharField(max_length=64, blank=True)
    leaflet_url = models.URLField(max_length=500, blank=True)
    characteristics_url = models.URLField(max_length=500, blank=True)
    # The `stanNaDzien` of the most recent snapshot containing this product —
    # the freshness value, and the one F-02 reads. Deliberately the only date
    # column: a second one would carry the same value on every row on every run.
    last_seen_as_of = models.DateField()
    is_active = models.BooleanField(default=True)

    def __str__(self) -> str:
        return self.name


class ProductSubstance(models.Model):
    """A product→substance link, with the amount fields the source stated.

    Deliberately carries no unique constraint on `(product, substance)`: 89
    source rows across 29,064 legitimately repeat a substance on the same
    product at a different amount.
    """

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='substance_links',
    )
    # PROTECT, not CASCADE: a substance must never disappear while links
    # reference it.
    substance = models.ForeignKey(
        Substance,
        on_delete=models.PROTECT,
        related_name='product_links',
    )
    # Text, not numeric: values are Polish-formatted with a decimal comma
    # ('3,13'), so float() raises or truncates.
    amount = models.CharField(max_length=64, blank=True)
    unit = models.CharField(max_length=64, blank=True)
    preparation_amount = models.CharField(max_length=64, blank=True)
    preparation_unit = models.CharField(max_length=64, blank=True)
    amount_description = models.TextField(blank=True)
    source_field = models.CharField(max_length=32, choices=SourceField.choices)
    # 0-based position among this product's *emitted* links, so repeated
    # substances keep their relative source order. Not the source element's
    # index: the parser drops blank and denylisted rows and closes the gap, so
    # the fallback's single link can share the same numbering.
    source_order = models.PositiveSmallIntegerField()

    class Meta:
        # Without this, nothing reads source_order and the row order is
        # whatever the engine returns — unspecified in SQL, and not stable
        # across the loader's per-snapshot delete-and-recreate on Postgres.
        ordering = ['source_order']

    def __str__(self) -> str:
        return f'{self.substance} in {self.product}'


class RunStatus(models.TextChoices):
    """Where an import attempt currently stands.

    `RUNNING` is the state a row is created in, before any work happens —
    `import_registry` writes the row first so a crash the `except` clause
    cannot even catch (a killed process, an OOM) still leaves evidence rather
    than nothing. It should never be the last state anyone reads for a
    completed process; a row stuck at `RUNNING` past its own run is itself a
    signal, not a success.
    """

    RUNNING = 'running', 'Running'
    SUCCESS = 'success', 'Success'
    FAILED = 'failed', 'Failed'


class RunTrigger(models.TextChoices):
    """How an import attempt was started.

    Diagnosis only — the freshness verdict is deliberately trigger-agnostic —
    but without it a manually-run import would make a dead cron look healthy.
    """

    MANUAL = 'manual', 'Manual'
    SCHEDULED = 'scheduled', 'Scheduled'


class ImportRun(models.Model):
    """One row per `import_registry` attempt, success or failure.

    Written outside the import's own `transaction.atomic()` block (see
    `import_registry.py`), so a failure record survives the exact rollback it
    exists to capture. This is the app's own record of "did the pipeline run",
    independent of whether the platform's cron scheduler fired it — see
    `registry/freshness.py` for the verdict this feeds.
    """

    started_at = models.DateTimeField(db_index=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=RunStatus.choices, default=RunStatus.RUNNING)
    trigger = models.CharField(max_length=16, choices=RunTrigger.choices)
    attempts = models.PositiveSmallIntegerField(default=0)
    # The snapshot's own stanNaDzien. Null on a failed run: it never learned
    # one. Carried for display and diagnosis; deliberately NOT part of the
    # freshness verdict — see registry/freshness.py.
    source_as_of = models.DateField(null=True, blank=True)
    error = models.TextField(blank=True)

    # LoadStats counters, all nullable: a failed run has none of them.
    products_loaded = models.PositiveIntegerField(null=True, blank=True)
    products_created = models.PositiveIntegerField(null=True, blank=True)
    products_inactive = models.PositiveIntegerField(null=True, blank=True)
    substances_created = models.PositiveIntegerField(null=True, blank=True)
    links_created = models.PositiveIntegerField(null=True, blank=True)
    products_without_links = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ['-started_at']

    def __str__(self) -> str:
        return f'{self.status} run started {self.started_at}'
