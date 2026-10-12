from datetime import date

from freezegun import freeze_time

from odoo.tests import tagged

from .common import TreasuryDashboardCommon


@freeze_time("2026-10-14 12:00:00")
@tagged("post_install", "-at_install")
class TestInvestments(TreasuryDashboardCommon):

    def test_investment_in_foreign_currency(self):
        Dashboard = self.env["account.treasury.dashboard"]
        eur = self.setup_other_currency("EUR", rates=[("2026-01-01", 0.6), ("2026-10-14", 0.5)])
        journal = self._create_journal("Fund EUR", "FEUR", "general", currency=eur)
        journal.default_account_id = self._create_account("1.2.1.01", "Investment fund EUR", "asset_current",
                                                          currency=eur)
        medium = self._create_medium("investment", journal)
        capital = self._create_account("3.1.1.01", "Capital", "equity")
        self._entry(date(2026, 10, 2), [
            (journal.default_account_id, 1800.0, {"currency_id": eur.id, "amount_currency": 1000.0}),
            (capital, -1800.0),
        ])
        self.assertEqual(medium.currency_id, eur)
        section = Dashboard.get_section_data("investments")
        table = next(block for block in section["blocks"] if block["type"] == "table")
        cells = table["rows"][0]["cells"]
        self.assertAlmostEqual(cells["original"]["value"], 1000.0)
        self.assertEqual(cells["original"]["currency_id"], eur.id)
        self.assertAlmostEqual(cells["equivalent"]["value"], 2000.0)
        self.assertAlmostEqual(cells["book"]["value"], 1800.0)
        self.assertAlmostEqual(cells["difference"]["value"], 200.0)
        self.assertEqual(cells["last_date"]["value"], "2026-10-02")
        self.assertAlmostEqual(cells["last_amount"]["value"], 1000.0)
        self.assertEqual(cells["days"]["value"], 12)
        self.assertAlmostEqual(table["rows"][-1]["cells"]["equivalent"]["value"], 2000.0)
        popup = Dashboard.get_drilldown("investments", "balance", {"medium_id": medium.id})
        self.assertAlmostEqual(popup["total"]["value"], 1000.0)
