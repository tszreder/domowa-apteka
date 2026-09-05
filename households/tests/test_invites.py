from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from households.models import Household, Membership
from households.views import INVITE_TOKEN_SESSION_KEY


class JoinViewTests(TestCase):
    def setUp(self) -> None:
        self.household = Household.objects.create(name='Kowalscy')
        self.owner = User.objects.create_user(username='alice@example.com', password='pass12345')
        Membership.objects.create(user=self.owner, household=self.household)

    def test_anonymous_join_stashes_token_and_completes_on_signup(self) -> None:
        join_url = reverse('households:join', kwargs={'token': self.household.invite_token})

        response = self.client.get(join_url)

        self.assertRedirects(response, reverse('households:signup'))
        self.assertEqual(self.client.session[INVITE_TOKEN_SESSION_KEY], self.household.invite_token)

        self.client.post(
            reverse('households:signup'),
            {
                'email': 'bob@example.com',
                'password1': 'wystarczajaco-trudne-haslo',
                'password2': 'wystarczajaco-trudne-haslo',
            },
        )

        bob = User.objects.get(username='bob@example.com')
        membership = Membership.objects.get(user=bob)
        self.assertEqual(membership.household_id, self.household.id)

    def test_session_key_cleared_after_signup_so_later_signup_does_not_rejoin(self) -> None:
        join_url = reverse('households:join', kwargs={'token': self.household.invite_token})
        self.client.get(join_url)

        self.client.post(
            reverse('households:signup'),
            {
                'email': 'bob@example.com',
                'password1': 'wystarczajaco-trudne-haslo',
                'password2': 'wystarczajaco-trudne-haslo',
            },
        )
        self.assertNotIn(INVITE_TOKEN_SESSION_KEY, self.client.session)
        self.client.post(reverse('households:logout'))

        self.client.post(
            reverse('households:signup'),
            {
                'email': 'carol@example.com',
                'password1': 'wystarczajaco-trudne-haslo',
                'password2': 'wystarczajaco-trudne-haslo',
            },
        )

        carol = User.objects.get(username='carol@example.com')
        self.assertFalse(Membership.objects.filter(user=carol).exists())

    def test_authenticated_household_less_user_confirms_then_joins_on_post(self) -> None:
        superuser = User.objects.create_superuser(
            username='admin@example.com', email='admin@example.com', password='pass12345'
        )
        self.client.force_login(superuser)
        join_url = reverse('households:join', kwargs={'token': self.household.invite_token})

        confirmation = self.client.get(join_url)

        self.assertEqual(confirmation.status_code, 200)
        self.assertTemplateUsed(confirmation, 'households/join_confirm.html')
        self.assertFalse(Membership.objects.filter(user=superuser).exists())

        response = self.client.post(join_url)

        self.assertRedirects(response, reverse('households:household_detail'))
        membership = Membership.objects.get(user=superuser)
        self.assertEqual(membership.household_id, self.household.id)

    def test_sequential_repeat_post_is_refused_not_duplicated(self) -> None:
        """A re-POST after joining hits the already-a-member branch, not a second create.

        This does *not* cover the concurrent double-submit: by the second request the
        membership is loaded with `request.user`, so `hasattr` is True and the view never
        reaches `get_or_create`. That race is unrepresentable in a single-threaded
        `TestCase` — `get_or_create` is the guard, verified by reading, not by this test.
        """
        superuser = User.objects.create_superuser(
            username='admin@example.com', email='admin@example.com', password='pass12345'
        )
        self.client.force_login(superuser)
        join_url = reverse('households:join', kwargs={'token': self.household.invite_token})
        self.client.post(join_url)

        response = self.client.post(join_url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['same_household'], True)
        self.assertEqual(Membership.objects.filter(user=superuser).count(), 1)

    def test_authenticated_user_with_other_household_is_refused_without_second_membership(self) -> None:
        other_household = Household.objects.create(name='Nowakowie')
        other_owner = User.objects.create_user(username='dana@example.com', password='pass12345')
        Membership.objects.create(user=other_owner, household=other_household)
        self.client.force_login(other_owner)
        join_url = reverse('households:join', kwargs={'token': self.household.invite_token})

        response = self.client.get(join_url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['same_household'], False)
        self.assertEqual(Membership.objects.filter(user=other_owner).count(), 1)
        membership = Membership.objects.get(user=other_owner)
        self.assertEqual(membership.household_id, other_household.id)

    def test_authenticated_member_clicking_own_link_sees_plain_confirmation(self) -> None:
        self.client.force_login(self.owner)
        join_url = reverse('households:join', kwargs={'token': self.household.invite_token})

        response = self.client.get(join_url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['same_household'], True)
        self.assertEqual(Membership.objects.filter(user=self.owner).count(), 1)

    def test_bogus_token_404s(self) -> None:
        response = self.client.get(reverse('households:join', kwargs={'token': 'does-not-exist'}))
        self.assertEqual(response.status_code, 404)

    def test_regenerated_token_invalidates_previous_url(self) -> None:
        old_token = self.household.invite_token
        self.household.regenerate_invite_token()

        response = self.client.get(reverse('households:join', kwargs={'token': old_token}))

        self.assertEqual(response.status_code, 404)
        self.assertTrue(Household.objects.filter(pk=self.household.pk).exists())
        self.assertTrue(Membership.objects.filter(household=self.household).exists())


