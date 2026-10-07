from freezegun import freeze_time

from odoo import Command
from odoo.tests import tagged

from .common import PlDashboardAnalyticMixin, PlDashboardArsCommon, PlDashboardCommon


class BudgetMixin:

    @classmethod
    def _setup_budget(cls, items):
        """items: [(account, "YYYY-MM-01", amount)], amount with the
        accounting sign (income budgets negative), as Odoo stores them."""
        cls.budget = cls.env["account.report.budget"].create({
            "name": "Budget 2026",
            "company_id": cls.company.id,
            "item_ids": [
                Command.create({"account_id": account.id, "date": date, "amount": amount})
                for account, date, amount in items
            ],
        })

    def _data(self, period="fiscal_year", **kwargs):
        """The budget is picked in the dashboard's toolbar."""
        kwargs.setdefault("budget_id", self.budget.id)
        return super()._data(period, **kwargs)

    def _detail(self, row_key, column_key, **kwargs):
        kwargs.setdefault("budget_id", self.budget.id)
        return self.Dashboard.get_cell_detail(row_key, column_key, **kwargs)


@tagged("post_install", "-at_install")
@freeze_time("2026-03-15")
class TestPlBudget(BudgetMixin, PlDashboardAnalyticMixin, PlDashboardCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_analytics()
        cls._setup_budget([
            (cls.account_salaries, "2026-01-01", 90.0),
            (cls.account_salaries, "2026-02-01", 250.0),
            (cls.account_commissions, "2026-02-01", 40.0),
            (cls.account_sales, "2026-02-01", -800.0),
            # Future month: left out, like the actuals.
            (cls.account_salaries, "2026-06-01", 999.0),
        ])
        cls._entry("2026-01-10", [(cls.account_salaries, 100.0, None)])
        cls._entry("2026-02-10", [
            (cls.account_salaries, 200.0, None),
            (cls.account_commissions, 50.0, None, {cls.unit_1: 100.0}),
            (cls.account_rent, 10.0, None),
            (cls.account_sales, -1000.0, cls.customer_a),
        ])

    def test_cost_leaf_budget_and_deviation(self):
        row = self._line_row(self._data(), self.leaf_salaries)
        self.assertEqual(row["budget"]["2026-01"], 90.0)
        self.assertAlmostEqual(row["deviation"]["2026-01"], 100.0 / 9.0)
        self.assertAlmostEqual(row["deviation"]["2026-02"], -20.0)
        self.assertEqual(row["budget"]["2026-03"], 0.0)
        self.assertIsNone(row["budget"]["2026-06"])
        self.assertEqual(row["budget"]["total"], 340.0)
        self.assertAlmostEqual(row["deviation"]["total"], (300.0 - 340.0) / 340.0 * 100.0)

    def test_zero_budget_is_not_available(self):
        row = self._line_row(self._data(), self.leaf_rent)
        self.assertEqual(row["budget"]["2026-02"], 0.0)
        self.assertIsNone(row["deviation"]["2026-02"])

    def test_groups_and_sections_add_up(self):
        data = self._data()
        self.assertEqual(self._line_row(data, self.group_staff)["budget"]["2026-02"], 250.0)
        direct = self._line_row(data, self.root_direct)
        self.assertEqual(direct["budget"]["2026-02"], 290.0)
        self.assertAlmostEqual(direct["deviation"]["2026-02"], (250.0 - 290.0) / 290.0 * 100.0)

    def test_sales_budget(self):
        # Income budgets are stored negative, like their balance.
        data = self._data()
        leaf = self._line_row(data, self.leaf_sales)
        self.assertEqual(leaf["budget"]["2026-02"], 800.0)
        self.assertAlmostEqual(leaf["deviation"]["2026-02"], 25.0)
        self.assertEqual(leaf["budget"]["total"], 800.0)
        sales = self._line_row(data, self.root_income)
        self.assertEqual(sales["budget"]["2026-02"], 800.0)
        self.assertAlmostEqual(sales["deviation"]["2026-02"], 25.0)

    def test_month_period(self):
        with freeze_time("2026-02-20"):
            data = self._data("month")
        row = self._line_row(data, self.leaf_salaries)
        self.assertEqual(list(row["budget"]), ["2026-02"])
        self.assertEqual(row["budget"]["2026-02"], 250.0)

    def test_budget_hidden(self):
        self.assertTrue(self._data()["budget_shown"])
        data = self._data(budget_id=None)
        self.assertFalse(data["budget_shown"])
        self.assertNotIn("budget", self._line_row(data, self.leaf_salaries))
        # By account only: not comparable with an analytic filter.
        data = self._data(analytic_ids=self.unit_1.ids)
        self.assertFalse(data["budget_shown"])
        self.assertTrue(data["budget_unavailable_reason"])
        # A budget of another company is ignored.
        other_budget = self.env["account.report.budget"].create({
            "name": "Other company", "company_id": self.company_data_2["company"].id,
        })
        self.assertFalse(self._data(budget_id=other_budget.id)["budget_shown"])
        config = self.Dashboard.get_dashboard_config()
        self.assertEqual([budget["id"] for budget in config["budgets"]], self.budget.ids)

    def test_detail_budgets_add_up(self):
        detail = self._detail("line-%d" % self.root_direct.id, "total")
        self.assertTrue(detail["budget_shown"])
        self.assertAlmostEqual(sum(entry["budget"] for entry in detail["entries"]), detail["total_budget"])
        self.assertEqual(detail["total_budget"], 380.0)
        # A budgeted account without movements is listed too.
        self.leaf_salaries.account_ids = [Command.link(self.account_social.id)]
        self.budget.item_ids = [Command.create({
            "account_id": self.account_social.id, "date": "2026-01-01", "amount": 15.0,
        })]
        detail = self._detail("line-%d" % self.leaf_salaries.id, "2026-01")
        entries = {entry["code"]: entry for entry in detail["entries"]}
        self.assertEqual(entries["5.1.2.01.020"]["amount"], 0.0)
        self.assertEqual(entries["5.1.2.01.020"]["budget"], 15.0)
        self.assertEqual(detail["total_budget"], 105.0)
        self.assertAlmostEqual(sum(entry["budget"] for entry in detail["entries"]), 105.0)

    def test_detail_sales_line_budget(self):
        # Budgets are by account, like the popup's rows.
        detail = self._detail("line-%d" % self.leaf_sales.id, "2026-02")
        self.assertEqual(detail["total_budget"], 800.0)
        self.assertAlmostEqual(detail["total_deviation"], 25.0)
        self.assertEqual([entry["budget"] for entry in detail["entries"]], [800.0])
        detail = self._detail("line-%d" % self.root_income.id, "2026-02")
        self.assertEqual(detail["total_budget"], 800.0)
        self.assertEqual([entry["budget"] for entry in detail["entries"]], [800.0])


@tagged("post_install", "-at_install")
@freeze_time("2026-03-15")
class TestPlBudgetSecondary(BudgetMixin, PlDashboardArsCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_budget([
            (cls.account_salaries, "2026-01-01", 100000.0),
            (cls.account_salaries, "2026-02-01", 200000.0),
            (cls.account_salaries, "2026-03-01", 300000.0),
        ])
        # Rates on the item dates (1st of the month) must not be used.
        cls._rate(cls.usd, "2026-01-01", 500.0)
        cls._rate(cls.usd, "2026-01-30", 1000.0)  # Friday; Jan 31 is a Saturday
        cls._rate(cls.usd, "2026-02-27", 1250.0)  # Friday; Feb 28 is a Saturday
        cls._rate(cls.usd, "2026-03-13", 1500.0)  # latest rate of the current month

    def test_each_month_at_its_last_day_rate(self):
        data = self._data(display_currency="secondary")
        budget = self._line_row(data, self.leaf_salaries)["budget"]
        self.assertAlmostEqual(budget["2026-01"], 100.0)
        self.assertAlmostEqual(budget["2026-02"], 160.0)
        self.assertAlmostEqual(budget["2026-03"], 200.0)
        self.assertAlmostEqual(budget["total"], 460.0)
        local = self._line_row(self._data(display_currency="company"), self.leaf_salaries)["budget"]
        self.assertEqual(local["total"], 600000.0)

    def test_deviation_includes_exchange_effect(self):
        # Spent exactly the budget in pesos, on a day with a different rate.
        self._rate(self.usd, "2026-02-10", 1000.0)
        self._entry("2026-02-10", [(self.account_salaries, 200000.0, None)])
        row = self._line_row(self._data(display_currency="secondary"), self.leaf_salaries)
        self.assertAlmostEqual(row["values"]["2026-02"], 200.0)
        self.assertAlmostEqual(row["deviation"]["2026-02"], 25.0)
        row = self._line_row(self._data(display_currency="company"), self.leaf_salaries)
        self.assertAlmostEqual(row["deviation"]["2026-02"], 0.0)
