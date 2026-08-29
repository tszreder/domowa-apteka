"""The three-form Polish plural rule, including the teens exception.

Pure logic: no DB, no request. The teens cases are the ones a naive
`n % 10 in (2, 3, 4)` implementation gets wrong, so they are asserted
explicitly rather than left to a spot check.
"""

from django.test import SimpleTestCase

from pharmacy.templatetags.polish import plural_pl

FORMS = 'opakowanie,opakowania,opakowań'


class PluralPlTests(SimpleTestCase):
    def test_one_takes_the_singular(self) -> None:
        self.assertEqual(plural_pl(1, FORMS), 'opakowanie')

    def test_two_three_and_four_take_the_few_form(self) -> None:
        for count in (2, 3, 4):
            with self.subTest(count=count):
                self.assertEqual(plural_pl(count, FORMS), 'opakowania')

    def test_five_and_above_take_the_many_form(self) -> None:
        for count in (5, 9, 11, 25, 100):
            with self.subTest(count=count):
                self.assertEqual(plural_pl(count, FORMS), 'opakowań')

    def test_teens_take_many_despite_ending_in_two_three_or_four(self) -> None:
        # The exception the whole rule turns on: 12/13/14 end in 2/3/4 but are
        # not "few" in Polish, while 22/23/24 are.
        for count in (12, 13, 14, 112, 213):
            with self.subTest(count=count):
                self.assertEqual(plural_pl(count, FORMS), 'opakowań')

    def test_twenty_two_and_up_resume_the_few_form(self) -> None:
        for count in (22, 23, 24, 104):
            with self.subTest(count=count):
                self.assertEqual(plural_pl(count, FORMS), 'opakowania')

    def test_zero_takes_the_many_form(self) -> None:
        self.assertEqual(plural_pl(0, FORMS), 'opakowań')

    def test_a_non_numeric_value_falls_back_rather_than_raising(self) -> None:
        # A template filter must not 500 a page over a typo in a variable name.
        self.assertEqual(plural_pl(None, FORMS), 'opakowań')
        self.assertEqual(plural_pl('abc', FORMS), 'opakowań')
