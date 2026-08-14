"""The JSON contract phase 3's autocomplete JavaScript will consume, and the auth boundary."""

from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from households.models import Household, Membership
from registry.models import Product

AS_OF = date(2026, 8, 13)


class SuggestionsEndpointAuthTests(TestCase):
    def test_anonymous_get_redirects_to_login(self) -> None:
        url = reverse('pharmacy:product_suggestions')

        response = self.client.get(url)

        self.assertRedirects(response, f"{reverse('households:login')}?next={url}")

    def test_household_less_user_redirects_to_household_create(self) -> None:
        user = User.objects.create_user(username='alice@example.com', password='pass12345')
        self.client.force_login(user)

        response = self.client.get(reverse('pharmacy:product_suggestions'), {'q': 'apap'})

        self.assertRedirects(response, reverse('households:household_create'))


class SuggestionsEndpointContractTests(TestCase):
    def setUp(self) -> None:
        self.household = Household.objects.create(name='Kowalscy')
        self.member = User.objects.create_user(username='alice@example.com', password='pass12345')
        Membership.objects.create(user=self.member, household=self.household)
        self.client.force_login(self.member)
        Product.objects.create(
            registry_id='1', name='Apap Extra', strength='500 mg',
            pharmaceutical_form='Tabletki', kind='ludzki', last_seen_as_of=AS_OF,
        )

    def test_member_gets_json_with_documented_keys(self) -> None:
        response = self.client.get(reverse('pharmacy:product_suggestions'), {'q': 'apap'})

        self.assertEqual(response['Content-Type'], 'application/json')
        data = response.json()
        self.assertIn('results', data)
        result = data['results'][0]
        self.assertEqual(
            set(result.keys()),
            {'name', 'strength', 'form', 'substances', 'default_product_id', 'producers'},
        )

    def test_short_query_returns_empty_results(self) -> None:
        response = self.client.get(reverse('pharmacy:product_suggestions'), {'q': 'a'})

        self.assertEqual(response.json(), {'results': []})

    def test_response_is_application_json(self) -> None:
        response = self.client.get(reverse('pharmacy:product_suggestions'), {'q': 'apap'})

        self.assertEqual(response['Content-Type'], 'application/json')
