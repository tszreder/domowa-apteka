"""Authorization boundary and the POST-only guard on delete."""

from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from households.models import Household, Membership
from pharmacy.models import Item
from registry.models import Product

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


class ItemDeleteAuthTests(TestCase):
    def setUp(self) -> None:
        self.household = Household.objects.create(name='Kowalscy')
        self.product = make_product('1')
        self.item = Item.objects.create(household=self.household, product=self.product)

    def test_anonymous_post_redirects_to_login(self) -> None:
        url = reverse('pharmacy:item_delete', args=[self.item.pk])

        response = self.client.post(url)

        self.assertRedirects(response, f"{reverse('households:login')}?next={url}")
        self.assertTrue(Item.objects.filter(pk=self.item.pk).exists())

    def test_household_less_user_redirects_to_household_create(self) -> None:
        user = User.objects.create_user(username='alice@example.com', password='pass12345')
        self.client.force_login(user)

        response = self.client.post(reverse('pharmacy:item_delete', args=[self.item.pk]))

        self.assertRedirects(response, reverse('households:household_create'))
        self.assertTrue(Item.objects.filter(pk=self.item.pk).exists())


class ItemDeleteTests(TestCase):
    def setUp(self) -> None:
        self.household = Household.objects.create(name='Kowalscy')
        self.other_household = Household.objects.create(name='Nowakowie')
        self.member = User.objects.create_user(username='alice@example.com', password='pass12345')
        self.other_member = User.objects.create_user(username='carol@example.com', password='pass12345')
        Membership.objects.create(user=self.member, household=self.household)
        Membership.objects.create(user=self.other_member, household=self.household)
        self.product = make_product('1')
        self.item = Item.objects.create(
            household=self.household, product=self.product, added_by=self.other_member
        )
        self.client.force_login(self.member)

    def test_member_deletes_their_households_item(self) -> None:
        response = self.client.post(reverse('pharmacy:item_delete', args=[self.item.pk]))

        self.assertRedirects(response, reverse('pharmacy:item_list'))
        self.assertFalse(Item.objects.filter(pk=self.item.pk).exists())

    def test_member_can_delete_item_added_by_different_household_member(self) -> None:
        # self.item was added_by=other_member, deleted here by self.member — the
        # roles are symmetric, so "added by someone else" is not a refusal reason.
        self.client.post(reverse('pharmacy:item_delete', args=[self.item.pk]))

        self.assertFalse(Item.objects.filter(pk=self.item.pk).exists())

    def test_member_of_another_household_gets_404_and_item_survives(self) -> None:
        member_b = User.objects.create_user(username='bob@example.com', password='pass12345')
        Membership.objects.create(user=member_b, household=self.other_household)
        self.client.force_login(member_b)

        response = self.client.post(reverse('pharmacy:item_delete', args=[self.item.pk]))

        self.assertEqual(response.status_code, 404)
        self.assertTrue(Item.objects.filter(pk=self.item.pk).exists())

    def test_get_is_rejected_with_405_and_deletes_nothing(self) -> None:
        response = self.client.get(reverse('pharmacy:item_delete', args=[self.item.pk]))

        self.assertEqual(response.status_code, 405)
        self.assertTrue(Item.objects.filter(pk=self.item.pk).exists())
