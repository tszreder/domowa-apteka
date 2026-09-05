from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from households.models import Household, Membership


class SignupTests(TestCase):
    def test_signup_creates_user_household_and_membership(self) -> None:
        response = self.client.post(
            reverse('households:signup'),
            {
                'email': 'alice@example.com',
                'password1': 'wystarczajaco-trudne-haslo',
                'password2': 'wystarczajaco-trudne-haslo',
            },
        )

        self.assertRedirects(response, '/list/')
        user = User.objects.get(username='alice@example.com')
        membership = Membership.objects.get(user=user)
        self.assertTrue(Household.objects.filter(pk=membership.household_id).exists())

    def test_stored_username_is_lowercase_regardless_of_submitted_case(self) -> None:
        self.client.post(
            reverse('households:signup'),
            {
                'email': 'Alice@Example.com',
                'password1': 'wystarczajaco-trudne-haslo',
                'password2': 'wystarczajaco-trudne-haslo',
            },
        )

        self.assertTrue(User.objects.filter(username='alice@example.com').exists())
        self.assertFalse(User.objects.filter(username='Alice@Example.com').exists())

    def test_duplicate_email_differing_only_in_case_is_rejected(self) -> None:
        User.objects.create_user(username='alice@example.com', password='pass12345')

        response = self.client.post(
            reverse('households:signup'),
            {
                'email': 'Alice@Example.com',
                'password1': 'wystarczajaco-trudne-haslo',
                'password2': 'wystarczajaco-trudne-haslo',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['form'].errors.get('email'))
        self.assertEqual(User.objects.filter(username__iexact='alice@example.com').count(), 1)

    def test_authenticated_user_hitting_signup_is_redirected(self) -> None:
        household = Household.objects.create(name='Kowalscy')
        user = User.objects.create_user(username='bob@example.com', password='pass12345')
        Membership.objects.create(user=user, household=household)
        self.client.force_login(user)

        response = self.client.post(
            reverse('households:signup'),
            {
                'email': 'someone-else@example.com',
                'password1': 'wystarczajaco-trudne-haslo',
                'password2': 'wystarczajaco-trudne-haslo',
            },
        )

        self.assertRedirects(response, reverse('pharmacy:item_list'))
        self.assertFalse(User.objects.filter(username='someone-else@example.com').exists())


class LoginLogoutTests(TestCase):
    def setUp(self) -> None:
        self.household = Household.objects.create(name='Kowalscy')
        self.user = User.objects.create_user(username='alice@example.com', password='pass12345')
        Membership.objects.create(user=self.user, household=self.household)

    def test_login_succeeds_with_differently_cased_email(self) -> None:
        response = self.client.post(
            reverse('households:login'),
            {'username': 'Alice@Example.com', 'password': 'pass12345'},
        )

        self.assertRedirects(response, '/list/')
        self.assertIn('_auth_user_id', self.client.session)

    def test_logout_clears_session(self) -> None:
        self.client.force_login(self.user)

        response = self.client.post(reverse('households:logout'))

        self.assertRedirects(response, '/')
        self.assertNotIn('_auth_user_id', self.client.session)
