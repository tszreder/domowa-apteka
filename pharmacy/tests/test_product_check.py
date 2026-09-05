"""The check screen's four load-bearing claims, asserted through HTTP.

It answers correctly, it refuses rather than guessing, it writes nothing, and
its query count does not grow with the size of the household. Phase 3 adds the
JavaScript that reaches this screen from the search box; nothing here depends
on it, because the screen is fully driveable by `?product=` — which is why this
file, and not an e2e layer this project does not have, carries the slice's
coverage.

Copy is asserted through the module constants below rather than inline string
literals: several assertions turn on one message being present *and* another
absent, and that pairing is unreadable when both are 90-character Polish
sentences repeated at each call site.
"""

import re
from datetime import date
from pathlib import Path

from django.contrib.auth.models import User
from django.db import connection
from django.http.response import HttpResponseBase
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from households.models import Household, Membership
from pharmacy.models import Item
from registry.models import Product, ProductSubstance, SourceField, Substance

AS_OF = date(2026, 8, 13)

# `SAME_PRODUCT_LABEL` is the invariant tail of a sentence that carries an
# inflected count ("Masz juz 2 opakowania tego samego leku"), so the whole
# sentence cannot be one constant. Tests that care about the count assert it
# separately.
SAME_PRODUCT_LABEL = 'tego samego leku'
SAME_SUBSTANCES_LABEL = 'Masz już lek z tą samą substancją czynną'
SHARED_SUBSTANCE_LABEL = 'Masz już lek, który ma przynajmniej jedną wspólną substancję czynną'
NO_MATCH = 'Nie masz tego leku ani zamienników w domu.'
TOTAL_REFUSAL = 'nie można go porównać z lekami w domu'
PARTIAL_REFUSAL = 'nie sprawdziliśmy, czy w domu są jego zamienniki'
COMPARISON_BASIS = 'Porównano według substancji czynnych'
INVALID_PRODUCT = 'Ten produkt nie jest już dostępny w rejestrze.'

TEMPLATE_PATH = Path(__file__).resolve().parent.parent / 'templates' / 'pharmacy' / 'product_check.html'


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


def link(product: Product, substance: Substance, order: int = 0) -> ProductSubstance:
    return ProductSubstance.objects.create(
        product=product,
        substance=substance,
        source_field=SourceField.SUBSTANCE_ROW,
        source_order=order,
    )


class ProductCheckAccessTests(TestCase):
    def setUp(self) -> None:
        self.household_a = Household.objects.create(name='Kowalscy')
        self.household_b = Household.objects.create(name='Nowakowie')
        self.member_a = User.objects.create_user(username='alice@example.com', password='pass12345')
        self.member_b = User.objects.create_user(username='bob@example.com', password='pass12345')
        Membership.objects.create(user=self.member_a, household=self.household_a)
        Membership.objects.create(user=self.member_b, household=self.household_b)

        self.para = Substance.objects.create(name='Paracetamol', name_key='paracetamol')
        self.candidate = make_product('1', name='Apap')
        link(self.candidate, self.para)
        Item.objects.create(household=self.household_a, product=self.candidate)

    def test_anonymous_request_redirects_to_login(self) -> None:
        response = self.client.get(reverse('pharmacy:product_check'))

        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.headers['Location'])

    def test_member_of_another_household_never_sees_this_households_items(self) -> None:
        # Household A holds the candidate itself. Household B's member asking
        # the same question must get the empty answer, not A's box.
        self.client.force_login(self.member_b)

        response = self.client.get(
            reverse('pharmacy:product_check'), {'product': self.candidate.pk}
        )

        self.assertContains(response, NO_MATCH)
        self.assertNotContains(response, SAME_PRODUCT_LABEL)

    def test_member_of_the_owning_household_sees_the_match(self) -> None:
        self.client.force_login(self.member_a)

        response = self.client.get(
            reverse('pharmacy:product_check'), {'product': self.candidate.pk}
        )

        self.assertContains(response, SAME_PRODUCT_LABEL)


