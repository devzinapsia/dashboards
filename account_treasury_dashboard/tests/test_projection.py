from datetime import date

from freezegun import freeze_time

from odoo import Command
from odoo.tests import tagged

from .common import TreasuryDashboardCommon


@freeze_time("2026-10-14 12:00:00")
@tagged("post_install", "-at_install")
class TestProjection(TreasuryDashboardCommon):
    """Today is Wednesday 2026-10-14: week 1 = 14-18/10, week 2 = 19-25/10,
    week 3 = 26/10-1/11, ... (6 weeks, up to 22/11)."""

    def setUp(self):
        super().setUp()
        self.Dashboard = self.env["account.treasury.dashboard"]
        self.bank, _receipts, _payments = self._setup_bank_with_outstanding("Bank A", "BKA")
        self.medium = self._create_medium("bank", self.bank)
        # Bank account: 1,000.
        self._st_line(self.bank, date(2026, 10, 1), 1000.0)

    def _projection(self):
        return self.Dashboard._compute_projection(self.Dashboard._prepare_context())

    def test_opening_balance_is_the_bank_account(self):
        # A pending receipt is not in the opening balance: it is a week 1 flow.
        self._payment(self.bank, 150.0, date=date(2026, 10, 13))
        projection = self._projection()
        self.assertAlmostEqual(projection["opening"], 1000.0)
        self.assertAlmostEqual(projection["cells"]["in_transit_receipts"][0], 150.0)
        self.assertAlmostEqual(projection["closings"][0], 1150.0)

    def test_investments_in_the_opening_balance(self):
        eur = self.setup_other_currency("EUR", rates=[("2026-01-01", 0.6), ("2026-10-14", 0.5)])
        fund = self._create_journal("Fund EUR", "FEUR", "general", currency=eur)
        fund.default_account_id = self._create_account("1.2.1.01", "Fund EUR", "asset_current", currency=eur)
        deposit = self._create_journal("Term deposit", "TDEP", "bank")
        capital = self._create_account("3.1.1.01", "Capital", "equity")
        self._entry(date(2026, 10, 2), [
            (fund.default_account_id, 180.0, {"currency_id": eur.id, "amount_currency": 100.0}), (capital, -180.0),
        ])
        self._entry(date(2026, 10, 2), [(deposit.default_account_id, 500.0), (capital, -500.0)])
        fund_medium = self._create_medium("investment", fund)
        self._create_medium("investment", deposit)  # not in the projection
        self.assertAlmostEqual(self._projection()["opening"], 1000.0)

        fund_medium.in_projection = True
        projection = self._projection()
        self.assertAlmostEqual(projection["opening"], 1000.0 + 200.0)  # 100 EUR at today's rate
        popup = self.Dashboard.get_drilldown("projection", "opening", {})
        self.assertEqual(len(popup["rows"]), 2)
        self.assertAlmostEqual(popup["total"]["value"], 1200.0)
        section = self.Dashboard.get_section_data("projection")
        self.assertEqual(section["blocks"][0]["items"][0]["secondary"]["value"],
                         "Bank accounts and investments as of today")

    def test_receivables_and_payables_by_due_date(self):
        self._invoice("out_invoice", 300.0, date(2026, 10, 20))
        self._invoice("in_invoice", 400.0, date(2026, 10, 30))
        projection = self._projection()
        self.assertAlmostEqual(projection["cells"]["receivables"][1], 300.0)
        self.assertAlmostEqual(projection["cells"]["payables"][2], -400.0)
        self.assertAlmostEqual(projection["closings"][-1], 1000.0 + 300.0 - 400.0)

    def test_overdue_receivables_separate_unless_included(self):
        self._invoice("out_invoice", 200.0, date(2026, 10, 1), date=date(2026, 9, 1))
        projection = self._projection()
        self.assertAlmostEqual(projection["cells"]["overdue_receivables"][0], 200.0)
        self.assertAlmostEqual(projection["cells"]["receivables"][0], 0.0)
        self.assertAlmostEqual(projection["closings"][0], 1000.0)

        self.config.include_overdue_receivables = True
        projection = self._projection()
        self.assertAlmostEqual(projection["cells"]["receivables"][0], 200.0)
        self.assertAlmostEqual(projection["closings"][0], 1200.0)

    def test_overdue_payables_in_week_1(self):
        self._invoice("in_invoice", 100.0, date(2026, 10, 5), date=date(2026, 9, 5))
        projection = self._projection()
        self.assertAlmostEqual(projection["cells"]["payables"][0], -100.0)
        self.assertAlmostEqual(projection["closings"][0], 900.0)

    def test_paid_invoice_is_not_counted_twice(self):
        invoice = self._invoice("out_invoice", 500.0, date(2026, 10, 20))
        payment = self._payment(self.bank, 500.0, date=date(2026, 10, 13))
        receivable_lines = (invoice.line_ids | payment.move_id.line_ids).filtered(
            lambda line: line.account_id.account_type == "asset_receivable")
        receivable_lines.reconcile()
        self.assertEqual(invoice.amount_residual, 0.0)
        projection = self._projection()
        self.assertAlmostEqual(sum(projection["cells"]["receivables"]), 0.0)
        self.assertAlmostEqual(projection["cells"]["in_transit_receipts"][0], 500.0)
        self.assertAlmostEqual(projection["closings"][-1], 1500.0)

        # Once matched with the bank statement, it is in the opening balance only.
        st_line = self._st_line(self.bank, date(2026, 10, 14), 500.0)
        self._match(st_line, self._outstanding_line(payment))
        projection = self._projection()
        self.assertAlmostEqual(projection["opening"], 1500.0)
        self.assertAlmostEqual(projection["cells"]["in_transit_receipts"][0], 0.0)
        self.assertAlmostEqual(projection["closings"][-1], 1500.0)

    def test_commitments(self):
        salaries = self._create_account("2.1.4.01", "Salaries payable", "liability_current", reconcile=True)
        taxes = self._create_account("2.1.5.01", "Taxes payable", "liability_current")
        expense = self.company_data["default_account_expense"]
        employee = self.env["res.partner"].create({"name": "Employee"})
        self._entry(date(2026, 10, 1), [
            (expense, 600.0), (salaries, -600.0, {"partner_id": employee.id, "date_maturity": date(2026, 10, 21)}),
        ])
        self._entry(date(2026, 10, 1), [(expense, 250.0), (taxes, -250.0)])
        payroll = self.Commitment.create({
            "config_id": self.config.id, "name": "Salaries", "kind": "payroll",
            "account_ids": [Command.set(salaries.ids)],
        })
        tax = self.Commitment.create({
            "config_id": self.config.id, "name": "Taxes", "kind": "tax",
            "account_ids": [Command.set(taxes.ids)], "payment_day": 27,
        })
        self.assertEqual(payroll.mode, "open_items")
        self.assertEqual(tax.mode, "balance")
        projection = self._projection()
        self.assertAlmostEqual(projection["cells"]["commitment_%s" % payroll.id][1], -600.0)
        self.assertAlmostEqual(projection["cells"]["commitment_%s" % tax.id][2], -250.0)  # 27/10: week 3
        popup = self.Dashboard.get_drilldown("projection", "flows",
                                             {"category": "commitment_%s" % payroll.id, "week": 1})
        self.assertEqual(popup["rows"][0]["cells"]["partner"]["value"], "Employee")

    def test_balance_commitment_without_payment_day(self):
        """Without a payment day, the balance goes on the due date of the
        latest entry crediting the accounts (week 1 once past)."""
        salaries = self._create_account("2.1.4.01", "Salaries payable", "liability_current")
        expense = self.company_data["default_account_expense"]
        self._entry(date(2026, 9, 30), [(expense, 400.0), (salaries, -400.0, {"date_maturity": date(2026, 10, 5)})])
        self._entry(date(2026, 10, 1), [(expense, 600.0), (salaries, -600.0, {"date_maturity": date(2026, 10, 28)})])
        commitment = self.Commitment.create({
            "config_id": self.config.id, "name": "Salaries", "kind": "payroll",
            "account_ids": [Command.set(salaries.ids)],
        })
        self.assertEqual(commitment.mode, "balance")
        cells = self._projection()["cells"]["commitment_%s" % commitment.id]
        self.assertAlmostEqual(cells[2], -1000.0)  # 28/10: week 3
        self._entry(date(2026, 10, 2), [(expense, 50.0), (salaries, -50.0, {"date_maturity": date(2026, 10, 2)})])
        cells = self._projection()["cells"]["commitment_%s" % commitment.id]
        self.assertAlmostEqual(cells[0], -1050.0)  # latest entry due 2/10, already past: week 1

    def test_credit_card_statements(self):
        card = self._create_medium("credit_card", self.credit_journal, closing_day=5, due_day=15)
        card_account = self.credit_journal.default_account_id
        expense = self.company_data["default_account_expense"]
        self._entry(date(2026, 9, 20), [(expense, 400.0), (card_account, -400.0)])
        self._entry(date(2026, 10, 8), [(expense, 250.0), (card_account, -250.0)])
        projection = self._projection()
        # Closed on 5/10, due on 15/10 (week 1); current cycle due on 15/11 (week 5).
        self.assertAlmostEqual(projection["cells"]["credit_cards"][0], -400.0)
        self.assertAlmostEqual(projection["cells"]["credit_cards"][4], -250.0)
        self.assertTrue(card)

    def test_negative_projected_balance_alert(self):
        self._invoice("in_invoice", 1500.0, date(2026, 10, 22))
        section = self.Dashboard.get_section_data("projection")
        self.assertTrue(any("Negative projected balance in Week 2" in alert["message"]
                            for alert in section["alerts"]))
        minimum = section["blocks"][0]["items"][1]
        self.assertAlmostEqual(minimum["main"]["value"], -500.0)
        self.assertEqual(minimum["main"]["alert"], "danger")
        table = next(block for block in section["blocks"] if block["type"] == "table")
        closing = next(row for row in table["rows"] if row["key"] == "closing")
        self.assertEqual(closing["cells"]["week_1"]["alert"], "danger")
        self.assertFalse(closing["cells"]["week_0"]["alert"])

    def test_drilldown_adds_up_to_the_cell(self):
        self._invoice("out_invoice", 300.0, date(2026, 10, 20))
        self._invoice("out_invoice", 120.0, date(2026, 10, 24))
        self._invoice("in_invoice", 100.0, date(2026, 10, 5), date=date(2026, 9, 5))
        self._invoice("in_invoice", 70.0, date(2026, 10, 16))
        self._payment(self.bank, 80.0, "outbound", date=date(2026, 10, 13), partner=self.vendor)
        section = self.Dashboard.get_section_data("projection")
        table = next(block for block in section["blocks"] if block["type"] == "table")
        checked = 0
        for row in table["rows"]:
            for cell in row["cells"].values():
                drilldown = cell.get("drilldown")
                if not drilldown or drilldown["key"] != "flows":
                    continue
                popup = self.Dashboard.get_drilldown("projection", "flows", drilldown["params"])
                self.assertAlmostEqual(sum(popup_row["cells"]["amount"]["value"] for popup_row in popup["rows"]),
                                       cell["value"])
                self.assertAlmostEqual(popup["total"]["value"], cell["value"])
                checked += 1
        self.assertGreaterEqual(checked, 6)
