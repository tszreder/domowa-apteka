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

from .forms import HouseholdCreateForm, SignupForm
from .models import Household, Membership

INVITE_TOKEN_SESSION_KEY = 'invite_token'


def landing(request: HttpRequest) -> HttpResponse:
    return render(request, 'households/landing.html')


def signup(request: HttpRequest) -> HttpResponse:
    if request.user.is_authenticated:
        return redirect('households:landing')

    if request.method == 'POST':
        form = SignupForm(request.POST)
        if form.is_valid():
            invite_token = request.session.pop(INVITE_TOKEN_SESSION_KEY, None)
            with transaction.atomic():
                user = form.save()
                if invite_token:
                    household = Household.objects.get(invite_token=invite_token)
                else:
                    local_part = form.cleaned_data['email'].split('@')[0]
                    household = Household.objects.create(name=local_part)
                Membership.objects.create(user=user, household=household)
            auth_login(request, user)
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
        Membership.objects.create(user=user, household=household)
        messages.success(request, f'Dołączono do gospodarstwa „{household.name}”.')
        return redirect('households:household_detail')

    same_household = user.membership.household_id == household.id
    return render(
        request,
        'households/join_refused.html',
        {'household': household, 'same_household': same_household},
    )


@login_required
def household_detail(request: HttpRequest) -> HttpResponse:
    user = cast(User, request.user)
    if not hasattr(user, 'membership'):
        return redirect('households:household_create')

    household = user.membership.household
    invite_url = request.build_absolute_uri(
        reverse('households:join', kwargs={'token': household.invite_token})
    )
    members = household.memberships.select_related('user').all()
    return render(
        request,
        'households/household_detail.html',
        {'household': household, 'invite_url': invite_url, 'members': members},
    )


@login_required
@require_POST
def regenerate_invite(request: HttpRequest) -> HttpResponse:
    user = cast(User, request.user)
    if not hasattr(user, 'membership'):
        return redirect('households:household_create')

    household = user.membership.household
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
