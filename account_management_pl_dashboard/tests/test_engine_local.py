from freezegun import freeze_time

from odoo import Command
from odoo.exceptions import AccessError
from odoo.tests import tagged

from .common import PlDashboardCommon


@tagged("post_install", "-at_install")
@freeze_time("2026-03-15")
class TestPlEngineLocal(PlDashboardCommon):

    def test_only_posted_entries_outside_excluded_journals(self):
        closing_journal = self.env["account.journal"].create({
            "name": "Closing", "code": "CLS", "type": "general", "company_id": self.company.id,
        })
        self.structure.excluded_journal_ids = [Command.set(closing_journal.ids)]
        self._entry("2026-01-10", [(self.account_salaries, 100.0, None)])
        self._entry("2026-01-11", [(self.account_salaries, 50.0, None)], post=False)
        self._entry("2026-01-31", [(self.account_salaries, 30.0, None)], journal=closing_journal)
        row = self._line_row(self._data(), self.leaf_salaries)
        self.assertAlmostEqual(row["values"]["2026-01"], 100.0)

    def test_month_grouping_groups_and_sections(self):
        self._entry("2026-01-10", [(self.account_salaries, 100.0, None)])
        self._entry("2026-02-10", [(self.account_salaries, 200.0, None), (self.account_commissions, 50.0, None)])
        self._entry("2026-03-01", [(self.account_rent, 10.0, None)])
        # A credit on a cost account (e.g. a refund) reduces the cost.
        self._entry("2026-03-02", [(self.account_rent, -4.0, None)])
        data = self._data()

        self.assertEqual([column["key"] for column in data["columns"]], [
            "2026-%02d" % month for month in range(1, 13)
        ] + ["total"])
        salaries = self._line_row(data, self.leaf_salaries)["values"]
        self.assertEqual((salaries["2026-01"], salaries["2026-02"], salaries["total"]), (100.0, 200.0, 300.0))
        staff = self._line_row(data, self.group_staff)["values"]
        self.assertEqual(staff["2026-02"], 200.0)
        direct = self._line_row(data, self.root_direct)["values"]
        self.assertEqual((direct["2026-01"], direct["2026-02"], direct["total"]), (100.0, 250.0, 350.0))
        indirect = self._line_row(data, self.root_indirect)["values"]
        self.assertEqual(indirect["2026-03"], 6.0)
        # Months after the current one are empty, not 0.
        self.assertIsNone(salaries["2026-04"])
        self.assertIsNone(direct["2026-12"])

    def test_profit_rows(self):
        self._entry("2026-01-10", [(self.account_salaries, 100.0, None)])
        self._entry("2026-02-10", [
            (self.account_sales, -1000.0, self.customer_a),
            (self.account_salaries, 200.0, None),
            (self.account_commissions, 50.0, None),
            (self.account_rent, 50.0, None),
        ])
        data = self._data()
        values = {key: self._row(data, key)["values"] for key in (
            "gross_profit", "gross_profit_pct", "net_profit", "net_profit_pct")}
        self.assertAlmostEqual(self._line_row(data, self.root_income)["values"]["2026-02"], 1000.0)
        self.assertAlmostEqual(values["gross_profit"]["2026-02"], 750.0)
        self.assertAlmostEqual(values["gross_profit_pct"]["2026-02"], 75.0)
        self.assertAlmostEqual(values["net_profit"]["2026-02"], 700.0)
        self.assertAlmostEqual(values["net_profit_pct"]["2026-02"], 70.0)
        # No sales in January: percentages are empty, never a division by zero.
        self.assertAlmostEqual(values["gross_profit"]["2026-01"], -100.0)
        self.assertIsNone(values["gross_profit_pct"]["2026-01"])
        self.assertIsNone(values["net_profit_pct"]["2026-01"])
        # Total column: amounts add up, percentages are recomputed on totals.
        self.assertAlmostEqual(values["net_profit"]["total"], 600.0)
        self.assertAlmostEqual(values["net_profit_pct"]["total"], 60.0)
        self.assertIsNone(values["net_profit"]["2026-05"])

    def test_sales_line_adds_up_its_accounts(self):
        # Every movement of the line's accounts counts, whatever the customer
        # (or none); credit notes subtract on their own.
        self._entry("2026-02-10", [
            (self.account_sales, -300.0, self.customer_a_contact),
            (self.account_sales, -200.0, self.customer_b),
            (self.account_sales, -10.0, None),
        ])
        self._entry("2026-02-20", [(self.account_sales, 50.0, self.customer_a)])
        data = self._data()
        self.assertAlmostEqual(self._line_row(data, self.leaf_sales)["values"]["2026-02"], 460.0)
        self.assertAlmostEqual(self._line_row(data, self.root_income)["values"]["2026-02"], 460.0)
        self.assertIsNone(self._row(data, "unassigned"))

    def test_unassigned_row(self):
        self._entry("2026-02-10", [(self.account_salaries, 100.0, None)])
        self.assertIsNone(self._row(self._data(), "unassigned"))

        # An expense account and an income account that no line includes.
        self._entry("2026-02-11", [
            (self.account_social, 40.0, None),
            (self.account_other_income, -110.0, self.customer_b),
        ])
        data = self._data()
        unassigned = self._row(data, "unassigned")
        self.assertTrue(unassigned)
        # Sign = effect on the result: +110 of income, -40 of expenses.
        self.assertAlmostEqual(unassigned["values"]["2026-02"], 70.0)
        self.assertAlmostEqual(unassigned["values"]["total"], 70.0)
        # Not included in sections nor profits.
        self.assertAlmostEqual(self._line_row(data, self.root_income)["values"]["2026-02"], 0.0)
        self.assertAlmostEqual(self._line_row(data, self.root_direct)["values"]["2026-02"], 100.0)
        self.assertAlmostEqual(self._row(data, "net_profit")["values"]["2026-02"], -100.0)

    def test_empty_leaf_is_zero(self):
        empty_leaf = self.Line.create({
            "structure_id": self.structure.id,
            "parent_id": self.root_indirect.id,
            "name": "IT infrastructure",
        })
        row = self._line_row(self._data(), empty_leaf)
        self.assertEqual(row["values"]["2026-01"], 0.0)
        self.assertEqual(row["values"]["total"], 0.0)
        self.assertEqual(row["assignment_status"], "Without accounts")

    def test_month_period(self):
        self._entry("2026-02-28", [(self.account_salaries, 100.0, None)])
        self._entry("2026-03-01", [(self.account_salaries, 70.0, None)])
        data = self._data("month")
        self.assertEqual([column["key"] for column in data["columns"]], ["2026-03"])
        self.assertEqual(self._line_row(data, self.leaf_salaries)["values"], {"2026-03": 70.0})

    def test_non_calendar_fiscal_year(self):
        self.company.write({"fiscalyear_last_month": "6", "fiscalyear_last_day": 30})
        self._entry("2025-06-30", [(self.account_salaries, 1.0, None)])
        self._entry("2025-07-01", [(self.account_salaries, 10.0, None)])
        self._entry("2025-12-31", [(self.account_salaries, 100.0, None)])
        self._entry("2026-01-01", [(self.account_salaries, 1000.0, None)])

        data = self._data("fiscal_year")
        self.assertEqual((data["date_from"], data["date_to"]), ("2025-07-01", "2026-06-30"))
        keys = [column["key"] for column in data["columns"]]
        self.assertEqual(keys[0], "2025-07")
        self.assertEqual(keys[11], "2026-06")
        salaries = self._line_row(data, self.leaf_salaries)["values"]
        self.assertEqual(salaries["total"], 1110.0)
        self.assertIsNone(salaries["2026-04"])

        data = self._data("previous_fiscal_year")
        self.assertEqual((data["date_from"], data["date_to"]), ("2024-07-01", "2025-06-30"))
        salaries = self._line_row(data, self.leaf_salaries)["values"]
        self.assertEqual(salaries["total"], 1.0)
        self.assertFalse(any(column["is_future"] for column in data["columns"]))

        data = self._data("last_12")
        self.assertEqual((data["date_from"], data["date_to"]), ("2025-04-01", "2026-03-31"))
        keys = [column["key"] for column in data["columns"]]
        self.assertEqual(keys[:12], ["2025-%02d" % m for m in range(4, 13)] + ["2026-01", "2026-02", "2026-03"])
        self.assertEqual(self._line_row(data, self.leaf_salaries)["values"]["total"], 1111.0)

    def test_no_structure(self):
        self.structure.active = False
        self.assertEqual(self._data()["has_structure"], False)

    def test_rpc_requires_module_group(self):
        user = self.env["res.users"].create({
            "name": "No dashboard", "login": "no_dashboard",
            "group_ids": [Command.set(self.env.ref("base.group_user").ids)],
            "company_id": self.company.id, "company_ids": [Command.set(self.company.ids)],
        })
        with self.assertRaises(AccessError):
            self.Dashboard.with_user(user).get_dashboard_data()

    def test_dashboard_config(self):
        config = self.Dashboard.get_dashboard_config()
        self.assertTrue(config["has_structure"])
        self.assertEqual(config["company_currency_id"], self.company.currency_id.id)
        self.assertEqual(config["secondary_currency_id"], self.structure.secondary_currency_id.id)
        self.assertEqual(config["default_display_currency"], "company")
        self.assertIn("analytic_plans", config)
        self.assertEqual(config["budgets"], [])
        self.assertTrue(config["can_configure"])
        self.structure.active = False
        self.assertFalse(self.Dashboard.get_dashboard_config()["has_structure"])
