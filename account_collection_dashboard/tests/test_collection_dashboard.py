from datetime import timedelta

from odoo import fields
from odoo.addons.account.tests.common import AccountTestInvoicingCommon
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
