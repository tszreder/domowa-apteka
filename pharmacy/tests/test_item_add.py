"""Server side of the add flow — the JavaScript is not unit-tested."""

from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from households.models import Household, Membership
from pharmacy.models import Item
from registry.models import Product, ProductSubstance, SourceField, Substance

AS_OF = date(2026, 8, 13)


def make_product(registry_id: str, name: str = 'Apap', **overrides: object) -> Product:
    defaults: dict[str, object] = {
        'registry_id': registry_id,
        'name': name,
        'kind': 'ludzki',
        'last_seen_as_of': AS_OF,
        'is_active': True,
    }
    defaults.update(overrides)
    return Product.objects.create(**defaults)


class ItemAddAuthTests(TestCase):
    def test_anonymous_get_redirects_to_login(self) -> None:
        url = reverse('pharmacy:item_add')

        response = self.client.get(url)

        self.assertRedirects(response, f"{reverse('households:login')}?next={url}")

    def test_household_less_user_redirects_to_household_create(self) -> None:
        user = User.objects.create_user(username='alice@example.com', password='pass12345')
        self.client.force_login(user)

        response = self.client.get(reverse('pharmacy:item_add'))

        self.assertRedirects(response, reverse('households:household_create'))


class ItemAddTests(TestCase):
    def setUp(self) -> None:
        self.household = Household.objects.create(name='Kowalscy')
        self.other_household = Household.objects.create(name='Nowakowie')
        self.member = User.objects.create_user(username='alice@example.com', password='pass12345')
        Membership.objects.create(user=self.member, household=self.household)
        self.client.force_login(self.member)

    def test_valid_post_creates_item_in_requesting_users_household(self) -> None:
        product = make_product('1')

        response = self.client.post(
            reverse('pharmacy:item_add'), {'product': product.id, 'producer_confirmed': 'true'}
        )

        self.assertRedirects(response, reverse('pharmacy:item_list'))
        item = Item.objects.get()
        self.assertEqual(item.household, self.household)
        self.assertEqual(item.added_by, self.member)

    def test_item_not_created_in_any_other_household(self) -> None:
        product = make_product('1')

        self.client.post(
            reverse('pharmacy:item_add'), {'product': product.id, 'producer_confirmed': 'true'}
        )

        self.assertFalse(Item.objects.filter(household=self.other_household).exists())

    def test_inactive_product_rejected_with_form_error_and_creates_nothing(self) -> None:
        product = make_product('1', is_active=False)

        response = self.client.post(
            reverse('pharmacy:item_add'), {'product': product.id, 'producer_confirmed': 'true'}
        )

        self.assertEqual(response.status_code, 200)
        self.assertFormError(
            response.context['form'], 'product', 'Ten produkt nie jest już dostępny w rejestrze.'
        )
        self.assertFalse(Item.objects.exists())

    def test_unresolved_product_still_creates_item_and_warns(self) -> None:
        product = make_product('1', name='Peditrace')

        response = self.client.post(
            reverse('pharmacy:item_add'),
            {'product': product.id, 'producer_confirmed': 'true'},
            follow=True,
        )

        self.assertTrue(Item.objects.filter(product=product).exists())
        messages = [(m.tags, str(m)) for m in response.context['messages']]
        self.assertTrue(any('warning' in tags for tags, _ in messages))

    def test_resolved_product_produces_success_message_naming_substances(self) -> None:
        product = make_product('1', name='Apap Extra')
        substance = Substance.objects.create(name='Paracetamol', name_key='paracetamol')
        ProductSubstance.objects.create(
            product=product, substance=substance,
            source_field=SourceField.SUBSTANCE_ROW, source_order=0,
        )

        response = self.client.post(
            reverse('pharmacy:item_add'),
            {'product': product.id, 'producer_confirmed': 'true'},
            follow=True,
        )

        messages = [(m.tags, str(m)) for m in response.context['messages']]
        self.assertTrue(any('success' in tags and 'Paracetamol' in text for tags, text in messages))

    def test_omitting_producer_confirmed_stores_false(self) -> None:
        product = make_product('1')

        self.client.post(reverse('pharmacy:item_add'), {'product': product.id})

        item = Item.objects.get()
        self.assertFalse(item.producer_confirmed)

    def test_member_of_household_b_cannot_see_item_household_a_just_added(self) -> None:
        product = make_product('1', name='Apap Extra')
        self.client.post(
            reverse('pharmacy:item_add'), {'product': product.id, 'producer_confirmed': 'true'}
        )

        member_b = User.objects.create_user(username='bob@example.com', password='pass12345')
        Membership.objects.create(user=member_b, household=self.other_household)
        # A fresh client, not a force_login swap on the same one: this test
        # is about server-side household scoping, and reusing self.client's
        # cookie jar would carry member A's queued flash message along —
        # a same-browser artifact of the messages framework, not a scoping
        # bug in the view.
        other_client = self.client_class()
        other_client.force_login(member_b)

        response = other_client.get(reverse('pharmacy:item_list'))

        self.assertNotContains(response, 'Apap Extra')
