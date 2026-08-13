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
    # 0-based position of the source element within its product, so repeated
    # substances keep their source order.
    source_order = models.PositiveSmallIntegerField()

    class Meta:
        # Without this, nothing reads source_order and the row order is
        # whatever the engine returns — unspecified in SQL, and not stable
        # across the loader's per-snapshot delete-and-recreate on Postgres.
        ordering = ['source_order']

    def __str__(self) -> str:
        return f'{self.substance} in {self.product}'
