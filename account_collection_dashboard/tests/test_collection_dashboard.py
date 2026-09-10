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

    def test_total_receivable_converts_to_selected_currency(self):
        """get_total_receivable must re-express company-currency residuals
        in the selected currency using today's rate, not filter invoices
        by matching currency like the other indicators do.
        """
        company_currency = self.env.company.currency_id
        foreign_currency = self.env["res.currency"].with_context(active_test=False).search(
            [("id", "!=", company_currency.id)], limit=1
        )
        foreign_currency.active = True
        self.env["res.currency.rate"].create({
            "currency_id": foreign_currency.id,
            "rate": 2.0,
            "name": fields.Date.today(),
            "company_id": self.env.company.id,
        })
        self._create_invoice_one_line(
            price_unit=1000.0,
            tax_ids=[],
            invoice_date=fields.Date.today(),
            invoice_payment_term_id=False,
            post=True,
        )

        company_currency_result = self.dashboard.get_total_receivable()
        foreign_currency_result = self.dashboard.get_total_receivable(currency_id=foreign_currency.id)

        self.assertAlmostEqual(company_currency_result["amount"], 1000.0)
        self.assertAlmostEqual(foreign_currency_result["amount"], 2000.0)

    def test_total_receivable_drilldown_opens_invoices_grouped_by_due_month(self):
        invoice = self._create_invoice_one_line(
            price_unit=1000.0, tax_ids=[], invoice_date=fields.Date.today(),
            invoice_payment_term_id=False, post=True,
        )

        result = self.dashboard.get_total_receivable()

        drilldown = result["drilldown"]
        self.assertEqual(drilldown["res_model"], "account.move")
        self.assertEqual(drilldown["domain"], [("id", "in", [invoice.id])])
        self.assertEqual(drilldown["views"][0][0], self.dashboard._invoice_list_view_id())
        self.assertEqual(drilldown["context"]["group_by"], ["invoice_date_due:month"])

    def test_total_receivable_restricted_to_sale_journals(self):
        other_journal = self.company_data["default_journal_sale"].copy({
            "name": "Other Sales Journal", "code": "OSJ",
        })
        config = self.env["account.collection.dashboard.config"].sudo()._get_config()
        config.sale_journal_ids = [(6, 0, self.company_data["default_journal_sale"].ids)]

        self._create_invoice_one_line(
            price_unit=1000.0,
            tax_ids=[],
            invoice_date=fields.Date.today(),
            invoice_payment_term_id=False,
            journal_id=self.company_data["default_journal_sale"].id,
            post=True,
        )
        self._create_invoice_one_line(
            price_unit=500.0,
            tax_ids=[],
            invoice_date=fields.Date.today(),
            invoice_payment_term_id=False,
            journal_id=other_journal.id,
            post=True,
        )

        result = self.dashboard.get_total_receivable()

        self.assertAlmostEqual(result["amount"], 1000.0)

    def test_turnover_period_bounds(self):
        company = self.env.company
        today = fields.Date.today()

        current_from, current_to = self.dashboard._get_turnover_period_bounds(
            "current_fiscal_year", company, today
        )
        previous_from, previous_to = self.dashboard._get_turnover_period_bounds(
            "previous_fiscal_year", company, today
        )
        last_12_months_from, last_12_months_to = self.dashboard._get_turnover_period_bounds(
            "last_12_months", company, today
        )

        self.assertEqual(current_to, company.compute_fiscalyear_dates(today)["date_to"])
        self.assertEqual(previous_to, current_from - timedelta(days=1))
        self.assertEqual(last_12_months_to, today)
        self.assertAlmostEqual((today - last_12_months_from).days, 365, delta=1)

    def test_collection_turnover_current_fiscal_year(self):
        self._create_invoice_one_line(
            price_unit=1000.0,
            tax_ids=[],
            invoice_date=fields.Date.today(),
            invoice_payment_term_id=False,
            post=True,
        )

        result = self.dashboard.get_collection_turnover(period="current_fiscal_year")

        # date_to is the fiscal year's end (which may be in the future), but
        # since no entries are dated after today, the AR balance "as of
        # fiscal year end" still equals the balance today [1000].
        # Average AR = (balance at fiscal year start [0] + balance today [1000]) / 2
        self.assertAlmostEqual(result["net_credit_sales"], 1000.0)
        self.assertAlmostEqual(result["average_receivable"], 500.0)
        self.assertAlmostEqual(result["turnover"], 2.0)

    def test_collection_turnover_average_ar_reflects_payment_from_other_journal(self):
        """Regression test: a payment's reconciling GL line lives in the
        payment's own journal (e.g. a bank journal), not the invoice's
        sales journal. The AR balance used for the turnover average must
        not be restricted by sale_journal_ids, or a paid invoice would
        look like it's still fully outstanding forever.
        """
        today = fields.Date.today()
        config = self.env["account.collection.dashboard.config"].sudo()._get_config()
        config.sale_journal_ids = [(6, 0, self.company_data["default_journal_sale"].ids)]

        invoice = self._create_invoice_one_line(
            price_unit=1000.0,
            tax_ids=[],
            invoice_date=today,
            invoice_payment_term_id=False,
            journal_id=self.company_data["default_journal_sale"].id,
            post=True,
        )
        self.env["account.payment.register"].with_context(
            active_model="account.move", active_ids=invoice.ids
        ).create({"amount": 1000.0, "payment_date": today}).action_create_payments()

        result = self.dashboard.get_collection_turnover(period="current_fiscal_year")

        self.assertAlmostEqual(result["average_receivable"], 0.0)

    def test_collection_payment_ratio(self):
        today = fields.Date.today()
        invoice = self._create_invoice_one_line(
            price_unit=1000.0,
            tax_ids=[],
            invoice_date=today,
            invoice_payment_term_id=False,
            post=True,
        )
        self.env["account.payment.register"].with_context(
            active_model="account.move", active_ids=invoice.ids
        ).create({"amount": 1000.0, "payment_date": today}).action_create_payments()

        bill = self._create_invoice_one_line(
            move_type="in_invoice",
            price_unit=400.0,
            tax_ids=[],
            invoice_date=today,
            invoice_payment_term_id=False,
            post=True,
        )
        self.env["account.payment.register"].with_context(
            active_model="account.move", active_ids=bill.ids
        ).create({"amount": 400.0, "payment_date": today}).action_create_payments()

        result = self.dashboard.get_collection_payment_ratio(today, today)

        self.assertAlmostEqual(result["collected"], 1000.0)
        self.assertAlmostEqual(result["paid"], 400.0)
        self.assertAlmostEqual(result["ratio"], 2.5)

    def test_collection_payment_ratio_restricted_to_sale_journals(self):
        """Regression test: account.payment.reconciled_invoice_ids has a
        custom search method that doesn't support dotted-path traversal
        into a related field (e.g. ".journal_id") — this crashed with
        "Unsupported operator" the first time this ran through the UI.
        """
        today = fields.Date.today()
        config = self.env["account.collection.dashboard.config"].sudo()._get_config()
        config.sale_journal_ids = [(6, 0, self.company_data["default_journal_sale"].ids)]

        invoice = self._create_invoice_one_line(
            price_unit=1000.0,
            tax_ids=[],
            invoice_date=today,
            invoice_payment_term_id=False,
            journal_id=self.company_data["default_journal_sale"].id,
            post=True,
        )
        self.env["account.payment.register"].with_context(
            active_model="account.move", active_ids=invoice.ids
        ).create({"amount": 1000.0, "payment_date": today}).action_create_payments()

        result = self.dashboard.get_collection_payment_ratio(today, today)

        self.assertAlmostEqual(result["collected"], 1000.0)

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

    def test_customers_with_debt_counts_distinct_partners(self):
        """A customer with several outstanding invoices counts once, but
        the drill-down still lists every one of their open invoices.
        """
        today = fields.Date.today()
        invoice_a1 = self._create_invoice_one_line(
            price_unit=1000.0, tax_ids=[], partner_id=self.partner_a.id,
            invoice_date=today, invoice_payment_term_id=False, post=True,
        )
        invoice_a2 = self._create_invoice_one_line(
            price_unit=500.0, tax_ids=[], partner_id=self.partner_a.id,
            invoice_date=today, invoice_payment_term_id=False, post=True,
        )
        invoice_b = self._create_invoice_one_line(
            price_unit=300.0, tax_ids=[], partner_id=self.partner_b.id,
            invoice_date=today, invoice_payment_term_id=False, post=True,
        )

        result = self.dashboard.get_customers_with_debt()

        self.assertEqual(result["count"], 2)
        drilldown_move_ids = result["drilldown"]["domain"][0][2]
        self.assertEqual(set(drilldown_move_ids), {invoice_a1.id, invoice_a2.id, invoice_b.id})
        self.assertEqual(
            result["drilldown"]["views"][0][0],
            self.dashboard._invoice_list_view_id(),
        )

    def test_undue_debt_includes_lines_without_followup_level(self):
        """Unlike "Due soon, by Follow-up level", this indicator sums every
        not-yet-due receivable, whether or not a level has been assigned.
        """
        today = fields.Date.today()
        not_due_invoice = self._create_invoice_one_line(
            price_unit=1000.0, tax_ids=[], invoice_date=today,
            invoice_date_due=today + timedelta(days=5),
            invoice_payment_term_id=False, post=True,
        )
        self._create_invoice_one_line(
            price_unit=500.0, tax_ids=[], invoice_date=today - timedelta(days=40),
            invoice_date_due=today - timedelta(days=10),
            invoice_payment_term_id=False, post=True,
        )

        result = self.dashboard.get_undue_debt()

        self.assertAlmostEqual(result["amount"], 1000.0)
        self.assertEqual(result["drilldown"]["domain"][0][2], [not_due_invoice.id])
        # confirms the line has no Follow-up level and is still counted here
        self.assertEqual(self.dashboard.get_due_soon_by_followup_level(), [])

    def test_due_today(self):
        today = fields.Date.today()
        due_today_invoice = self._create_invoice_one_line(
            price_unit=1000.0, tax_ids=[], invoice_date=today,
            invoice_date_due=today, invoice_payment_term_id=False, post=True,
        )
        self._create_invoice_one_line(
            price_unit=500.0, tax_ids=[], invoice_date=today,
            invoice_date_due=today + timedelta(days=1),
            invoice_payment_term_id=False, post=True,
        )
        self._create_invoice_one_line(
            price_unit=300.0, tax_ids=[], invoice_date=today - timedelta(days=10),
            invoice_date_due=today - timedelta(days=1),
            invoice_payment_term_id=False, post=True,
        )

        result = self.dashboard.get_due_today()

        self.assertAlmostEqual(result["amount"], 1000.0)
        self.assertEqual(result["drilldown"]["domain"][0][2], [due_today_invoice.id])

    def test_due_next_7_days_includes_due_today(self):
        today = fields.Date.today()
        due_today_invoice = self._create_invoice_one_line(
            price_unit=1000.0, tax_ids=[], invoice_date=today,
            invoice_date_due=today, invoice_payment_term_id=False, post=True,
        )
        due_in_5_days_invoice = self._create_invoice_one_line(
            price_unit=500.0, tax_ids=[], invoice_date=today,
            invoice_date_due=today + timedelta(days=5),
            invoice_payment_term_id=False, post=True,
        )
        self._create_invoice_one_line(
            price_unit=300.0, tax_ids=[], invoice_date=today,
            invoice_date_due=today + timedelta(days=10),
            invoice_payment_term_id=False, post=True,
        )
        self._create_invoice_one_line(
            price_unit=200.0, tax_ids=[], invoice_date=today - timedelta(days=10),
            invoice_date_due=today - timedelta(days=1),
            invoice_payment_term_id=False, post=True,
        )

        result = self.dashboard.get_due_next_7_days()

        self.assertAlmostEqual(result["amount"], 1500.0)
        self.assertEqual(
            set(result["drilldown"]["domain"][0][2]),
            {due_today_invoice.id, due_in_5_days_invoice.id},
        )

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

    def test_rejected_checks(self):
        """Odoo has no 'rejected' state for third-party checks (confirmed:
        it's purely a matter of which journal the check currently sits
        in). Simulate that convention: move a check into the journal
        configured as 'rejected' and check it shows up.
        """
        company = self.company_data_3["company"]
        dashboard = self.env["account.collection.dashboard"].with_company(company)
        config = self.env["account.collection.dashboard.config"].sudo()._get_config(company)
        config.rejected_check_journal_ids = [(6, 0, self.rejected_check_journal.ids)]

        payment = self._create_third_party_check()
        check = payment.l10n_latam_new_check_ids[0]

        # Same mechanism used by l10n_latam_check's own test suite to
        # simulate a check ending up in the rejected-checks journal:
        # a mass-transfer between journals, not a fresh "receive".
        self.env["l10n_latam.payment.mass.transfer"].with_context(
            active_model="l10n_latam.check", active_ids=[check.id]
        ).create({"destination_journal_id": self.rejected_check_journal.id})._create_payments()

        result = dashboard.get_rejected_checks()

        self.assertEqual(result["count"], 1)
        self.assertAlmostEqual(result["amount"], 1.0)
