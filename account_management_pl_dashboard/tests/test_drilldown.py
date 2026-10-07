from freezegun import freeze_time

from odoo import Command
from odoo.exceptions import AccessError, UserError
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

    def _accounts_of(self, detail):
        return {entry["code"]: entry["amount"] for entry in detail["entries"]}

    def test_group_detail_lists_accounts(self):
        detail = self.Dashboard.get_cell_detail("line-%d" % self.root_direct.id, "total")
        self.assertEqual(detail["kind"], "items")
        self.assertEqual(self._accounts_of(detail), {
            "5.1.2.01.010": 300.0, "5.1.2.01.020": 33.33, "5.2.1.01.070": 50.0,
        })
        self.assertTrue(all(entry["open"] == "items" for entry in detail["entries"]))

    def test_leaf_detail_lists_accounts(self):
        detail = self.Dashboard.get_cell_detail("line-%d" % self.leaf_salaries.id, "2026-01")
        self.assertEqual(
            [(entry["code"], entry["amount"]) for entry in detail["entries"]],
            [("5.1.2.01.010", 100.0), ("5.1.2.01.020", 33.33)],
        )
        self.assertAlmostEqual(detail["total"], 133.33)

    def test_sales_detail_lists_accounts(self):
        detail = self.Dashboard.get_cell_detail("line-%d" % self.leaf_sales.id, "total")
        self.assertEqual(self._accounts_of(detail), {"4.1.1.01.001": 1600.0})
        self.assertTrue(detail["can_open_all"])

    def test_profit_rows_have_no_detail(self):
        data = self._data()
        for key in ("gross_profit", "gross_profit_pct", "net_profit", "net_profit_pct"):
            self.assertFalse(self._row(data, key)["drilldown"])
        with self.assertRaises(UserError):
            self.Dashboard.get_cell_detail("gross_profit", "total")

    def test_unassigned_detail(self):
        detail = self.Dashboard.get_cell_detail("unassigned", "2026-02")
        # Effect-on-result sign: income counts positive.
        self.assertEqual(
            {entry["label"]: entry["amount"] for entry in detail["entries"]}, {"Other income": 7.0},
        )
        action = self.Dashboard.get_detail_action("unassigned", "2026-02", "all")
        lines = self.env["account.move.line"].search(action["domain"])
        self.assertEqual(lines.account_id, self.account_other_income)

    def test_account_opens_general_ledger(self):
        closing_journal = self.env["account.journal"].create({
            "name": "Closing", "code": "CLS", "type": "general", "company_id": self.company.id,
        })
        self.structure.excluded_journal_ids = [Command.set(closing_journal.ids)]
        action = self.Dashboard.get_detail_action(
            "line-%d" % self.leaf_salaries.id, "2026-02", "account-%d" % self.account_salaries.id,
        )
        self.assertEqual(action["tag"], "account_report")
        options = action["params"]["options"]
        self.assertEqual((options["date"]["date_from"], options["date"]["date_to"]), ("2026-02-01", "2026-02-28"))
        self.assertTrue(options["unfold_all"])
        self.assertEqual(action["context"]["default_filter_accounts"], "5.1.2.01.010 Salaries")
        selected = {journal["id"] for journal in options["journals"]
                    if journal.get("model") == "account.journal" and journal.get("selected")}
        self.assertTrue(selected)
        self.assertNotIn(closing_journal.id, selected)

    def test_open_all_journal_items_of_the_line(self):
        # Every journal item of the line's accounts, for the clicked column.
        action = self.Dashboard.get_detail_action("line-%d" % self.leaf_sales.id, "2026-02", "all")
        lines = self.env["account.move.line"].search(action["domain"])
        self.assertEqual(sorted(lines.mapped("balance")), [-1000.0, -100.0])
        action = self.Dashboard.get_detail_action("line-%d" % self.leaf_sales.id, "total", "all")
        self.assertEqual(len(self.env["account.move.line"].search(action["domain"])), 3)

    def test_open_with_analytic_filter_lists_analytic_lines(self):
        detail = self.Dashboard.get_cell_detail(
            "line-%d" % self.leaf_sales.id, "total", analytic_ids=self.unit_1.ids,
        )
        self.assertAlmostEqual(detail["total"], 200.0)
        action = self.Dashboard.get_detail_action(
            "line-%d" % self.leaf_sales.id, "total", "account-%d" % self.account_sales.id,
            analytic_ids=self.unit_1.ids,
        )
        self.assertEqual(action["res_model"], "account.analytic.line")
        analytic_lines = self.env["account.analytic.line"].search(action["domain"])
        self.assertEqual(analytic_lines.mapped("amount"), [200.0])

    def test_ledger_keeps_the_analytic_filter(self):
        self.env.user.group_ids += self.env.ref("analytic.group_analytic_accounting")
        action = self.Dashboard.get_detail_action(
            "line-%d" % self.leaf_sales.id, "total", "account-%d" % self.account_sales.id,
            analytic_ids=self.unit_1.ids,
        )
        self.assertEqual(action["tag"], "account_report")
        self.assertEqual(action["params"]["options"]["analytic_accounts"], self.unit_1.ids)

    def test_rpcs_accept_the_dashboard_request_params(self):
        """The popup sends the dashboard's whole set of request parameters
        to every RPC."""
        params = {"period": "fiscal_year", "display_currency": "company", "analytic_ids": [], "budget_id": False}
        self.Dashboard.get_dashboard_data(**params)
        self.Dashboard.get_cell_detail("line-%d" % self.leaf_sales.id, "total", **params)
        action = self.Dashboard.get_detail_action("line-%d" % self.leaf_sales.id, "total", "all", **params)
        self.assertEqual(action["res_model"], "account.move.line")

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
            "line-%d" % self.leaf_sales.id, "total", display_currency="secondary",
        )
        self.assertEqual(detail["display_currency"], "secondary")
        self.assertEqual(detail["company_currency_name"], "ARS")

    def test_invariant_company_currency(self):
        self._assert_details_match_cells(period="fiscal_year", display_currency="company")

    def test_invariant_secondary_with_analytic(self):
        self._assert_details_match_cells(period="fiscal_year", display_currency="secondary",
                                         analytic_ids=self.unit_1.ids)
