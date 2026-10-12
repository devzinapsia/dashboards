from unittest.mock import patch

from odoo import Command
from odoo.exceptions import AccessError, UserError
from odoo.tests import new_test_user, tagged
from odoo.tools import mute_logger

from .common import TreasuryDashboardCommon


@tagged("post_install", "-at_install")
class TestTreasurySections(TreasuryDashboardCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Dashboard = cls.env["account.treasury.dashboard"]
        cls.dashboard_user = new_test_user(
            cls.env, login="treasury_viewer", groups="account_treasury_dashboard.group_treasury_dashboard_user",
            company_id=cls.company.id, company_ids=[Command.set(cls.company.ids)],
        )
        cls.no_group_user = new_test_user(
            cls.env, login="no_treasury", groups="base.group_user",
            company_id=cls.company.id, company_ids=[Command.set(cls.company.ids)],
        )

    # The sections of this module: others (e.g. the checks bridge, installed
    # automatically) may add their own.
    OWN_SECTIONS = ("cash_position", "reconciliation", "investments", "projection", "movements")

    def _visible(self, frame):
        return [section["id"] for section in frame["sections"]
                if section["visible"] and section["id"] in self.OWN_SECTIONS]

    # -------------------------------------------------------------------------
    # Frame
    # -------------------------------------------------------------------------

    def test_company_without_configuration(self):
        self.config.active = False
        frame = self.Dashboard.get_dashboard()
        self.assertFalse(frame["has_config"])
        self.assertEqual(self._visible(frame), [])
        self.assertIn("not configured yet", frame["message"])

    def test_configuration_without_mediums(self):
        frame = self.Dashboard.get_dashboard()
        self.assertTrue(frame["has_config"])
        self.assertEqual(self._visible(frame), [])
        self.assertIn("nothing to show yet", frame["message"])

    def test_sections_follow_configuration(self):
        self._create_medium("bank", self.bank_journal)
        frame = self.Dashboard.get_dashboard()
        self.assertFalse(frame["message"])
        self.assertEqual(self._visible(frame), ["cash_position", "reconciliation", "projection", "movements"])

        self._create_medium("investment", self._create_journal("Investment", "INV1", "general"))
        self.config.show_reconciliation = False
        frame = self.Dashboard.get_dashboard()
        self.assertEqual(self._visible(frame), ["cash_position", "investments", "projection", "movements"])
        reconciliation = next(section for section in frame["sections"] if section["id"] == "reconciliation")
        self.assertFalse(reconciliation["enabled"])
        self.assertTrue(reconciliation["configured"])

    def test_hidden_section_is_not_computed(self):
        with self.assertRaises(UserError):
            self.Dashboard.get_section_data("investments")
        with self.assertRaises(UserError):
            self.Dashboard.get_section_data("unknown")

    # -------------------------------------------------------------------------
    # Error isolation
    # -------------------------------------------------------------------------

    def test_failing_section_does_not_break_the_others(self):
        self._create_medium("bank", self.bank_journal)
        Dashboard = type(self.Dashboard)

        def missing_rate(self, ctx):
            raise UserError("There is no USD exchange rate loaded yet.")

        def crashing(self, ctx):
            # A failed SQL query: the section's savepoint must leave the
            # transaction usable for the next sections.
            self.env.cr.execute("SELECT 1 / 0")

        with patch.object(Dashboard, "_section_cash_position", missing_rate), \
                patch.object(Dashboard, "_section_reconciliation", crashing):
            self.assertEqual(
                self.Dashboard.get_section_data("cash_position"),
                {"error": "There is no USD exchange rate loaded yet."},
            )
            with mute_logger("odoo.sql_db"), self.assertLogs("odoo.addons.account_treasury_dashboard.models.account_treasury_dashboard",
                                 level="ERROR"):
                result = self.Dashboard.get_section_data("reconciliation")
            self.assertIn("couldn't be computed", result["error"])
            projection = self.Dashboard.get_section_data("projection")
            self.assertNotIn("error", projection)
            self.assertIn("blocks", projection)

    # -------------------------------------------------------------------------
    # Security
    # -------------------------------------------------------------------------

    def test_rpc_requires_a_treasury_group(self):
        self._create_medium("bank", self.bank_journal)
        Dashboard = self.Dashboard.with_user(self.no_group_user)
        with self.assertRaises(AccessError):
            Dashboard.get_dashboard()
        with self.assertRaises(AccessError):
            Dashboard.get_section_data("cash_position")
        with self.assertRaises(AccessError):
            Dashboard.get_drilldown("cash_position", "anything", {})

    def test_dashboard_user_sees_the_dashboard(self):
        self._create_medium("bank", self.bank_journal)
        frame = self.Dashboard.with_user(self.dashboard_user).get_dashboard()
        self.assertIn("cash_position", self._visible(frame))
        self.assertNotIn("error", self.Dashboard.with_user(self.dashboard_user).get_section_data("cash_position"))

    def test_company_not_allowed(self):
        other_company = self.setup_other_company()["company"]
        self.Config.create({"company_id": other_company.id})
        with self.assertRaises(AccessError):
            self.Dashboard.with_user(self.dashboard_user).with_company(other_company).get_dashboard()

    def test_popup_links_only_readable_models(self):
        rows = [{"key": "1", "cells": {}, "record": ("account.move.line", 1)}]

        popup = self.Dashboard._popup("Detail", [], rows, list_model="account.move.line")
        self.assertTrue(popup["list_action"])
        self.assertEqual(popup["rows"][0]["record"], {"model": "account.move.line", "id": 1})

        popup = self.Dashboard.with_user(self.dashboard_user)._popup(
            "Detail", [], rows, list_model="account.move.line",
        )
        self.assertFalse(popup["list_action"])
        self.assertFalse(popup["rows"][0]["record"])
