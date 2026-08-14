from typing import cast

from django.contrib.auth.models import User
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from households.decorators import household_required
from households.models import Household, Membership

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