class SignupWithStaleInviteTests(TestCase):
    def test_signup_with_stale_token_creates_user_without_household(self) -> None:
        household = Household.objects.create(name='Kowalscy')
        owner = User.objects.create_user(username='alice@example.com', password='pass12345')
        Membership.objects.create(user=owner, household=household)

        join_url = reverse('households:join', kwargs={'token': household.invite_token})
        self.client.get(join_url)
        household.regenerate_invite_token()

        response = self.client.post(
            reverse('households:signup'),
            {
                'email': 'bob@example.com',
                'password1': 'wystarczajaco-trudne-haslo',
                'password2': 'wystarczajaco-trudne-haslo',
            },
        )

        self.assertRedirects(response, '/list/', target_status_code=302)
        bob = User.objects.get(username='bob@example.com')
        self.assertFalse(Membership.objects.filter(user=bob).exists())


class InviteTokenOnLoginTests(TestCase):
    """F-11: invite token consumed on login via signal handler."""

    def setUp(self) -> None:
        self.household = Household.objects.create(name='Kowalscy')
        self.owner = User.objects.create_user(username='alice@example.com', password='pass12345')
        Membership.objects.create(user=self.owner, household=self.household)
        self.existing_user = User.objects.create_user(
            username='bob@example.com', password='pass12345'
        )

    def test_login_with_invite_token_creates_membership(self) -> None:
        join_url = reverse('households:join', kwargs={'token': self.household.invite_token})
        self.client.get(join_url)

        self.client.post(
            reverse('households:login'),
            {'username': 'bob@example.com', 'password': 'pass12345'},
        )

        self.assertTrue(Membership.objects.filter(user=self.existing_user).exists())
        membership = Membership.objects.get(user=self.existing_user)
        self.assertEqual(membership.household_id, self.household.id)

    def test_stale_token_on_login_does_nothing(self) -> None:
        join_url = reverse('households:join', kwargs={'token': self.household.invite_token})
        self.client.get(join_url)
        self.household.regenerate_invite_token()

        self.client.post(
            reverse('households:login'),
            {'username': 'bob@example.com', 'password': 'pass12345'},
        )

        self.assertFalse(Membership.objects.filter(user=self.existing_user).exists())

    def test_user_already_in_household_gets_info(self) -> None:
        other_household = Household.objects.create(name='Nowakowie')
        Membership.objects.create(user=self.existing_user, household=other_household)

        join_url = reverse('households:join', kwargs={'token': self.household.invite_token})
        self.client.get(join_url)

        response = self.client.post(
            reverse('households:login'),
            {'username': 'bob@example.com', 'password': 'pass12345'},
            follow=True,
        )

        membership = Membership.objects.get(user=self.existing_user)
        self.assertEqual(membership.household_id, other_household.id)
        msgs = [str(m) for m in response.context['messages']]
        self.assertTrue(any('innego' in m for m in msgs))

    def test_token_cleared_from_session_after_login(self) -> None:
        join_url = reverse('households:join', kwargs={'token': self.household.invite_token})
        self.client.get(join_url)

        self.client.post(
            reverse('households:login'),
            {'username': 'bob@example.com', 'password': 'pass12345'},
        )

        self.assertNotIn(INVITE_TOKEN_SESSION_KEY, self.client.session)


class RegenerateInviteTests(TestCase):
    def setUp(self) -> None:
        self.household = Household.objects.create(name='Kowalscy')
        self.owner = User.objects.create_user(username='alice@example.com', password='pass12345')
        Membership.objects.create(user=self.owner, household=self.household)

    def test_regeneration_requires_post(self) -> None:
        self.client.force_login(self.owner)
        old_token = self.household.invite_token

        response = self.client.get(reverse('households:regenerate_invite'))

        self.assertEqual(response.status_code, 405)
        self.household.refresh_from_db()
        self.assertEqual(self.household.invite_token, old_token)

    def test_regeneration_via_post_changes_token(self) -> None:
        self.client.force_login(self.owner)
        old_token = self.household.invite_token

        response = self.client.post(reverse('households:regenerate_invite'))

        self.assertRedirects(response, reverse('households:household_detail'))
        self.household.refresh_from_db()
        self.assertNotEqual(self.household.invite_token, old_token)
