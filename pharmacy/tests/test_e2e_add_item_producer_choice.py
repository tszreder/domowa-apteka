"""E2E for test-plan.md risk #1 (autocomplete picks the wrong box).

Django's `StaticLiveServerTestCase` + the Python `playwright` package is this
project's chosen e2e stack (test-plan.md §4 "Stack" and its "Stack grounding
tools" note — a TS/npx Playwright Test runner was considered and rejected
because it isn't the CI-reproducible host `manage.py test` already is).

`search_presentations` (registry/suggestions.py) groups rows into one
presentation per (name, strength, form) and lists every distinct manufacturer
as a producer. Two things about that only exist in the rendered page, not at
the integration-test layer test-plan.md recommends for the rest of risk #1:
the suggestion *label* names only the first (alphabetical) producer
(`product-search.js: presentationLabel`), and picking a *different* producer
from the dropdown is what actually changes `id_product`'s value
(`autocomplete.js`, the `producer-select` "change" listener). A regression
there — the dropdown rendering but silently not rewiring the hidden field —
would still submit the alphabetically-first producer's row: the exact
"confidently wrong identity" risk #1 describes, and no server-only test can
see it because the wiring lives in event-handler JavaScript.
"""

import os
from datetime import date

# Playwright's sync API leaves the main thread looking like it has a running
# asyncio loop, which trips Django's SynchronousOnlyOperation guard on every
# ORM call in this file even though nothing here is actually concurrent —
# must be set before any Django DB access happens.
os.environ.setdefault('DJANGO_ALLOW_ASYNC_UNSAFE', 'true')

from django.contrib.auth.models import User
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import Client, tag
from django.urls import reverse
from playwright.sync_api import Browser, Playwright, sync_playwright

from households.models import Household, Membership
from pharmacy.models import Item
from registry.models import Product, ProductSubstance, SourceField, Substance

AS_OF = date(2026, 8, 13)


@tag('e2e')
class ProducerChoiceSurvivesToSaveTests(StaticLiveServerTestCase):
    playwright: Playwright
    browser: Browser

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.browser.close()
        cls.playwright.stop()
        super().tearDownClass()

    def setUp(self) -> None:
        self.household = Household.objects.create(name='Kowalscy')
        self.member = User.objects.create_user(username='alice@example.com', password='pass12345')
        Membership.objects.create(user=self.member, household=self.household)

        # The `Sortis 20` salt-variant shape (registry/tests/test_suggestions.py),
        # one level up: two *producers* of the same presentation whose rows
        # disagree on substances, so picking the wrong one is not cosmetic.
        simvastatin = Substance.objects.create(name='Simwastatyna', name_key='simwastatyna')
        simvastatin_sodium = Substance.objects.create(
            name='Symwastatyna sodowa', name_key='symwastatyna_sodowa'
        )
        self.default_product = Product.objects.create(
            registry_id='1', name='Zocor 20', strength='20 mg',
            pharmaceutical_form='Tabletki', marketing_holder='Actavis',
            kind='ludzki', last_seen_as_of=AS_OF, is_active=True,
        )
        ProductSubstance.objects.create(
            product=self.default_product, substance=simvastatin,
            source_field=SourceField.SUBSTANCE_ROW, source_order=0,
        )
        self.other_producer_product = Product.objects.create(
            registry_id='2', name='Zocor 20', strength='20 mg',
            pharmaceutical_form='Tabletki', marketing_holder='Zentiva',
            kind='ludzki', last_seen_as_of=AS_OF, is_active=True,
        )
        ProductSubstance.objects.create(
            product=self.other_producer_product, substance=simvastatin_sodium,
            source_field=SourceField.SUBSTANCE_ROW, source_order=0,
        )

        # Authenticate without the UI (the login form is risk #5/#6's concern,
        # not this one): log in through the plain test client, then hand its
        # session cookie to the real browser context.
        api_client = Client()
        api_client.force_login(self.member)
        session_cookie = api_client.cookies['sessionid']

        self.context = self.browser.new_context()
        self.context.add_cookies([{
            'name': 'sessionid',
            'value': session_cookie.value,
            'url': self.live_server_url,
        }])
        self.page = self.context.new_page()

    def tearDown(self) -> None:
        self.context.close()

    def test_choosing_the_non_default_producer_saves_that_producers_product(self) -> None:
        self.page.goto(f'{self.live_server_url}{reverse("pharmacy:item_add")}')

        self.page.get_by_label('Nazwa leku').fill('Zocor')

        # Alphabetically-first producer is 'Actavis' (`_build_presentation`
        # sorts producers by holder), so the rendered option names it and
        # says nothing about 'Zentiva' existing — exactly the ambiguity
        # risk #1 is about.
        option = self.page.get_by_role('option', name='Zocor 20 — 20 mg — Tabletki')
        option.wait_for(state='visible')
        option.click()

        producer_select = self.page.get_by_label('Producent (opcjonalnie)')
        producer_select.wait_for(state='visible')
        producer_select.select_option(label='Zentiva')

        self.page.get_by_role('button', name='Dodaj').click()

        self.page.wait_for_url(f'{self.live_server_url}{reverse("pharmacy:item_list")}')

        item = Item.objects.get(household=self.household)
        self.assertEqual(item.product_id, self.other_producer_product.id)
        self.assertNotEqual(item.product_id, self.default_product.id)
        substance_names = [link.substance.name for link in item.product.substance_links.all()]
        self.assertEqual(substance_names, ['Symwastatyna sodowa'])
