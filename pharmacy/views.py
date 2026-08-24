from typing import cast

from django.contrib import messages
from django.contrib.auth.models import User
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from households.decorators import household_required
from households.models import Household, Membership
from registry.suggestions import search_presentations

from .duplicates import build_list_view
from .forms import ItemAddForm
from .models import Item


def _household_of(user: User) -> Household:
    """Household of a user `household_required` has already vouched for."""
    membership = cast(Membership, getattr(user, 'membership'))
    return membership.household


@household_required
def item_list(request: HttpRequest) -> HttpResponse:
    household = _household_of(cast(User, request.user))
    items = list(
        Item.objects.filter(household=household)
        .select_related('product')
        .prefetch_related('product__substance_links__substance')
    )
    list_view = build_list_view(items)
    return render(
        request,
        'pharmacy/item_list.html',
        {'household': household, 'items': items, 'list_view': list_view},
    )


@household_required
@require_GET
def product_suggestions(request: HttpRequest) -> HttpResponse:
    query = request.GET.get('q', '')
    presentations = search_presentations(query)
    results = [
        {
            'name': presentation.name,
            'strength': presentation.strength,
            'form': presentation.pharmaceutical_form,
            'substances': presentation.substances,
            'default_product_id': presentation.default_product_id,
            'producers': [
                {'holder': producer.holder, 'product_id': producer.product_id}
                for producer in presentation.producers
            ],
        }
        for presentation in presentations
    ]
    return JsonResponse({'results': results})


@household_required
def item_add(request: HttpRequest) -> HttpResponse:
    household = _household_of(cast(User, request.user))
    if request.method == 'POST':
        form = ItemAddForm(request.POST)
        if form.is_valid():
            item = form.save(commit=False)
            item.household = household
            item.added_by = request.user
            item.save()
            substances = [
                link.substance.name for link in item.product.substance_links.all()
            ]
            if substances:
                messages.success(
                    request,
                    f'Dodano {item.product.name}. Substancje czynne: {", ".join(substances)}.',
                )
            else:
                messages.warning(
                    request,
                    f'Dodano {item.product.name}, ale nie udało się ustalić jego '
                    'substancji czynnej na podstawie rejestru.',
                )
            return redirect(reverse('pharmacy:item_list'))
    else:
        form = ItemAddForm()
    return render(request, 'pharmacy/item_form.html', {'form': form})


@household_required
@require_POST
def item_delete(request: HttpRequest, pk: int) -> HttpResponse:
    household = _household_of(cast(User, request.user))
    # Filtered by household before lookup: an item belonging to another
    # household is a 404, not a 403 — the endpoint never confirms the id exists.
    item = get_object_or_404(Item, pk=pk, household=household)
    item.delete()
    messages.success(request, f'Usunięto {item.product.name}.')
    return redirect(reverse('pharmacy:item_list'))
