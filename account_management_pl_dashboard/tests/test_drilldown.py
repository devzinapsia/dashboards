from freezegun import freeze_time

from odoo import Command
from odoo.exceptions import AccessError
from odoo.tests import tagged

from .common import PlDashboardAnalyticMixin, PlDashboardArsCommon, PlDashboardCommon


class DrilldownAssertions:

    def _assert_details_match_cells(self, **params):
        """Every drillable cell's popup detail adds up to the cell value,
        within the presentation rounding tolerance."""
        data = self._data(**params)
        tolerance = 10 ** -self.env["res.currency"].browse(data["currency_id"]).decimal_places / 2
        checked = 0
        for row in data["rows"]:
            if not row["drilldown"]:
                continue
            for column in data["columns"]:
                value = row["values"][column["key"]]
                if value is None:
                    continue
                detail = self.Dashboard.get_cell_detail(row["key"], column["key"], **params)
                self.assertLessEqual(
                    abs(detail["total"] - value), tolerance,
                    "Detail of %s / %s doesn't match its cell" % (row["name"], column["key"]),
                )
                checked += 1
        self.assertTrue(checked)
        return data


@tagged("post_install", "-at_install")
@freeze_time("2026-03-15")
class TestPlDrilldown(DrilldownAssertions, PlDashboardAnalyticMixin, PlDashboardCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_analytics()
        cls.leaf_salaries.account_ids = [Command.link(cls.account_social.id)]
        cls._entry("2026-01-10", [
            (cls.account_salaries, 100.0, None, {cls.unit_1: 100.0}),
            (cls.account_social, 33.33, None),
            (cls.account_sales, -500.0, cls.customer_a_contact, {cls.unit_1: 40.0, cls.unit_2: 60.0}),
        ])
        cls._entry("2026-02-10", [
            (cls.account_salaries, 200.0, None),
            (cls.account_commissions, 50.0, None, {cls.unit_2: 100.0}),
            (cls.account_rent, 10.0, None),
            (cls.account_other_income, -7.0, None),
            (cls.account_sales, -1000.0, cls.customer_a),
            (cls.account_sales, -100.0, cls.customer_b),
        ])

    def test_invariant_company_currency(self):
        self._assert_details_match_cells(period="fiscal_year")
        self._assert_details_match_cells(period="month")

    def test_invariant_with_analytic_filter(self):
        self._assert_details_match_cells(period="fiscal_year", analytic_ids=self.unit_1.ids)

    def test_invariant_sales_by_analytic(self):
        self.structure.sales_dimension = "analytic"
        self._assert_details_match_cells(period="fiscal_year")

    def test_group_detail_lists_its_leaves(self):
        detail = self.Dashboard.get_cell_detail("line-%d" % self.root_direct.id, "total")
        self.assertEqual(detail["kind"], "lines")
        self.assertEqual(
            {entry["label"]: entry["amount"] for entry in detail["entries"]},
            {"Staff / Salaries": 333.33, "Sales commissions": 50.0},
        )
        self.assertTrue(all(entry["open"] == "line" for entry in detail["entries"]))

    def test_leaf_detail_lists_accounts(self):
        detail = self.Dashboard.get_cell_detail("line-%d" % self.leaf_salaries.id, "2026-01")
        self.assertEqual(detail["kind"], "items")
        self.assertEqual(
            [(entry["code"], entry["amount"]) for entry in detail["entries"]],
            [("5.1.2.01.010", 100.0), ("5.1.2.01.020", 33.33)],
        )
        self.assertAlmostEqual(detail["total"], 133.33)

    def test_unassigned_detail(self):
        detail = self.Dashboard.get_cell_detail("unassigned", "2026-02")
        labels = {entry["label"]: entry["amount"] for entry in detail["entries"]}
        # Effect-on-result sign: income counts positive.
        self.assertEqual(set(labels), {"Other income", "Sales: Customer B"})
        self.assertAlmostEqual(labels["Other income"], 7.0)
        self.assertAlmostEqual(labels["Sales: Customer B"], 100.0)
        self.assertTrue(all(entry["open"] == "items" for entry in detail["entries"]))

    def test_open_account_journal_items(self):
        action = self.Dashboard.get_detail_action(
            "line-%d" % self.leaf_salaries.id, "2026-02", "account-%d" % self.account_salaries.id,
        )
        self.assertEqual(action["res_model"], "account.move.line")
        self.assertEqual(action["context"].get("create"), False)
        lines = self.env["account.move.line"].search(action["domain"])
        self.assertEqual(lines.mapped("balance"), [200.0])

    def test_open_customer_includes_contacts(self):
        action = self.Dashboard.get_detail_action(
            "line-%d" % self.leaf_customers.id, "total", "partner-%d" % self.customer_a.id,
        )
        lines = self.env["account.move.line"].search(action["domain"])
        self.assertEqual(sorted(lines.mapped("balance")), [-1000.0, -500.0])
        self.assertIn(self.customer_a_contact, lines.partner_id)

    def test_open_with_analytic_filter_lists_analytic_lines(self):
        detail = self.Dashboard.get_cell_detail(
            "line-%d" % self.leaf_customers.id, "total", analytic_ids=self.unit_1.ids,
        )
        self.assertAlmostEqual(detail["total"], 200.0)
        action = self.Dashboard.get_detail_action(
            "line-%d" % self.leaf_customers.id, "total", "partner-%d" % self.customer_a.id,
            analytic_ids=self.unit_1.ids,
        )
        self.assertEqual(action["res_model"], "account.analytic.line")
        analytic_lines = self.env["account.analytic.line"].search(action["domain"])
        self.assertEqual(analytic_lines.mapped("amount"), [200.0])

    def test_sales_not_distributed_has_no_list(self):
        self.structure.sales_dimension = "analytic"
        detail = self.Dashboard.get_cell_detail("unassigned", "2026-02")
        entry = next(entry for entry in detail["entries"] if entry["key"] == "sales-no-analytic")
        self.assertFalse(entry["open"])
        self.assertAlmostEqual(entry["amount"], 1100.0)

    def test_detail_requires_module_group(self):
        user = self.env["res.users"].create({
            "name": "No dashboard", "login": "no_dashboard_detail",
            "group_ids": [Command.set(self.env.ref("base.group_user").ids)],
            "company_id": self.company.id, "company_ids": [Command.set(self.company.ids)],
        })
        with self.assertRaises(AccessError):
            self.Dashboard.with_user(user).get_cell_detail("line-%d" % self.leaf_salaries.id, "total")
        with self.assertRaises(AccessError):
            self.Dashboard.with_user(user).get_detail_action(
                "line-%d" % self.leaf_salaries.id, "total", "account-%d" % self.account_salaries.id,
            )


@tagged("post_install", "-at_install")
@freeze_time("2026-03-15")
class TestPlDrilldownSecondary(DrilldownAssertions, PlDashboardAnalyticMixin, PlDashboardArsCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_analytics()
        cls._rate(cls.usd, "2026-01-10", 997.0)
        cls._rate(cls.usd, "2026-02-10", 1013.0)
        cls._rate(cls.usd, "2026-02-12", 1021.0)
        cls._entry("2026-01-10", [
            (cls.account_salaries, 123456.78, None, {cls.unit_1: 33.33, cls.unit_2: 66.67}),
            (cls.account_social, 9999.99, None),
        ])
        cls._entry("2026-02-10", [
            (cls.account_commissions, 15000.0, None, cls.eur, 10.0),
            (cls.account_commissions, 777.0, None, cls.usd, 0.0),
        ])
        cls._invoice("2026-02-12", 1234.56, cls.usd, cls.customer_a, distribution={cls.unit_1: 70.0, cls.unit_2: 30.0})
        cls._invoice("2026-02-12", 99.99, cls.usd, cls.customer_b)
        cls._entry("2026-02-12", [(cls.account_sales, -55555.55, cls.customer_a_contact)])

    def test_invariant_secondary_currency(self):
        data = self._assert_details_match_cells(period="fiscal_year", display_currency="secondary")
        self.assertEqual(data["currency_id"], self.usd.id)
        detail = self.Dashboard.get_cell_detail(
            "line-%d" % self.leaf_customers.id, "total", display_currency="secondary",
        )
        self.assertEqual(detail["display_currency"], "secondary")
        self.assertEqual(detail["company_currency_name"], "ARS")

    def test_invariant_company_currency(self):
        self._assert_details_match_cells(period="fiscal_year", display_currency="company")

    def test_invariant_secondary_with_analytic(self):
        self._assert_details_match_cells(period="fiscal_year", display_currency="secondary",
                                         analytic_ids=self.unit_1.ids)
        self.structure.sales_dimension = "analytic"
        self._assert_details_match_cells(period="fiscal_year", display_currency="secondary")
