from freezegun import freeze_time

from odoo import Command
from odoo.exceptions import ValidationError
from odoo.tests import new_test_user, tagged

from .common import TreasuryChecksCommon


@freeze_time("2026-10-14 12:00:00")
@tagged("post_install", "-at_install")
class TestChecks(TreasuryChecksCommon):
    """Today is Wednesday 2026-10-14: projection week 1 = 14-18/10, week 2 =
    19-25/10, week 3 = 26/10-1/11, week 4 = 2-8/11, week 5 = 9-15/11."""

    def _rows(self):
        section = self.Dashboard.get_section_data("checks")
        self.assertNotIn("error", section)
        table = next(block for block in section["blocks"] if block["type"] == "table")
        return section, {row["key"]: row["cells"] for row in table["rows"]}

    def _projection(self):
        return self.Dashboard._compute_projection(self.Dashboard._prepare_context())

    # -------------------------------------------------------------------------
    # Section
    # -------------------------------------------------------------------------

    def test_section_is_registered(self):
        frame = self.Dashboard.get_dashboard()
        checks = next(section for section in frame["sections"] if section["id"] == "checks")
        self.assertTrue(checks["visible"])
        self.config.show_checks = False
        frame = self.Dashboard.get_dashboard()
        self.assertFalse(next(section for section in frame["sections"] if section["id"] == "checks")["visible"])

    def test_portfolio_by_payment_date(self):
        self._receive_checks([("001", -5, 100.0), ("002", 0, 200.0), ("003", 5, 300.0),
                              ("004", 20, 400.0), ("005", 60, 500.0)])
        section, rows = self._rows()
        portfolio = rows["portfolio"]
        expected = {"overdue": 100.0, "today": 200.0, "next_7": 300.0, "next_30": 400.0, "later": 500.0}
        for bucket, amount in expected.items():
            self.assertEqual(portfolio[bucket]["count"], 1, bucket)
            self.assertAlmostEqual(portfolio[bucket]["value"], amount, msg=bucket)
        self.assertAlmostEqual(portfolio["total"]["value"], 1500.0)
        self.assertEqual(portfolio["overdue"]["alert"], "warning")
        self.assertTrue(any("payment date already passed" in alert["message"] for alert in section["alerts"]))

    def test_popup_lists_the_checks(self):
        self._receive_checks([("001", 5, 300.0), ("002", 6, 50.0), ("003", 20, 400.0)])
        popup = self.Dashboard.get_drilldown("checks", "checks", {"group": "portfolio", "bucket": "next_7"})
        self.assertEqual([row["cells"]["number"]["value"] for row in popup["rows"]], ["001", "002"])
        self.assertAlmostEqual(popup["total"]["value"], 350.0)
        self.assertEqual(popup["rows"][0]["record"]["model"], "l10n_latam.check")

    def test_deposited_and_rejected(self):
        checks = self._receive_checks([("001", 10, 1000.0), ("002", 20, 500.0), ("003", 25, 70.0)])
        self._transfer(checks[0], self.bank)
        self._transfer(checks[2], self.rejected_journal)
        section, rows = self._rows()
        self.assertAlmostEqual(rows["deposited"]["next_30"]["value"], 1000.0)
        self.assertAlmostEqual(rows["portfolio"]["total"]["value"], 500.0)
        self.assertAlmostEqual(rows["rejected"]["total"]["value"], 70.0)
        self.assertTrue(any("1 rejected check:" in alert["message"] for alert in section["alerts"]))

    def test_own_checks_pending_debit(self):
        self._issue_own_checks([("501", 20, 700.0)])
        _section, rows = self._rows()
        self.assertAlmostEqual(rows["own"]["next_30"]["value"], 700.0)
        self.assertEqual(rows["own"]["total"]["count"], 1)

    # -------------------------------------------------------------------------
    # Projection
    # -------------------------------------------------------------------------

    def test_portfolio_projected_on_payment_date(self):
        self._receive_checks([("001", -3, 100.0), ("002", 8, 300.0), ("003", 30, 400.0), ("004", 90, 900.0)])
        projection = self._projection()
        cells = projection["cells"]["third_party_checks"]
        self.assertAlmostEqual(cells[0], 100.0)  # payment date passed: week 1
        self.assertAlmostEqual(cells[1], 300.0)  # 22/10
        self.assertAlmostEqual(cells[4], 400.0)  # 13/11
        self.assertAlmostEqual(sum(cells), 800.0)  # 12/01 is beyond the horizon

    def test_own_check_out_of_generic_in_transit(self):
        self._issue_own_checks([("501", 20, 700.0)])
        projection = self._projection()
        self.assertAlmostEqual(sum(projection["cells"]["in_transit_payments"]), 0.0)
        self.assertAlmostEqual(projection["cells"]["own_checks"][3], -700.0)  # 3/11: week 4
        self.assertAlmostEqual(sum(projection["cells"]["own_checks"]), -700.0)

    def test_several_own_checks_in_one_payment(self):
        self._issue_own_checks([("501", 6, 100.0), ("502", 13, 200.0)])
        projection = self._projection()
        self.assertAlmostEqual(sum(projection["cells"]["in_transit_payments"]), 0.0)
        self.assertAlmostEqual(projection["cells"]["own_checks"][1], -100.0)  # 20/10
        self.assertAlmostEqual(projection["cells"]["own_checks"][2], -200.0)  # 27/10

    def test_deposited_check_on_its_date_not_in_week_1(self):
        checks = self._receive_checks([("001", 10, 1000.0), ("002", 15, 600.0)])
        self._transfer(checks, self.bank)
        projection = self._projection()
        self.assertAlmostEqual(sum(projection["cells"]["in_transit_receipts"]), 0.0)
        self.assertAlmostEqual(projection["cells"]["third_party_checks"][1], 1000.0)  # 24/10
        self.assertAlmostEqual(projection["cells"]["third_party_checks"][2], 600.0)  # 29/10
        # Once credited (matched with the statement), only in the opening balance.
        deposit = self.env["account.payment"].search([
            ("journal_id", "=", self.bank.id), ("l10n_latam_move_check_ids", "in", checks.ids)])
        st_line = self._st_line(self.bank, self.today, 1600.0)
        self._match(st_line, self._outstanding_line(deposit))
        projection = self._projection()
        self.assertAlmostEqual(sum(projection["cells"]["third_party_checks"]), 0.0)
        self.assertAlmostEqual(projection["opening"], 1600.0)

    def test_rejected_checks_are_not_projected(self):
        checks = self._receive_checks([("001", 10, 1000.0)])
        self._transfer(checks, self.rejected_journal)
        self.assertAlmostEqual(sum(self._projection()["cells"]["third_party_checks"]), 0.0)

    def test_drilldown_adds_up_to_the_cell(self):
        self._receive_checks([("001", 3, 100.0), ("002", 4, 50.0), ("003", 12, 300.0)])
        self._issue_own_checks([("501", 6, 100.0), ("502", 13, 200.0)])
        section = self.Dashboard.get_section_data("projection")
        table = next(block for block in section["blocks"] if block["type"] == "table")
        checked = 0
        for row in table["rows"]:
            if row["key"] not in ("third_party_checks", "own_checks"):
                continue
            for cell in row["cells"].values():
                if cell.get("drilldown"):
                    popup = self.Dashboard.get_drilldown("projection", "flows", cell["drilldown"]["params"])
                    self.assertAlmostEqual(popup["total"]["value"], cell["value"])
                    checked += 1
        self.assertGreaterEqual(checked, 4)

    # -------------------------------------------------------------------------
    # Configuration
    # -------------------------------------------------------------------------

    def test_check_journal_cannot_be_a_payment_mean(self):
        with self.assertValidationError("is configured as a check journal"):
            self._create_medium("cash", self.checks_journal)
        cash = self._create_medium("cash", self.cash_journal)
        with self.assertValidationError("is a check journal, so it can't be payment mean"):
            self.config.rejected_check_journal_ids = [Command.link(cash.journal_id.id)]

    def test_same_journal_third_party_and_rejected(self):
        with self.assertRaises(ValidationError):
            self.config.rejected_check_journal_ids = [Command.link(self.checks_journal.id)]

    def test_load_suggested_skips_check_journals(self):
        self.config.action_load_suggested()
        journals = self.config.medium_ids.journal_id
        self.assertNotIn(self.checks_journal, journals)
        self.assertNotIn(self.rejected_journal, journals)
        self.assertIn(self.cash_journal, journals)

    def test_dashboard_user_without_check_rights(self):
        self._receive_checks([("001", 5, 300.0)])
        user = new_test_user(
            self.env, login="treasury_checks_viewer",
            groups="account_treasury_dashboard.group_treasury_dashboard_user",
            company_id=self.company.id, company_ids=[Command.set(self.company.ids)],
        )
        Dashboard = self.Dashboard.with_user(user)
        self.assertNotIn("error", Dashboard.get_section_data("checks"))
        popup = Dashboard.get_drilldown("checks", "checks", {"group": "portfolio"})
        self.assertAlmostEqual(popup["total"]["value"], 300.0)
        self.assertFalse(popup["list_action"])
        self.assertFalse(popup["rows"][0]["record"])
