from datetime import date

from freezegun import freeze_time

from odoo.tests import tagged

from .common import TreasuryDashboardCommon


@freeze_time("2026-10-14 12:00:00")
@tagged("post_install", "-at_install")
class TestMovements(TreasuryDashboardCommon):

    def setUp(self):
        super().setUp()
        self.Dashboard = self.env["account.treasury.dashboard"]
        self._create_medium("bank", self.bank_journal)
        self._create_medium("cash", self.cash_journal)
        self.card = self._create_medium("credit_card", self.credit_journal, closing_day=5, due_day=15)
        bank = self.bank_journal.default_account_id
        cash = self.cash_journal.default_account_id
        revenue = self.company_data["default_account_revenue"]
        expense = self.company_data["default_account_expense"]
        # Previous month: one inflow before the 14th, one outflow after it.
        self._entry(date(2026, 9, 2), [(bank, 800.0), (revenue, -800.0)])
        self._entry(date(2026, 9, 20), [(expense, 500.0), (bank, -500.0)])
        # This month.
        self._entry(date(2026, 10, 3), [(bank, 1000.0), (revenue, -1000.0)])
        self._entry(date(2026, 10, 5), [(expense, 300.0), (bank, -300.0)])
        self._entry(date(2026, 10, 6), [(cash, 200.0), (bank, -200.0)])  # internal transfer
        self._entry(date(2026, 10, 7), [(self.credit_journal.default_account_id, 150.0), (bank, -150.0)])  # card

    def _cells(self, row_key):
        section = self.Dashboard.get_section_data("movements")
        table = next(block for block in section["blocks"] if block["type"] == "table")
        return next(row for row in table["rows"] if row["key"] == row_key)["cells"]

    def test_inflows_outflows_and_transfers(self):
        income = self._cells("income")
        expense = self._cells("expense")
        transfer = self._cells("transfer")
        self.assertAlmostEqual(income["current"]["value"], 1000.0)
        # The card statement paid from the bank is an outflow, not a transfer.
        self.assertAlmostEqual(expense["current"]["value"], 450.0)
        self.assertAlmostEqual(transfer["current"]["value"], 200.0)
        self.assertEqual(transfer["current"]["count"], 1)

    def test_comparison_with_previous_month(self):
        income = self._cells("income")
        expense = self._cells("expense")
        self.assertAlmostEqual(income["previous_same_day"]["value"], 800.0)
        self.assertAlmostEqual(income["previous"]["value"], 800.0)
        self.assertAlmostEqual(income["variation"]["value"], 25.0)
        self.assertAlmostEqual(expense["previous_same_day"]["value"], 0.0)
        self.assertAlmostEqual(expense["previous"]["value"], 500.0)
        self.assertFalse(expense["variation"]["value"])  # no comparison against zero

    def test_transfer_through_transfer_account(self):
        transfer_account = self.company.transfer_account_id
        self._entry(date(2026, 10, 8), [(transfer_account, 90.0), (self.bank_journal.default_account_id, -90.0)])
        self._entry(date(2026, 10, 9), [(self.cash_journal.default_account_id, 90.0), (transfer_account, -90.0)])
        self.assertAlmostEqual(self._cells("expense")["current"]["value"], 450.0)
        transfer = self._cells("transfer")
        self.assertAlmostEqual(transfer["current"]["value"], 290.0)
        self.assertEqual(transfer["current"]["count"], 2)

    def test_popup_matches_cell(self):
        popup = self.Dashboard.get_drilldown("movements", "moves", {"period": "current", "kind": "expense"})
        self.assertEqual(len(popup["rows"]), 2)
        self.assertAlmostEqual(popup["total"]["value"], 450.0)
        # "View all" opens the payment means' items of those entries.
        items = self.env["account.move.line"].search(popup["list_action"]["domain"])
        self.assertEqual(len(items.move_id), 2)
        self.assertAlmostEqual(sum(items.mapped("balance")), -450.0)
