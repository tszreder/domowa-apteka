from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from households.models import Household, Membership


class CrossHouseholdIsolationTests(TestCase):
    """Proves that household *resolution* is scoped to the logged-in user's own membership.

    What this class proves: every view that calls `_household_of(request.user)` returns
    the household the logged-in user belongs to, never another household's record
    (households/views.py copy of `_household_of`).

    What this class does NOT prove: that household-owned records (Items, etc.) never leak
    across household boundaries. No Item is created for household_a in setUp, so
    `assertNotContains(response, household_a.name)` cannot observe item-level leakage.
    The item-level isolation guarantee is proven in:
      - pharmacy/tests/test_item_list.py::test_item_in_household_a_never_appears_for_member_of_household_b
      - pharmacy/tests/test_product_check.py
    """

    def setUp(self) -> None:
        self.household_a = Household.objects.create(name='Kowalscy')
        self.household_b = Household.objects.create(name='Nowakowie')
        self.member_a = User.objects.create_user(username='alice@example.com', password='pass12345')
        self.member_b = User.objects.create_user(username='bob@example.com', password='pass12345')
        Membership.objects.create(user=self.member_a, household=self.household_a)
        Membership.objects.create(user=self.member_b, household=self.household_b)

    def test_household_detail_only_ever_resolves_own_household(self) -> None:
        self.client.force_login(self.member_b)

        response = self.client.get(reverse('households:household_detail'))

        self.assertEqual(response.context['household'], self.household_b)
        self.assertNotContains(response, self.household_a.name)
        self.assertNotIn(self.household_a.invite_token, response.content.decode())

    def test_item_list_only_ever_resolves_own_household(self) -> None:
        self.client.force_login(self.member_b)

        response = self.client.get(reverse('pharmacy:item_list'))

        self.assertEqual(response.context['household'], self.household_b)
        self.assertNotContains(response, self.household_a.name)


class ProtectedUrlsRedirectAnonymousUsersTests(TestCase):
    def setUp(self) -> None:
        self.household = Household.objects.create(name='Kowalscy')
        self.member = User.objects.create_user(username='alice@example.com', password='pass12345')
        Membership.objects.create(user=self.member, household=self.household)

    def _assert_redirects_to_login(self, url: str) -> None:
        response = self.client.get(url)
        self.assertRedirects(response, f"{reverse('households:login')}?next={url}")

    def test_household_detail_redirects_anonymous_to_login(self) -> None:
        self._assert_redirects_to_login(reverse('households:household_detail'))

    def test_household_create_redirects_anonymous_to_login(self) -> None:
        self._assert_redirects_to_login(reverse('households:household_create'))

    def test_regenerate_invite_redirects_anonymous_to_login(self) -> None:
        self._assert_redirects_to_login(reverse('households:regenerate_invite'))

    def test_item_list_redirects_anonymous_to_login(self) -> None:
        self._assert_redirects_to_login(reverse('pharmacy:item_list'))


class HouseholdRequiredDecoratorTests(TestCase):
    def setUp(self) -> None:
        self.household = Household.objects.create(name='Kowalscy')
        self.member = User.objects.create_user(username='alice@example.com', password='pass12345')
        Membership.objects.create(user=self.member, household=self.household)
        self.household_less = User.objects.create_superuser(
            username='admin@example.com', email='admin@example.com', password='pass12345'
        )

    def test_household_less_user_redirected_to_household_create(self) -> None:
        self.client.force_login(self.household_less)

        response = self.client.get(reverse('pharmacy:item_list'))

        self.assertRedirects(response, reverse('households:household_create'))

    def test_household_less_redirect_does_not_loop(self) -> None:
        self.client.force_login(self.household_less)

        response = self.client.get(reverse('pharmacy:item_list'), follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'households/household_create.html')

    def test_household_holding_user_reaches_list_directly(self) -> None:
        self.client.force_login(self.member)

        response = self.client.get(reverse('pharmacy:item_list'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['household'], self.household)

    def test_anonymous_user_redirect_does_not_loop(self) -> None:
        response = self.client.get(reverse('pharmacy:item_list'), follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'households/login.html')
