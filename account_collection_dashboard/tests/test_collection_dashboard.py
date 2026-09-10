from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.addons.l10n_latam_check.tests.common import L10nLatamCheckTest
from odoo.exceptions import AccessError
from odoo.tests import tagged


@tagged("post_install", "-at_install")
class TestCollectionDashboard(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.dashboard = cls.env["account.collection.dashboard"]
        cls.date_from = "2024-01-01"
        cls.date_to = "2024-01-31"

    def test_invoiced_vs_collected(self):
        invoice = self._create_invoice_one_line(
            price_unit=1000.0,
            tax_ids=[],
            invoice_date="2024-01-15",
            post=True,
        )
        self.env["account.payment.register"].with_context(
            active_model="account.move", active_ids=invoice.ids
        ).create({"amount": 400.0}).action_create_payments()

        result = self.dashboard.get_invoiced_vs_collected(self.date_from, self.date_to)

        self.assertAlmostEqual(result["invoiced"], 1000.0)
        self.assertAlmostEqual(result["collected"], 400.0)
        self.assertAlmostEqual(result["percentage"], 40.0)

    def test_invoiced_vs_collected_nets_credit_notes(self):
        self._create_invoice_one_line(
            price_unit=1000.0, tax_ids=[], invoice_date="2024-01-10", post=True
        )
        self._create_invoice_one_line(
            move_type="out_refund", price_unit=300.0, tax_ids=[], invoice_date="2024-01-20", post=True
        )

        result = self.dashboard.get_invoiced_vs_collected(self.date_from, self.date_to)

        self.assertAlmostEqual(result["invoiced"], 700.0)

    def test_config_access_denied_for_dashboard_user(self):
        dashboard_user = self.env["res.users"].create({
            "name": "Collection Dashboard User",
            "login": "collection_dashboard_user",
            "group_ids": [(6, 0, [self.env.ref("account_collection_dashboard.group_collection_dashboard_user").id])],
        })
        with self.assertRaises(AccessError):
            self.env["account.collection.dashboard.config"].with_user(dashboard_user).search([])

    def test_get_config_recovers_from_concurrent_creation_race(self):
        """The dashboard's client action fires several RPC calls
        concurrently on first load, several of which may call _get_config()
        before any row exists yet for the company. Simulate the resulting
        create() race (one request's create() hits the unique constraint
        because another one just won it) and check it's recovered from
        instead of raising to the user.
        """
        Config = self.env["account.collection.dashboard.config"].sudo()
        existing = Config._get_config()
        original_search = type(Config).search
        call_count = {"n": 0}

        def fake_search(self, *args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return self.browse()
            return original_search(self, *args, **kwargs)

        with patch.object(type(Config), "search", fake_search):
            config = Config._get_config()

        self.assertEqual(config, existing)

    def test_currency_filter_separates_indicators(self):
        company_currency = self.env.company.currency_id
        foreign_currency = self.env["res.currency"].with_context(active_test=False).search(
            [("id", "!=", company_currency.id)], limit=1
        )
        foreign_currency.active = True

        self._create_invoice_one_line(
            price_unit=1000.0, tax_ids=[], invoice_date="2024-01-05", post=True
        )
        self._create_invoice_one_line(
            price_unit=500.0, tax_ids=[], currency_id=foreign_currency.id, invoice_date="2024-01-06", post=True
        )

        company_currency_result = self.dashboard.get_invoiced_vs_collected(
            self.date_from, self.date_to, currency_id=company_currency.id
        )
        foreign_currency_result = self.dashboard.get_invoiced_vs_collected(
            self.date_from, self.date_to, currency_id=foreign_currency.id
        )

        self.assertAlmostEqual(company_currency_result["invoiced"], 1000.0)
        self.assertAlmostEqual(foreign_currency_result["invoiced"], 500.0)

    def test_overdue_by_age_buckets(self):
        today = fields.Date.today()
        self._create_invoice_one_line(
            price_unit=100.0,
            tax_ids=[],
            invoice_date=today - timedelta(days=40),
            invoice_date_due=today - timedelta(days=10),
            invoice_payment_term_id=False,
            post=True,
        )
        self._create_invoice_one_line(
            price_unit=200.0,
            tax_ids=[],
            invoice_date=today - timedelta(days=130),
            invoice_date_due=today - timedelta(days=100),
            invoice_payment_term_id=False,
            post=True,
        )

        buckets = {bucket["label"]: bucket["amount"] for bucket in self.dashboard.get_overdue_by_age()}

        self.assertAlmostEqual(buckets["0-30 days"], 100.0)
        self.assertAlmostEqual(buckets["31-60 days"], 0.0)
        self.assertAlmostEqual(buckets["61-90 days"], 0.0)
        self.assertAlmostEqual(buckets["+90 days"], 200.0)

    def test_top_overdue_partners(self):
        today = fields.Date.today()
        self._create_invoice_one_line(
            price_unit=1000.0,
            tax_ids=[],
            partner_id=self.partner_a.id,
            invoice_date=today - timedelta(days=40),
            invoice_date_due=today - timedelta(days=10),
            invoice_payment_term_id=False,
            post=True,
        )
        self._create_invoice_one_line(
            price_unit=500.0,
            tax_ids=[],
            partner_id=self.partner_b.id,
            invoice_date=today - timedelta(days=40),
            invoice_date_due=today - timedelta(days=10),
            invoice_payment_term_id=False,
            post=True,
        )

        results = self.dashboard.get_top_overdue_partners()

        self.assertEqual(results[0]["partner_id"], self.partner_a.id)
        self.assertAlmostEqual(results[0]["amount"], 1000.0)
        self.assertEqual(results[1]["partner_id"], self.partner_b.id)
        self.assertAlmostEqual(results[1]["amount"], 500.0)

    def test_due_soon_by_followup_level(self):
        today = fields.Date.today()
        invoice = self._create_invoice_one_line(
            price_unit=1000.0,
            tax_ids=[],
            invoice_date=today,
            invoice_date_due=today + timedelta(days=5),
            invoice_payment_term_id=False,
            post=True,
        )
        followup_level = self.env["account_followup.followup.line"].create({
            "name": "Test pre-due reminder",
            "delay": -3,
            "company_id": self.env.company.id,
        })
        invoice.line_ids.filtered(lambda l: l.account_id.account_type == "asset_receivable").followup_line_id = followup_level

        results = self.dashboard.get_due_soon_by_followup_level()

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["level_id"], followup_level.id)
        self.assertAlmostEqual(results[0]["amount"], 1000.0)

    def test_pending_exchange_difference_detects_rate_change(self):
        today = fields.Date.today()
        company_currency = self.env.company.currency_id
        foreign_currency = self.env["res.currency"].with_context(active_test=False).search(
            [("id", "!=", company_currency.id)], limit=1
        )
        foreign_currency.active = True
        self.env["res.currency.rate"].create({
            "currency_id": foreign_currency.id,
            "rate": 2.0,
            "name": today - timedelta(days=30),
            "company_id": self.env.company.id,
        })
        invoice = self._create_invoice_one_line(
            price_unit=1000.0,
            tax_ids=[],
            currency_id=foreign_currency.id,
            invoice_date=today - timedelta(days=30),
            invoice_payment_term_id=False,
            post=True,
        )
        # Rate changes after the invoice was booked.
        self.env["res.currency.rate"].create({
            "currency_id": foreign_currency.id,
            "rate": 4.0,
            "name": today,
            "company_id": self.env.company.id,
        })

        result = self.dashboard.get_pending_exchange_difference()

        aml = invoice.line_ids.filtered(lambda l: l.account_id.account_type == "asset_receivable")
        expected_revalued = foreign_currency._convert(
            aml.amount_residual_currency, company_currency, self.env.company, today
        )
        expected_adjustment = expected_revalued - aml.amount_residual

        self.assertEqual(result["count"], 1)
        self.assertAlmostEqual(result["amount"], expected_adjustment)
        self.assertIn(invoice.id, result["drilldown"]["domain"][0][2])

    def test_pending_exchange_difference_ignores_unchanged_rate(self):
        today = fields.Date.today()
        company_currency = self.env.company.currency_id
        foreign_currency = self.env["res.currency"].with_context(active_test=False).search(
            [("id", "!=", company_currency.id)], limit=1
        )
        foreign_currency.active = True
        self.env["res.currency.rate"].create({
            "currency_id": foreign_currency.id,
            "rate": 3.0,
            "name": today - timedelta(days=30),
            "company_id": self.env.company.id,
        })
        invoice = self._create_invoice_one_line(
            price_unit=1000.0,
            tax_ids=[],
            currency_id=foreign_currency.id,
            invoice_date=today - timedelta(days=30),
            invoice_payment_term_id=False,
            post=True,
        )

        result = self.dashboard.get_pending_exchange_difference()

        affected_ids = result["drilldown"]["domain"][0][2]
        self.assertNotIn(invoice.id, affected_ids)


@tagged("post_install_l10n", "post_install", "-at_install")
class TestThirdPartyChecksIndicator(L10nLatamCheckTest):

    def _create_third_party_check(self):
        payment_method_line = self.third_party_check_journal._get_available_payment_method_lines(
            "inbound"
        ).filtered(lambda line: line.code == "new_third_party_checks")
        payment = self.env["account.payment"].create({
            "partner_id": self.partner_a.id,
            "payment_type": "inbound",
            "journal_id": self.third_party_check_journal.id,
            "l10n_latam_new_check_ids": [
                (0, 0, {"name": "00000001", "payment_date": fields.Date.today() + timedelta(days=30), "amount": 1}),
                (0, 0, {"name": "00000002", "payment_date": fields.Date.today() + timedelta(days=30), "amount": 1}),
            ],
            "payment_method_line_id": payment_method_line.id,
        })
        payment.action_post()
        return payment

    def test_third_party_checks_in_portfolio(self):
        company = self.company_data_3["company"]
        dashboard = self.env["account.collection.dashboard"].with_company(company)
        config = self.env["account.collection.dashboard.config"].sudo()._get_config(company)
        config.third_party_check_journal_ids = [(6, 0, self.third_party_check_journal.ids)]

        self._create_third_party_check()

        result = dashboard.get_third_party_checks_in_portfolio()

        self.assertEqual(len(result["by_currency"]), 1)
        self.assertEqual(result["by_currency"][0]["count"], 2)
        self.assertAlmostEqual(result["by_currency"][0]["amount"], 2.0)
        self.assertEqual(result["by_currency"][0]["overdue_count"], 0)
