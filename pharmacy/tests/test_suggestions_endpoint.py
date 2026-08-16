"""The JSON contract phase 3's autocomplete JavaScript will consume, and the auth boundary."""

from datetime import date

from django.contrib.auth.models import User
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from households.models import Household, Membership
from registry.models import Product, ProductSubstance, SourceField, Substance

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

    def test_post_is_rejected(self) -> None:
        response = self.client.post(reverse('pharmacy:product_suggestions'), {'q': 'apap'})

        self.assertEqual(response.status_code, 405)


class SuggestionsEndpointQueryCountTests(TestCase):
    """Pin the query *shape*, which the list view guards but this path did not.

    This endpoint fires on every debounced keystroke, so it is the most
    frequently hit query in the app. The count must not scale with the number
    of matched groups: a per-group hydration loop costs 1+3N statements, which
    is invisible on dev SQLite in-process and expensive over a network.
    """

    def setUp(self) -> None:
        self.household = Household.objects.create(name='Kowalscy')
        self.member = User.objects.create_user(username='alice@example.com', password='pass12345')
        Membership.objects.create(user=self.member, household=self.household)
        self.client.force_login(self.member)

    def _make_groups(self, count: int) -> None:
        # Every product carries a substance link on purpose: with none, the
        # second prefetch level resolves to an empty id set and Django skips
        # that query, so a link-free fixture would pin a count one lower than
        # production ever sees.
        # get_or_create, not create: the growth test calls this twice.
        substance, _ = Substance.objects.get_or_create(
            name='Paracetamol', name_key='paracetamol'
        )
        for i in range(count):
            product = Product.objects.create(
                registry_id=str(i), name=f'Apap {i}', strength='500 mg',
                pharmaceutical_form='Tabletki', kind='ludzki', last_seen_as_of=AS_OF,
            )
            ProductSubstance.objects.create(
                product=product, substance=substance,
                source_field=SourceField.SUBSTANCE_ROW, source_order=0,
            )

    def test_query_count_does_not_grow_with_the_number_of_groups(self) -> None:
        # The load-bearing assertion: one group and ten cost the same. A
        # regression to per-group hydration fails here even if the absolute
        # number below is later renegotiated.
        self._make_groups(1)
        with CaptureQueriesContext(connection) as one_group:
            self.client.get(reverse('pharmacy:product_suggestions'), {'q': 'apap'})

        Product.objects.all().delete()
        self._make_groups(10)
        with CaptureQueriesContext(connection) as ten_groups:
            response = self.client.get(reverse('pharmacy:product_suggestions'), {'q': 'apap'})

        self.assertEqual(len(response.json()['results']), 10)
        self.assertEqual(len(ten_groups), len(one_group))

    def test_query_count_is_bounded(self) -> None:
        self._make_groups(10)

        # 1 session + 1 user + 1 membership (household_required), then
        # 1 distinct-keys query + 1 OR'd hydration + 2 prefetch.
        with self.assertNumQueries(7):
            self.client.get(reverse('pharmacy:product_suggestions'), {'q': 'apap'})
