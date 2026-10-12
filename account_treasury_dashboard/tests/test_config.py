from odoo import Command
from odoo.exceptions import AccessError
from odoo.tests import new_test_user, tagged

from .common import TreasuryDashboardCommon


@tagged("post_install", "-at_install")
class TestTreasuryConfig(TreasuryDashboardCommon):

    # -------------------------------------------------------------------------
    # Configuration
    # -------------------------------------------------------------------------

    def test_single_active_config_per_company(self):
        with self.assertValidationError("already has an active treasury dashboard configuration"):
            self.Config.create({"company_id": self.company.id})
        # An archived one is fine, and so is another company's.
        self.Config.create({"company_id": self.company.id, "active": False})
        other_company = self.setup_other_company()["company"]
        self.Config.create({"company_id": other_company.id})

    def test_projection_weeks_bounds(self):
        for weeks in (4, 8):
            self.config.projection_weeks = weeks
        for weeks in (3, 9):
            with self.assertValidationError("between 4 and 8 weeks"):
                self.config.projection_weeks = weeks

    def test_statement_stale_days_positive(self):
        with self.assertValidationError("at least 1"):
            self.config.statement_stale_days = 0

    def test_action_open_config_reuses_company_config(self):
        action = self.Config.action_open_config()
        self.assertEqual(action["res_id"], self.config.id)
        self.assertFalse(action["context"]["create"])
        self.assertFalse(action["context"]["delete"])

    def test_action_open_config_creates_missing_config(self):
        self.config.active = False
        action = self.Config.action_open_config()
        new_config = self.Config.browse(action["res_id"])
        self.assertTrue(new_config.active)
        self.assertNotEqual(new_config, self.config)

    # -------------------------------------------------------------------------
    # Payment means
    # -------------------------------------------------------------------------

    def test_in_available_total_default_by_kind(self):
        bank = self._create_medium("bank", self.bank_journal)
        cash = self._create_medium("cash", self.cash_journal)
        card = self._create_medium("credit_card", self.credit_journal, closing_day=20, due_day=5)
        self.assertTrue(bank.in_available_total)
        self.assertTrue(cash.in_available_total)
        self.assertFalse(card.in_available_total)

    def test_journal_required_kinds(self):
        for kind in ("bank", "cash", "petty_cash", "investment"):
            with self.assertValidationError("needs a journal"):
                self._create_medium(kind, name=kind)

    def test_prepaid_and_card_need_journal_or_accounts(self):
        with self.assertValidationError("needs a journal, accounts, or both"):
            self._create_medium("prepaid", name="Prepaid")
        with self.assertValidationError("needs a journal, accounts, or both"):
            self._create_medium("credit_card", name="Card", closing_day=20, due_day=5)
        account = self._create_account("1.1.9.01", "Prepaid card", "asset_current")
        prepaid = self._create_medium("prepaid", accounts=account, name="Prepaid")
        self.assertFalse(prepaid.journal_id)

    def test_journal_type_matches_kind(self):
        cases = [
            ("bank", self.cash_journal),
            ("cash", self.bank_journal),
            ("petty_cash", self.bank_journal),
            ("prepaid", self.credit_journal),
            ("credit_card", self.bank_journal),
            ("investment", self.cash_journal),
        ]
        for kind, journal in cases:
            with self.assertValidationError("needs a journal of type"):
                self._create_medium(kind, journal, closing_day=20, due_day=5)
        # Allowed combinations.
        investment_journal = self._create_journal("Investment", "INV1", "general")
        self._create_medium("investment", investment_journal)
        self._create_medium("petty_cash", self._create_journal("Petty cash", "PC1", "cash"))
        self._create_medium("prepaid", self._create_journal("Prepaid", "PP1", "bank"))
        self._create_medium("credit_card", self.credit_journal, closing_day=20, due_day=5)

    def test_journal_in_two_mediums(self):
        self._create_medium("bank", self.bank_journal, name="Bank A")
        with self.assertValidationError("already used by payment mean Bank A"):
            self._create_medium("bank", self.bank_journal, name="Bank B")

    def test_archived_medium_frees_its_journal(self):
        medium = self._create_medium("bank", self.bank_journal, name="Bank A")
        medium.active = False
        self._create_medium("bank", self.bank_journal, name="Bank B")
        with self.assertValidationError("already used by payment mean Bank B"):
            medium.active = True

    def test_account_in_two_mediums(self):
        account = self._create_account("1.1.9.01", "Prepaid card", "asset_current")
        self._create_medium("prepaid", accounts=account, name="Prepaid A")
        with self.assertValidationError("already used by payment mean Prepaid A"):
            self._create_medium("prepaid", accounts=account, name="Prepaid B")

    def test_account_shared_with_a_journal_default_account(self):
        self._create_medium("bank", self.bank_journal, name="Bank A")
        with self.assertValidationError("already used by payment mean Bank A"):
            self._create_medium("prepaid", accounts=self.bank_journal.default_account_id, name="Prepaid")

    def test_account_in_medium_and_commitment(self):
        account = self._create_account("2.1.9.01", "Card liability", "liability_current")
        self._create_medium("credit_card", accounts=account, name="Card", closing_day=20, due_day=5)
        with self.assertValidationError("already used by payment mean Card"):
            self.Commitment.create({
                "config_id": self.config.id, "name": "Taxes", "account_ids": [Command.set(account.ids)],
                "payment_day": 10,
            })

    def test_card_days_and_limit(self):
        for closing_day, due_day in ((0, 5), (32, 5), (20, 0), (20, 32)):
            with self.assertValidationError("between 1 and 31"):
                self._create_medium("credit_card", self.credit_journal, closing_day=closing_day, due_day=due_day)
        with self.assertValidationError("credit limit can't be negative"):
            self._create_medium("credit_card", self.credit_journal, closing_day=20, due_day=5, credit_limit=-1)
        card = self._create_medium("credit_card", self.credit_journal, closing_day=31, due_day=10,
                                   credit_limit=1000)
        self.assertEqual(card.credit_limit, 1000)

    def test_medium_currency_from_journal_or_account(self):
        usd = self.setup_other_currency("USD", rates=[("2000-01-01", 0.001)])
        usd_journal = self._create_journal("Bank USD", "BUSD", "bank", currency=usd)
        self.assertEqual(self._create_medium("bank", usd_journal).currency_id, usd)
        usd_account = self._create_account("1.1.9.02", "USD prepaid", "asset_current", currency=usd)
        self.assertEqual(self._create_medium("prepaid", accounts=usd_account).currency_id, usd)
        self.assertEqual(self._create_medium("bank", self.bank_journal).currency_id, self.company.currency_id)

    # -------------------------------------------------------------------------
    # Commitments
    # -------------------------------------------------------------------------

    def test_commitment_mode_from_reconcile(self):
        reconcilable = self._create_account("2.1.5.01", "Taxes payable", "liability_current", reconcile=True)
        not_reconcilable = self._create_account("2.1.4.01", "Salaries payable", "liability_current")
        commitment = self.Commitment.create({
            "config_id": self.config.id, "name": "Taxes", "kind": "tax",
            "account_ids": [Command.set(reconcilable.ids)],
        })
        self.assertEqual(commitment.mode, "open_items")
        with self.assertValidationError("needs a payment day"):
            commitment.account_ids = [Command.link(not_reconcilable.id)]
        commitment.write({"account_ids": [Command.link(not_reconcilable.id)], "payment_day": 5})
        self.assertEqual(commitment.mode, "balance")
        self.assertTrue(self.config.has_balance_commitments)

    def test_commitment_payment_day_bounds(self):
        account = self._create_account("2.1.4.01", "Salaries payable", "liability_current")
        with self.assertValidationError("between 1 and 31"):
            self.Commitment.create({
                "config_id": self.config.id, "name": "Salaries", "kind": "payroll",
                "account_ids": [Command.set(account.ids)], "payment_day": 32,
            })

    def test_account_in_two_commitments(self):
        account = self._create_account("2.1.4.01", "Salaries payable", "liability_current")
        self.Commitment.create({
            "config_id": self.config.id, "name": "Salaries", "account_ids": [Command.set(account.ids)],
            "payment_day": 5,
        })
        with self.assertValidationError("already used by projection commitment Salaries"):
            self.Commitment.create({
                "config_id": self.config.id, "name": "Bonus", "account_ids": [Command.set(account.ids)],
                "payment_day": 5,
            })
        with self.assertValidationError("already used by projection commitment Salaries"):
            self._create_medium("prepaid", accounts=account, name="Prepaid")

    # -------------------------------------------------------------------------
    # Load suggested
    # -------------------------------------------------------------------------

    def test_load_suggested_without_duplicates(self):
        second_bank = self._create_journal("Second bank", "BNK9", "bank")
        existing = self._create_medium("bank", self.bank_journal, name="My bank", in_available_total=False)
        archived = self._create_medium("cash", self.cash_journal, name="Old cash")
        archived.active = False

        self.config.action_load_suggested()
        mediums = self.config.with_context(active_test=False).medium_ids
        bank_journals = self.env["account.journal"].search([
            ("company_id", "=", self.company.id), ("type", "in", ("bank", "cash")),
        ])
        # Every bank/cash journal exactly once; existing ones untouched.
        self.assertEqual(sorted(mediums.journal_id.ids), sorted(bank_journals.ids))
        self.assertEqual(len(mediums), len(bank_journals))
        self.assertEqual(existing.name, "My bank")
        self.assertFalse(existing.in_available_total)
        self.assertFalse(archived.active)
        new_medium = mediums.filtered(lambda medium: medium.journal_id == second_bank)
        self.assertEqual(new_medium.kind, "bank")
        self.assertTrue(new_medium.in_available_total)

        # A second click adds nothing.
        self.config.action_load_suggested()
        self.assertEqual(len(self.config.with_context(active_test=False).medium_ids), len(bank_journals))

    # -------------------------------------------------------------------------
    # Security
    # -------------------------------------------------------------------------

    def test_dashboard_user_has_no_access_to_configuration(self):
        user = new_test_user(
            self.env, login="treasury_user", groups="account_treasury_dashboard.group_treasury_dashboard_user",
            company_id=self.company.id, company_ids=[Command.set(self.company.ids)],
        )
        for model in ("account.treasury.config", "account.treasury.medium", "account.treasury.commitment"):
            with self.assertRaises(AccessError):
                self.env[model].with_user(user).search([])

    def test_configuration_isolated_by_company(self):
        other_company = self.setup_other_company()["company"]
        other_config = self.Config.create({"company_id": other_company.id})
        manager = new_test_user(
            self.env, login="treasury_manager",
            groups="account_treasury_dashboard.group_treasury_dashboard_manager",
            company_id=self.company.id, company_ids=[Command.set(self.company.ids)],
        )
        visible = self.Config.with_user(manager).search([])
        self.assertIn(self.config, visible)
        self.assertNotIn(other_config, visible)