class ProductCheckResultStateTests(TestCase):
    def setUp(self) -> None:
        self.household = Household.objects.create(name='Kowalscy')
        self.member = User.objects.create_user(username='alice@example.com', password='pass12345')
        Membership.objects.create(user=self.member, household=self.household)
        self.client.force_login(self.member)

        self.para = Substance.objects.create(name='Paracetamol', name_key='paracetamol')
        self.pseudo = Substance.objects.create(name='Pseudoefedryna', name_key='pseudoefedryna')

    def _check(self, candidate: Product) -> HttpResponseBase:
        return self.client.get(reverse('pharmacy:product_check'), {'product': candidate.pk})

    def test_no_product_parameter_renders_the_search_screen_only(self) -> None:
        response = self.client.get(reverse('pharmacy:product_check'))

        self.assertContains(response, 'Sprawdź lek')
        self.assertContains(response, 'Sprawdzenie niczego nie dodaje do listy leków.')
        # Nothing was asked, so nothing may be answered — including a refusal.
        self.assertNotContains(response, NO_MATCH)
        self.assertNotContains(response, TOTAL_REFUSAL)

    def test_empty_product_parameter_renders_the_search_screen_not_a_required_field_error(self) -> None:
        # `?product=` is present but empty — a stray `&` from a template, not
        # a submitted id. It must fall through the same path as no parameter
        # at all, not bind the form and surface Django's generic required
        # error.
        response = self.client.get(reverse('pharmacy:product_check'), {'product': ''})

        self.assertContains(response, 'Sprawdź lek')
        self.assertIsNone(response.context['form'])
        self.assertNotContains(response, 'To pole jest wymagane.')

    def test_household_holding_the_same_product_gets_the_same_product_label(self) -> None:
        candidate = make_product('1', name='Apap', strength='500 mg')
        link(candidate, self.para)
        Item.objects.create(household=self.household, product=candidate)
        Item.objects.create(household=self.household, product=candidate)

        response = self._check(candidate)

        # The count lives inside the sentence, correctly inflected: Polish takes
        # "opakowania" for 2, not the "opakowań" a two-form pluralize would give.
        self.assertContains(response, 'Masz już 2 opakowania tego samego leku')
        self.assertNotContains(response, NO_MATCH)

    def test_same_product_row_repeats_neither_the_name_nor_a_separate_pack_count(self) -> None:
        # A name absent from the search box's placeholder ("np. Apap, Xanax,
        # Concor..."), so the occurrence count below measures the heading and
        # the row rather than boilerplate.
        candidate = make_product('1', name='Ibuprom Max', strength='400 mg')
        link(candidate, self.para)
        Item.objects.create(household=self.household, product=candidate)

        response = self._check(candidate)

        # The heading above the row already names the product, and the sentence
        # already carries the count, so the row adds neither back.
        self.assertNotContains(response, 'Liczba opakowań:')
        self.assertContains(response, 'Ibuprom Max', count=2)

    def test_comparison_basis_is_dropped_when_identity_is_the_whole_answer(self) -> None:
        candidate = make_product('1', name='Apap')
        link(candidate, self.para)
        Item.objects.create(household=self.household, product=candidate)

        response = self._check(candidate)

        # Nothing was decided by substances here, so a line explaining which
        # substances were compared would describe a comparison that never ran.
        self.assertNotContains(response, COMPARISON_BASIS)

    def test_comparison_basis_is_kept_when_a_substance_match_needs_explaining(self) -> None:
        candidate = make_product('1', name='Apap')
        link(candidate, self.para)
        substitute = make_product('2', name='Paracetamol Hasco')
        link(substitute, self.para)
        Item.objects.create(household=self.household, product=candidate)
        Item.objects.create(household=self.household, product=substitute)

        response = self._check(candidate)

        # Same product *and* a substitute: the substitute row is the one the
        # line explains, so dropping it would remove the mitigation entirely.
        self.assertContains(response, SAME_PRODUCT_LABEL)
        self.assertContains(response, SAME_SUBSTANCES_LABEL)
        self.assertContains(response, COMPARISON_BASIS)

    def test_household_holding_a_substitute_gets_the_same_substances_label(self) -> None:
        candidate = make_product('1', name='Apap')
        link(candidate, self.para)
        substitute = make_product('2', name='Paracetamol Hasco')
        link(substitute, self.para)
        Item.objects.create(household=self.household, product=substitute)

        response = self._check(candidate)

        self.assertContains(response, SAME_SUBSTANCES_LABEL)
        self.assertContains(response, 'Paracetamol Hasco')
        self.assertNotContains(response, SAME_PRODUCT_LABEL)

    def test_partial_overlap_gets_the_shared_label_and_names_the_shared_substance(self) -> None:
        candidate = make_product('1', name='Combo')
        link(candidate, self.para, order=0)
        link(candidate, self.pseudo, order=1)
        para_only = make_product('2', name='Apap')
        link(para_only, self.para)
        Item.objects.create(household=self.household, product=para_only)

        response = self._check(candidate)

        self.assertContains(response, SHARED_SUBSTANCE_LABEL)
        self.assertContains(response, 'Wspólne substancje: Paracetamol')
        # The comparison names what it ran on, so presentation-level picking is
        # visible rather than implicit.
        self.assertContains(
            response, 'Porównano według substancji czynnych: Paracetamol, Pseudoefedryna.'
        )

    def test_resolved_candidate_with_nothing_related_states_no_match(self) -> None:
        ibu = Substance.objects.create(name='Ibuprofen', name_key='ibuprofen')
        candidate = make_product('1', name='Apap')
        link(candidate, self.para)
        unrelated = make_product('2', name='Ibuprom')
        link(unrelated, ibu)
        Item.objects.create(household=self.household, product=unrelated)

        response = self._check(candidate)

        self.assertContains(response, NO_MATCH)
        self.assertNotContains(response, TOTAL_REFUSAL)


