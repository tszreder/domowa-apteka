from typing import cast

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db import transaction
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from .decorators import household_required
from .forms import HouseholdCreateForm, SignupForm
from .models import Household, Membership

INVITE_TOKEN_SESSION_KEY = 'invite_token'


def _household_of(user: User) -> Household:
    """Household of a user `household_required` has already vouched for.

    The reverse one-to-one is invisible to django-stubs, and the decorator has
    already resolved (and cached) it on the instance, so this reads the cache
    without a second query.
    """
    membership = cast(Membership, getattr(user, 'membership'))
    return membership.household


def landing(request: HttpRequest) -> HttpResponse:
    return render(request, 'households/landing.html')


def signup(request: HttpRequest) -> HttpResponse:
    if request.user.is_authenticated:
        return redirect('households:landing')

    if request.method == 'POST':
        form = SignupForm(request.POST)
        if form.is_valid():
            invite_token = request.session.pop(INVITE_TOKEN_SESSION_KEY, None)
            invite_expired = False
            with transaction.atomic():
                user = form.save()
                household = None
                if invite_token:
                    household = Household.objects.filter(invite_token=invite_token).first()
                    invite_expired = household is None
                if household is None:
                    local_part = form.cleaned_data['email'].split('@')[0]
                    household = Household.objects.create(name=local_part)
                Membership.objects.create(user=user, household=household)
            auth_login(request, user)
            if invite_expired:
                messages.info(
                    request,
                    'Link zaproszenia był już nieaktualny, więc założono nowe gospodarstwo domowe.',
                )
            return redirect(settings.LOGIN_REDIRECT_URL)
    else:
        form = SignupForm()
    return render(request, 'households/signup.html', {'form': form})


def join(request: HttpRequest, token: str) -> HttpResponse:
    household = get_object_or_404(Household, invite_token=token)

    if not request.user.is_authenticated:
        request.session[INVITE_TOKEN_SESSION_KEY] = token
        return redirect('households:signup')

    user = cast(User, request.user)

    if not hasattr(user, 'membership'):
        if request.method != 'POST':
            return render(request, 'households/join_confirm.html', {'household': household})
        # get_or_create absorbs the IntegrityError a concurrent insert would raise and
        # re-gets the winner's row, so a double-submitted confirmation cannot 500.
        membership, created = Membership.objects.get_or_create(
            user=user, defaults={'household': household}
        )
        if created:
            messages.success(request, f'Dołączono do gospodarstwa „{household.name}”.')
            return redirect('households:household_detail')
    else:
        membership = user.membership

    same_household = membership.household_id == household.id
    return render(
        request,
        'households/join_refused.html',
        {'household': household, 'same_household': same_household},
    )


@household_required
def household_detail(request: HttpRequest) -> HttpResponse:
    household = _household_of(cast(User, request.user))
    invite_url = request.build_absolute_uri(
        reverse('households:join', kwargs={'token': household.invite_token})
    )
    members = household.memberships.select_related('user').all()
    return render(
        request,
        'households/household_detail.html',
        {'household': household, 'invite_url': invite_url, 'members': members},
    )


@household_required
@require_POST
def regenerate_invite(request: HttpRequest) -> HttpResponse:
    household = _household_of(cast(User, request.user))
    household.regenerate_invite_token()
    messages.success(request, 'Wygenerowano nowy link zaproszenia. Poprzedni link już nie działa.')
    return redirect('households:household_detail')


@login_required
def household_create(request: HttpRequest) -> HttpResponse:
    user = cast(User, request.user)
    if hasattr(user, 'membership'):
        return redirect('households:household_detail')

    if request.method == 'POST':
        form = HouseholdCreateForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                household = form.save()
                Membership.objects.create(user=user, household=household)
            return redirect('households:household_detail')
    else:
        form = HouseholdCreateForm()
    return render(request, 'households/household_create.html', {'form': form})
