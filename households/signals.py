from django.contrib import messages
from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver
from django.http import HttpRequest

from .models import Household, Membership

INVITE_TOKEN_SESSION_KEY = 'invite_token'


@receiver(user_logged_in)
def consume_invite_token_on_login(
    sender: type, request: HttpRequest, user: object, **kwargs: object
) -> None:
    token = request.session.pop(INVITE_TOKEN_SESSION_KEY, None)
    if not token:
        return

    household = Household.objects.filter(invite_token=token).first()
    if household is None:
        return

    if hasattr(user, 'membership'):
        if user.membership.household_id == household.id:  # type: ignore[union-attr]
            messages.info(request, f'Już należysz do gospodarstwa „{household.name}".')
        else:
            messages.info(
                request,
                'Należysz już do innego gospodarstwa domowego.',
            )
        return

    Membership.objects.get_or_create(user=user, defaults={'household': household})
    messages.success(request, f'Dołączyłeś do gospodarstwa „{household.name}".')