class ProductCheckRefusalTests(TestCase):
    """The two refusal shapes, and the line that separates each from a verdict.

    Both directions matter. Reporting "nothing at home matches" for a product we
    failed to resolve reads as a buy signal; refusing outright for one the
    household demonstrably holds throws away an answer that never needed
    substances, because identity comes from primary keys.
    """

    def setUp(self) -> None:
        self.household = Household.objects.create(name='Kowalscy')
        self.member = User.objects.create_user(username='alice@example.com', password='pass12345')
        Membership.objects.create(user=self.member, household=self.household)
        self.client.force_login(self.member)

    def test_total_refusal_when_the_household_does_not_hold_the_unresolved_candidate(self) -> None:
        para = Substance.objects.create(name='Paracetamol', name_key='paracetamol')
        held = make_product('1', name='Apap')
        link(held, para)
        Item.objects.create(household=self.household, product=held)
        candidate = make_product('2', name='Peditrace')

        response = self.client.get(
            reverse('pharmacy:product_check'), {'product': candidate.pk}
        )

        self.assertContains(response, TOTAL_REFUSAL)
        # The assertion that separates "we could not tell" from "there is nothing".
        self.assertNotContains(response, NO_MATCH)
        self.assertNotContains(response, PARTIAL_REFUSAL)

    def test_partial_refusal_when_the_household_does_hold_the_unresolved_candidate(self) -> None:
        candidate = make_product('1', name='Peditrace')
        Item.objects.create(household=self.household, product=candidate)
        Item.objects.create(household=self.household, product=candidate)

        response = self.client.get(
            reverse('pharmacy:product_check'), {'product': candidate.pk}
        )

        # The confirmation, in full, comes first.
        self.assertContains(response, 'Masz już 2 opakowania tego samego leku')
        # Then the limitation qualifying it — and never the total refusal, which
        # would deny an answer the screen just gave.
        self.assertContains(response, PARTIAL_REFUSAL)
        self.assertNotContains(response, TOTAL_REFUSAL)
        self.assertNotContains(response, NO_MATCH)


