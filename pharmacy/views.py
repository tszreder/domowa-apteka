from typing import cast

from django.contrib.auth.models import User
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render

from households.decorators import household_required
from households.models import Household, Membership
from registry.suggestions import search_presentations

from .models import Item


def _household_of(user: User) -> Household:
    """Household of a user `household_required` has already vouched for."""
    membership = cast(Membership, getattr(user, 'membership'))
    return membership.household


@household_required
def item_list(request: HttpRequest) -> HttpResponse:
    household = _household_of(cast(User, request.user))
    items = Item.objects.filter(household=household).select_related('product').prefetch_related(
        'product__substance_links__substance'
    )
    return render(request, 'pharmacy/item_list.html', {'household': household, 'items': items})


@household_required
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
