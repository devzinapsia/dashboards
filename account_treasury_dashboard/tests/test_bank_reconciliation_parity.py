from freezegun import freeze_time

from odoo.tests import tagged

from .test_cash_position import TreasuryBankScenario


@freeze_time("2026-10-14 12:00:00")
@tagged("post_install", "-at_install")
class TestBankReconciliationParity(TreasuryBankScenario):
    """The dashboard's bank figures must match Odoo's bank reconciliation
    report (account_reports, Enterprise) for the same journal and date.
    Skipped where that report isn't installed."""

    def _report_amounts(self, journal):
        report = self.env.ref("account_reports.bank_reconciliation_report")
        report = report.with_context(active_id=journal.id, active_model="account.journal")
        options = report.get_options({})
        amounts = {}
        for line in report._get_lines(options):
            model, res_id = report._get_model_info_from_id(line["id"])
            if model != "account.report.line":
                continue
            code = self.env["account.report.line"].browse(res_id).code
            amount_column = next(column for column in line["columns"] if column["expression_label"] == "amount")
            amounts[code] = amount_column["no_format"] or 0.0
        return amounts

    def test_matches_bank_reconciliation_report(self):
        if "account.bank.reconciliation.report.handler" not in self.env:
            self.skipTest("Odoo's bank reconciliation report (account_reports) is not installed.")
        report = self._report_amounts(self.bank)
        figures = self.Dashboard._compute_banks(self.Dashboard._prepare_context(), self.bank_medium)[self.bank_medium.id]
        self.assertAlmostEqual(figures["liquidity"], report["balance_bank"])
        self.assertAlmostEqual(figures["statement"], report["last_statement_balance"])
        self.assertAlmostEqual(figures["without_statement"], report["transaction_without_statement"])
        self.assertAlmostEqual(figures["misc"], report["misc_operations"])
        self.assertAlmostEqual(figures["receipts"], report["outstanding_receipts"])
        self.assertAlmostEqual(figures["payments"], report["outstanding_payments"])