class ProductCheckUncomparableSuppressionTests(TestCase):
    """The screen never reports how much of the household it could not compare.

    `CandidateCheck.uncomparable_count` still counts household boxes whose own
    substances never resolved — `test_duplicates.py` pins that — but the screen
    stopped rendering it on 2026-08-30 as clutter, at the user's direction.

    The cost is stated here rather than left implicit: a "nothing at home
    matches" verdict is now shown over a household the comparison only partly
    saw, with nothing on screen saying so. These tests exist so that removal
    stays a decision someone made, not something a later edit reintroduces or
    drops by accident.
    """

    def setUp(self) -> None:
        self.household = Household.objects.create(name='Kowalscy')
        self.member = User.objects.create_user(username='alice@example.com', password='pass12345')
        Membership.objects.create(user=self.member, household=self.household)
        self.client.force_login(self.member)
        # One box the comparison can never see, in both tests below.
        Item.objects.create(
            household=self.household, product=make_product('9', name='Peditrace')
        )

    def test_not_disclosed_beside_a_no_match_statement(self) -> None:
        para = Substance.objects.create(name='Paracetamol', name_key='paracetamol')
        candidate = make_product('1', name='Apap')
        link(candidate, para)

        response = self.client.get(
            reverse('pharmacy:product_check'), {'product': candidate.pk}
        )

        self.assertEqual(response.context['check'].uncomparable_count, 1)
        self.assertContains(response, NO_MATCH)

    def test_not_disclosed_when_the_candidate_itself_did_not_resolve(self) -> None:
        candidate = make_product('1', name='Nutriflex')

        response = self.client.get(
            reverse('pharmacy:product_check'), {'product': candidate.pk}
        )

        self.assertEqual(response.context['check'].uncomparable_count, 1)
        self.assertContains(response, TOTAL_REFUSAL)

    def test_uncomparable_count_is_not_wired_into_an_active_template_tag(self) -> None:
        """Pins the removal decision itself, independent of any fixture or wording.

        `{% comment %}` blocks never reach rendered output, so an
        `assertNotContains` against the HTTP response cannot tell a suppressed
        disclosure from one reintroduced with different copy. Reading the
        template source — with comment blocks stripped — is what actually pins
        "this field is not wired into a live tag".
        """
        source = TEMPLATE_PATH.read_text(encoding='utf-8')
        live_source = re.sub(r'{%-?\s*comment\s*-?%}.*?{%-?\s*endcomment\s*-?%}', '', source, flags=re.DOTALL)

        self.assertNotIn('uncomparable_count', live_source)


class ProductCheckWritesNothingTests(TestCase):
    def setUp(self) -> None:
        self.household = Household.objects.create(name='Kowalscy')
        self.member = User.objects.create_user(username='alice@example.com', password='pass12345')
        Membership.objects.create(user=self.member, household=self.household)
        self.client.force_login(self.member)

    def test_item_count_is_unchanged_across_a_check_that_produces_matches(self) -> None:
        para = Substance.objects.create(name='Paracetamol', name_key='paracetamol')
        candidate = make_product('1', name='Apap')
        link(candidate, para)
        substitute = make_product('2', name='Paracetamol Hasco')
        link(substitute, para)
        Item.objects.create(household=self.household, product=substitute)
        before = Item.objects.count()

        response = self.client.get(
            reverse('pharmacy:product_check'), {'product': candidate.pk}
        )

        self.assertContains(response, SAME_SUBSTANCES_LABEL)
        self.assertEqual(Item.objects.count(), before)

    def test_post_is_refused(self) -> None:
        # `require_GET` is what makes the screen's standing line enforceable
        # rather than a convention someone can quietly break later.
        response = self.client.post(reverse('pharmacy:product_check'))

        self.assertEqual(response.status_code, 405)


class ProductCheckInvalidProductTests(TestCase):
    """A stale `?product=` is a sentence, not an error page."""

    def setUp(self) -> None:
        self.household = Household.objects.create(name='Kowalscy')
        self.member = User.objects.create_user(username='alice@example.com', password='pass12345')
        Membership.objects.create(user=self.member, household=self.household)
        self.client.force_login(self.member)

    def test_non_numeric_id_renders_the_message_with_status_200(self) -> None:
        response = self.client.get(reverse('pharmacy:product_check'), {'product': 'abc'})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, INVALID_PRODUCT)

    def test_id_absent_from_the_registry_renders_the_message_with_status_200(self) -> None:
        response = self.client.get(reverse('pharmacy:product_check'), {'product': 999999})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, INVALID_PRODUCT)

    def test_inactive_product_renders_the_message_with_status_200(self) -> None:
        # F-01's loader deactivates rather than deletes, so this is the shape a
        # bookmark from before the last import actually takes.
        withdrawn = make_product('1', name='Wycofany', is_active=False)

        response = self.client.get(
            reverse('pharmacy:product_check'), {'product': withdrawn.pk}
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, INVALID_PRODUCT)
        self.assertNotContains(response, NO_MATCH)


