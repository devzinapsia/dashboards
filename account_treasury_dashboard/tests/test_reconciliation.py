from datetime import date, timedelta

from freezegun import freeze_time

from odoo.tests import tagged

from .common import TreasuryDashboardCommon


@freeze_time("2026-10-14 12:00:00")
@tagged("post_install", "-at_install")
class TestReconciliation(TreasuryDashboardCommon):

    def setUp(self):
        super().setUp()
        self.Dashboard = self.env["account.treasury.dashboard"]
        self.bank, _receipts, _payments = self._setup_bank_with_outstanding("Bank A", "BKA")
        self.medium = self._create_medium("bank", self.bank)
        for days, amount in ((3, 100.0), (10, 200.0), (40, -50.0), (90, 70.0)):
            self._st_line(self.bank, self.today - timedelta(days=days), amount)
        # A reconciled line: never counted.
        reconciled = self._st_line(self.bank, self.today - timedelta(days=5), 30.0)
        self._match(reconciled, self._outstanding_line(self._payment(self.bank, 30.0, date=self.today)))
        self.assertTrue(reconciled.is_reconciled)

    def _bank_row(self, section):
        table = next(block for block in section["blocks"] if block["type"] == "table")
        return next(row for row in table["rows"] if row["key"] == "medium-%s" % self.medium.id)

    def test_aging_buckets(self):
        cells = self._bank_row(self.Dashboard.get_section_data("reconciliation"))["cells"]
        expected = {"0_7": (1, 100.0), "8_30": (1, 200.0), "31_60": (1, -50.0), "over_60": (1, 70.0)}
        for bucket, (count, amount) in expected.items():
            self.assertEqual(cells[bucket]["count"], count, bucket)
            self.assertAlmostEqual(cells[bucket]["value"], amount, msg=bucket)
        self.assertEqual(cells["total"]["count"], 4)
        self.assertAlmostEqual(cells["total"]["value"], 320.0)

    def test_bucket_popup_matches_cell(self):
        popup = self.Dashboard.get_drilldown("reconciliation", "unreconciled",
                                             {"medium_id": self.medium.id, "bucket": "8_30"})
        self.assertEqual(len(popup["rows"]), 1)
        self.assertAlmostEqual(popup["total"]["value"], 200.0)
        popup = self.Dashboard.get_drilldown("reconciliation", "unreconciled", {"medium_id": self.medium.id})
        self.assertAlmostEqual(popup["total"]["value"], 320.0)

    def test_stale_statement_alert(self):
        # Latest line 3 days ago, global threshold 3: not stale.
        section = self.Dashboard.get_section_data("reconciliation")
        self.assertFalse(self._bank_row(section)["cells"]["days"]["alert"])
        self.assertFalse(section["alerts"])
        # Global threshold lowered.
        self.config.statement_stale_days = 2
        section = self.Dashboard.get_section_data("reconciliation")
        self.assertEqual(self._bank_row(section)["cells"]["days"]["alert"], "warning")
        self.assertIn("no new statement for 3 days", section["alerts"][0]["message"])
        # The bank's own threshold wins over the global one.
        self.medium.stale_days = 5
        section = self.Dashboard.get_section_data("reconciliation")
        self.assertFalse(self._bank_row(section)["cells"]["days"]["alert"])

    def test_bank_without_statement_lines(self):
        medium = self._create_medium("bank", self._create_journal("Bank B", "BKB", "bank"))
        section = self.Dashboard.get_section_data("reconciliation")
        table = next(block for block in section["blocks"] if block["type"] == "table")
        row = next(row for row in table["rows"] if row["key"] == "medium-%s" % medium.id)
        self.assertEqual(row["cells"]["last_date"]["value"], "No statement")
        self.assertTrue(any("Bank B has no bank statement yet" in alert["message"] for alert in section["alerts"]))
