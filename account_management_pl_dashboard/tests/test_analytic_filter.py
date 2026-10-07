from freezegun import freeze_time

from odoo import Command
from odoo.tests import tagged

from .common import PlDashboardAnalyticMixin, PlDashboardArsCommon, PlDashboardCommon


@tagged("post_install", "-at_install")
@freeze_time("2026-03-15")
class TestPlAnalyticFilter(PlDashboardAnalyticMixin, PlDashboardCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_analytics()

    def test_toolbar_filter_restricts_every_section(self):
        self._entry("2026-02-10", [
            (self.account_salaries, 100.0, None, {self.unit_1: 100.0}),
            (self.account_rent, 50.0, None, {self.unit_2: 100.0}),
            (self.account_commissions, 80.0, None, {self.unit_1: 25.0, self.unit_2: 75.0}),
            (self.account_salaries, 30.0, None),
            (self.account_sales, -1000.0, self.customer_a_contact, {self.unit_1: 40.0, self.unit_2: 60.0}),
        ])
        data = self._data(analytic_ids=self.unit_1.ids)
        self.assertEqual(data["analytic_ids"], self.unit_1.ids)
        self.assertAlmostEqual(self._line_row(data, self.leaf_salaries)["values"]["2026-02"], 100.0)
        self.assertAlmostEqual(self._line_row(data, self.leaf_commissions)["values"]["2026-02"], 20.0)
        self.assertAlmostEqual(self._line_row(data, self.leaf_rent)["values"]["2026-02"], 0.0)
        # Only unit 1's share of the Sales line's accounts.
        self.assertAlmostEqual(self._line_row(data, self.leaf_sales)["values"]["2026-02"], 400.0)
        self.assertAlmostEqual(self._row(data, "net_profit")["values"]["2026-02"], 280.0)
        # Without the filter, everything counts.
        data = self._data()
        self.assertAlmostEqual(self._line_row(data, self.leaf_salaries)["values"]["2026-02"], 130.0)
        self.assertAlmostEqual(self._line_row(data, self.leaf_sales)["values"]["2026-02"], 1000.0)

    def test_filter_respects_state_and_excluded_journals(self):
        closing_journal = self.env["account.journal"].create({
            "name": "Closing", "code": "CLS", "type": "general", "company_id": self.company.id,
        })
        self.structure.excluded_journal_ids = [Command.set(closing_journal.ids)]
        self._entry("2026-02-10", [(self.account_sales, -100.0, None, {self.unit_1: 100.0})])
        self._entry("2026-02-11", [(self.account_sales, -20.0, None, {self.unit_1: 100.0})], post=False)
        self._entry("2026-02-28", [(self.account_sales, 30.0, None, {self.unit_1: 100.0})], journal=closing_journal)
        data = self._data(analytic_ids=self.unit_1.ids)
        self.assertAlmostEqual(self._line_row(data, self.leaf_sales)["values"]["2026-02"], 100.0)

    def test_unassigned_accounts_with_filter(self):
        self._entry("2026-02-10", [(self.account_social, 40.0, None, {self.unit_1: 50.0, self.unit_2: 50.0})])
        data = self._data(analytic_ids=self.unit_1.ids)
        self.assertAlmostEqual(self._row(data, "unassigned")["values"]["2026-02"], -20.0)

    def test_project_mode_uses_project_plan(self):
        project_plan, _other_plans = self.env["account.analytic.plan"]._get_all_plans()
        project = self.env["account.analytic.account"].create({
            "name": "Project X", "plan_id": project_plan.id, "company_id": self.company.id,
        })
        self.structure.analytic_mode = "project"
        self._entry("2026-02-10", [(self.account_sales, -250.0, None, {project: 100.0})])
        self.assertAlmostEqual(
            self._line_row(self._data(analytic_ids=project.ids), self.leaf_sales)["values"]["2026-02"], 250.0,
        )
        options = self.Dashboard.get_dashboard_config()["analytic_filter_options"]
        self.assertIn(project.id, [option["id"] for option in options])

    def test_toolbar_filter_ignored_when_analytics_not_used(self):
        self._entry("2026-02-10", [(self.account_salaries, 100.0, None, {self.unit_2: 100.0})])
        self.structure.analytic_mode = "none"
        data = self._data(analytic_ids=self.unit_1.ids)
        self.assertEqual(data["analytic_ids"], [])
        self.assertEqual(self.Dashboard.get_dashboard_config()["analytic_filter_options"], [])
        self.assertAlmostEqual(self._line_row(data, self.leaf_salaries)["values"]["2026-02"], 100.0)


@tagged("post_install", "-at_install")
@freeze_time("2026-03-15")
class TestPlAnalyticFilterSecondary(PlDashboardAnalyticMixin, PlDashboardArsCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_analytics()

    def test_share_of_usd_invoice_keeps_original_amount(self):
        rate = self._rate(self.usd, "2026-02-10", 1000.0)
        self._invoice("2026-02-10", 1000.0, self.usd, self.customer_a, distribution={self.unit_1: 60.0, self.unit_2: 40.0})
        rate.rate = 1.0 / 1500.0
        data = self._data(display_currency="secondary", analytic_ids=self.unit_1.ids)
        self.assertAlmostEqual(self._line_row(data, self.leaf_sales)["values"]["2026-02"], 600.0)
        local = self._data(display_currency="company", analytic_ids=self.unit_1.ids)
        self.assertAlmostEqual(self._line_row(local, self.leaf_sales)["values"]["2026-02"], 600000.0)

    def test_share_of_peso_item_converted_at_its_date(self):
        self._rate(self.usd, "2026-02-10", 1000.0)
        self._entry("2026-02-10", [(self.account_sales, -10000.0, None, {self.unit_1: 100.0})])
        data = self._data(display_currency="secondary", analytic_ids=self.unit_1.ids)
        self.assertAlmostEqual(self._line_row(data, self.leaf_sales)["values"]["2026-02"], 10.0)

    def test_third_currency_share_in_secondary(self):
        self._rate(self.usd, "2026-02-10", 1000.0)
        self._entry("2026-02-10", [
            (self.account_salaries, 15000.0, None, self.eur, 10.0, {self.unit_1: 50.0, self.unit_2: 50.0}),
        ])
        data = self._data(display_currency="secondary", analytic_ids=self.unit_1.ids)
        # Half of 15000 ARS converted at 1000.
        self.assertAlmostEqual(self._line_row(data, self.leaf_salaries)["values"]["2026-02"], 7.5)
