"""Read-only inspection surface over the mirrored registry snapshot.

Structurally incapable of modifying the data: an edit here could not survive
the next import, and would break source traceability until then.
"""

from django.contrib import admin
from django.db.models import QuerySet
from django.http import HttpRequest

from .models import Product, ProductSubstance, Substance


class ProductSubstanceInline(admin.TabularInline):
    model = ProductSubstance
    extra = 0
    fields = ('substance', 'amount', 'unit', 'source_field')
    readonly_fields = fields

    # Without select_related the read-only substance column costs one query
    # per row — 19 on Vaminolact, 46 on the widest product observed.
    def get_queryset(self, request: HttpRequest) -> QuerySet[ProductSubstance]:
        return super().get_queryset(request).select_related('substance')

    # Django's InlineModelAdmin.has_add_permission passes the parent object
    # positionally, but django-stubs types it off BaseModelAdmin, which takes
    # request only. `obj` therefore needs a default: without it the runtime
    # call fails, and without the default mypy rejects the override.
    def has_add_permission(self, request: HttpRequest, obj: Product | None = None) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Product | None = None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Product | None = None) -> bool:
        return False


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'common_name',
        'strength',
        'pharmaceutical_form',
        'last_seen_as_of',
        'is_active',
    )
    search_fields = ('name', 'common_name')
    list_filter = ('is_active',)
    inlines = (ProductSubstanceInline,)

    # has_view_permission is deliberately NOT overridden: it is what keeps the
    # read-only detail page reachable once change permission is denied.
    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Product | None = None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Product | None = None) -> bool:
        return False


@admin.register(Substance)
class SubstanceAdmin(admin.ModelAdmin):
    list_display = ('name', 'name_key')

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Substance | None = None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Substance | None = None) -> bool:
        return False