class ProductCheckQueryShapeTests(TestCase):
    """The N+1 guard, pinned the way `test_item_list.py:124-129` pins the list's.

    The claim under test is that the count does not move with household size —
    asserted by running the same check against 2 items and against 12 and
    demanding the same number, so a regression to a per-item query fails CI
    rather than being noticed in production.
    """

    def setUp(self) -> None:
        self.household = Household.objects.create(name='Kowalscy')
        self.member = User.objects.create_user(username='alice@example.com', password='pass12345')
        Membership.objects.create(user=self.member, household=self.household)
        self.client.force_login(self.member)
        self.para = Substance.objects.create(name='Paracetamol', name_key='paracetamol')
        self.candidate = make_product('candidate', name='Apap')
        link(self.candidate, self.para)

    def _fill(self, count: int, start: int) -> None:
        """Add `count` resolved items, each its own product.

        `start` offsets `registry_id`, which is unique: the second fill in the
        test below extends the same household rather than replacing it, so
        reusing ids from the first would raise IntegrityError instead of
        measuring anything.
        """
        for i in range(start, start + count):
            product = make_product(str(i), name=f'Produkt {i}')
            link(product, self.para)
            Item.objects.create(household=self.household, product=product)

    def _measure(self) -> int:
        """Actually count the queries, rather than assert a constant twice.

        `assertNumQueries` would make both halves of the comparison below a
        hardcoded literal, and the test would pass without ever observing the
        household size. This returns what the request really cost.
        """
        with CaptureQueriesContext(connection) as captured:
            response = self.client.get(
                reverse('pharmacy:product_check'), {'product': self.candidate.pk}
            )
        self.assertEqual(response.status_code, 200)
        return len(captured)

    def test_query_count_does_not_grow_with_household_size(self) -> None:
        self._fill(2, start=0)
        small = self._measure()

        self._fill(10, start=2)
        large = self._measure()

        # The N+1 guard: two items or twelve, the request costs the same.
        self.assertEqual(small, large)
        # 4 queries are request plumbing (session, user, membership, household)
        # that run regardless of household size. The other 6 are data: 3 for the
        # candidate (row + substance_links + substances, prefetched by the
        # form's own queryset, since ModelChoiceField is what issues the lookup)
        # and 3 for the household (items+product via select_related, then
        # substance_links, then substances).
        self.assertEqual(small, 10)


class ScriptOrderTests(TestCase):
    """Both screens must load the shared module before their own script.

    The only Phase 3 failure this project's test stack can observe. There is no
    JS toolchain and no e2e layer, so nothing here proves the picker *works* —
    what it does prove is that the two tags are present and correctly ordered.
    Deferred scripts execute in document order, so a reversed pair leaves
    `window.ProductSearch` undefined and the screen script throws on load, in
    the browser, with nothing failing in CI.
    """

    def setUp(self) -> None:
        self.household = Household.objects.create(name='Kowalscy')
        self.member = User.objects.create_user(username='alice@example.com', password='pass12345')
        Membership.objects.create(user=self.member, household=self.household)
        self.client.force_login(self.member)

    def _assert_module_precedes(self, url: str, screen_script: str) -> None:
        body = self.client.get(url).content.decode()
        module_at = body.find('pharmacy/js/product-search.js')
        screen_at = body.find(screen_script)
        self.assertNotEqual(module_at, -1, 'product-search.js is not loaded')
        self.assertNotEqual(screen_at, -1, f'{screen_script} is not loaded')
        self.assertLess(module_at, screen_at)

    def test_check_screen_loads_the_module_before_check_js(self) -> None:
        self._assert_module_precedes(
            reverse('pharmacy:product_check'), 'pharmacy/js/check.js'
        )

    def test_add_screen_loads_the_module_before_autocomplete_js(self) -> None:
        self._assert_module_precedes(
            reverse('pharmacy:item_add'), 'pharmacy/js/autocomplete.js'
        )

    def test_check_screen_hands_its_result_url_to_the_search_input(self) -> None:
        # check.js reads the route off the input rather than rebuilding "/check/"
        # in JavaScript, so this attribute is what keeps one definition of it.
        response = self.client.get(reverse('pharmacy:product_check'))

        self.assertContains(
            response, f'data-result-url="{reverse("pharmacy:product_check")}"'
        )
