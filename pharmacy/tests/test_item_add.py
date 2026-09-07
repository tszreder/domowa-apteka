"""Server side of the add flow — the JavaScript is not unit-tested."""

from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from households.models import Household, Membership
from pharmacy.models import Item
from registry.models import Product, ProductSubstance, SourceField, Substance
from registry.suggestions import search_presentations

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
            response.context['form'], 'product', 'Wybrany lek nie został znaleziony. Spróbuj ponownie.'
        )
        self.assertFalse(Item.objects.exists())

    def test_empty_product_shows_custom_required_error(self) -> None:
        response = self.client.post(
            reverse('pharmacy:item_add'), {'product': '', 'producer_confirmed': 'false'}
        )

        self.assertEqual(response.status_code, 200)
        self.assertFormError(
            response.context['form'], 'product', 'Wybierz lek z listy podpowiedzi.'
        )

    def test_adding_duplicate_shows_warning_flash(self) -> None:
        para = Substance.objects.create(name='Paracetamol', name_key='paracetamol')
        product = make_product('1', name='Apap')
        ProductSubstance.objects.create(
            product=product, substance=para,
            source_field=SourceField.SUBSTANCE_ROW, source_order=0,
        )
        Item.objects.create(household=self.household, product=product)

        response = self.client.post(
            reverse('pharmacy:item_add'),
            {'product': product.id, 'producer_confirmed': 'true'},
            follow=True,
        )

        msgs = [str(m) for m in response.context['messages']]
        self.assertTrue(any('Uwaga' in m for m in msgs))

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

    def test_posting_producer_confirmed_false_stores_false(self) -> None:
        # The path the browser actually takes: autocomplete.js always submits
        # the literal string 'false', never omits the field. This passes only
        # because BooleanField.to_python special-cases 'false' and '0' — an
        # undocumented framework nicety. Without this test, changing the field
        # or widget would make 'false' truthy, every unconfirmed item would
        # render the tiebreak default producer as fact, and the suite would
        # stay green. The omission test above covers a different, still-valid
        # HTTP shape; neither replaces the other.
        product = make_product('1')

        self.client.post(
            reverse('pharmacy:item_add'),
            {'product': product.id, 'producer_confirmed': 'false'},
        )

        item = Item.objects.get()
        self.assertFalse(item.producer_confirmed)

    def test_collision_persists_default_product_and_its_own_substances(self) -> None:
        # The "Sortis 20" shape (registry/tests/test_suggestions.py:151-167):
        # two rows share name/strength/form with no distinguishing producer
        # (no marketing_holder on either) and disagree on substances. Proves
        # the suggestions-layer tiebreak is what item_add actually persists,
        # not just what search_presentations reports.
        atorvastatinum = Substance.objects.create(name='Atorvastatinum', name_key='atorvastatinum')
        atorvastatinum_calcicum = Substance.objects.create(
            name='Atorvastatinum calcicum', name_key='atorvastatinum_calcicum'
        )
        higher = make_product('200', name='Sortis 20')
        ProductSubstance.objects.create(
            product=higher, substance=atorvastatinum_calcicum,
            source_field=SourceField.SUBSTANCE_ROW, source_order=0,
        )
        lower = make_product('100', name='Sortis 20')
        ProductSubstance.objects.create(
            product=lower, substance=atorvastatinum,
            source_field=SourceField.SUBSTANCE_ROW, source_order=0,
        )

        presentation = search_presentations('sortis')[0]
        response = self.client.post(
            reverse('pharmacy:item_add'),
            {'product': presentation.default_product_id, 'producer_confirmed': 'false'},
        )

        self.assertRedirects(response, reverse('pharmacy:item_list'))
        item = Item.objects.get()
        self.assertEqual(item.product_id, presentation.default_product_id)
        self.assertEqual(item.product_id, lower.id)
        persisted_substances = [link.substance.name for link in item.product.substance_links.all()]
        self.assertEqual(persisted_substances, presentation.substances)
        self.assertEqual(persisted_substances, ['Atorvastatinum'])
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
