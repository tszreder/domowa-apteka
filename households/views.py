from django.conf import settings
from django.contrib.auth import login as auth_login
from django.db import transaction
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render

from .forms import SignupForm
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
