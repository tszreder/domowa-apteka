from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.test import TestCase

from households.models import Household, Membership


class HouseholdModelTests(TestCase):
    def test_invite_token_generated_on_save(self) -> None:
        household = Household.objects.create(name='Kowalscy')
        self.assertTrue(household.invite_token)

    def test_invite_token_unique_across_households(self) -> None:
        first = Household.objects.create(name='Kowalscy')
        second = Household.objects.create(name='Nowakowie')
        self.assertNotEqual(first.invite_token, second.invite_token)

    def test_regenerate_invite_token_changes_value(self) -> None:
        household = Household.objects.create(name='Kowalscy')
        original_token = household.invite_token
        household.regenerate_invite_token()
        self.assertNotEqual(household.invite_token, original_token)

    def test_regenerate_invite_token_does_not_alter_membership(self) -> None:
        household = Household.objects.create(name='Kowalscy')
        user = User.objects.create_user(username='alice@example.com', password='pass12345')
        membership = Membership.objects.create(user=user, household=household)

        household.regenerate_invite_token()
        membership.refresh_from_db()

        self.assertEqual(membership.household_id, household.id)
        self.assertEqual(membership.user_id, user.id)

    def test_delete_cascades_to_membership_not_user(self) -> None:
        household = Household.objects.create(name='Kowalscy')
        user = User.objects.create_user(username='alice@example.com', password='pass12345')
        Membership.objects.create(user=user, household=household)

        household.delete()

        self.assertFalse(Membership.objects.filter(user=user).exists())
        self.assertTrue(User.objects.filter(pk=user.pk).exists())


class MembershipModelTests(TestCase):
    def test_second_membership_for_same_user_raises_integrity_error(self) -> None:
        household_a = Household.objects.create(name='Kowalscy')
        household_b = Household.objects.create(name='Nowakowie')
        user = User.objects.create_user(username='alice@example.com', password='pass12345')
        Membership.objects.create(user=user, household=household_a)

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Membership.objects.create(user=user, household=household_b)
