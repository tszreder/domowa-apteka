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
        membership = Membership.objects.get(user=carol)
        self.assertNotEqual(membership.household_id, self.household.id)

    def test_authenticated_household_less_user_joins_directly(self) -> None:
        superuser = User.objects.create_superuser(
            username='admin@example.com', email='admin@example.com', password='pass12345'
        )
        self.client.force_login(superuser)
        join_url = reverse('households:join', kwargs={'token': self.household.invite_token})

        response = self.client.get(join_url)

        self.assertRedirects(response, reverse('households:household_detail'))
        membership = Membership.objects.get(user=superuser)
        self.assertEqual(membership.household_id, self.household.id)

    def test_authenticated_user_with_other_household_is_refused_without_second_membership(self) -> None:
        other_household = Household.objects.create(name='Nowakowie')
        other_owner = User.objects.create_user(username='dana@example.com', password='pass12345')
        Membership.objects.create(user=other_owner, household=other_household)
        self.client.force_login(other_owner)
        join_url = reverse('households:join', kwargs={'token': self.household.invite_token})

        response = self.client.get(join_url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Membership.objects.filter(user=other_owner).count(), 1)
        membership = Membership.objects.get(user=other_owner)
        self.assertEqual(membership.household_id, other_household.id)

    def test_authenticated_member_clicking_own_link_sees_plain_confirmation(self) -> None:
        self.client.force_login(self.owner)
        join_url = reverse('households:join', kwargs={'token': self.household.invite_token})

        response = self.client.get(join_url)

        self.assertEqual(response.status_code, 200)
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
