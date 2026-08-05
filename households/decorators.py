from functools import wraps
from typing import Callable, cast

from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect


def household_required(view_func: Callable[..., HttpResponse]) -> Callable[..., HttpResponse]:
    """Redirect anonymous users to login and household-less users to household creation.

    Never apply this to `/household/create/`, `/join/<token>/`, `/login/`,
    `/signup/`, or `/` — those are the undecorated escape hatches this
    decorator redirects to, and decorating one of them would create a loop.
    """

    @login_required
    @wraps(view_func)
    def wrapper(request: HttpRequest, *args: object, **kwargs: object) -> HttpResponse:
        user = cast(User, request.user)
        if not hasattr(user, 'membership'):
            return redirect('households:household_create')
        return view_func(request, *args, **kwargs)

    return wrapper
