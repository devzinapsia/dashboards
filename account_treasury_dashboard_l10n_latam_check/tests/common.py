from datetime import timedelta

from odoo import Command

from odoo.addons.account_treasury_dashboard.tests.common import TreasuryDashboardCommon


class TreasuryChecksCommon(TreasuryDashboardCommon):
    """A bank with its outstanding accounts and an own checks payment method,
    a third-party checks journal and a rejected checks journal, configured in
    the treasury settings."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        ref = cls.env.ref
        cls.checks_account = cls._create_account("1.1.1.02.003", "Checks to deposit", "asset_current", reconcile=True)
        cls.deferred_account = cls._create_account("1.1.1.02.004", "Deferred checks", "asset_current", reconcile=True)
        cls.bank, cls.receipts_account, cls.payments_account = cls._setup_bank_with_outstanding("Bank A", "BKA")
        cls.bank.outbound_payment_method_line_ids = [Command.create({
            "payment_method_id": ref("l10n_latam_check.account_payment_method_own_checks").id,
            "name": "Own checks",
            "payment_account_id": cls.deferred_account.id,
        })]

        def check_journal(name, code):
            journal = cls._create_journal(name, code, "cash")
            journal.inbound_payment_method_line_ids = [
                Command.create({"payment_method_id": ref(method).id, "name": method,
                                "payment_account_id": cls.checks_account.id})
                for method in ("l10n_latam_check.account_payment_method_new_third_party_checks",
                               "l10n_latam_check.account_payment_method_in_third_party_checks")
            ]
            journal.outbound_payment_method_line_ids = [Command.create({
                "payment_method_id": ref("l10n_latam_check.account_payment_method_out_third_party_checks").id,
                "name": "Out third-party checks",
                "payment_account_id": cls.checks_account.id,
            })]
            return journal

        cls.checks_journal = check_journal("Third-party checks", "CHT")
        cls.rejected_journal = check_journal("Rejected checks", "CHR")
        cls.config.write({
            "third_party_check_journal_ids": [Command.set(cls.checks_journal.ids)],
            "rejected_check_journal_ids": [Command.set(cls.rejected_journal.ids)],
        })

    def setUp(self):
        super().setUp()
        self.Dashboard = self.env["account.treasury.dashboard"]
        self.bank_medium = self._create_medium("bank", self.bank)

    def _receive_checks(self, checks, partner=None):
        """checks = [(number, days from today, amount)]: a customer receipt
        with third-party checks, in the checks journal."""
        method = self.checks_journal.inbound_payment_method_line_ids.filtered(
            lambda line: line.code == "new_third_party_checks")[:1]
        payment = self.env["account.payment"].create({
            "partner_id": (partner or self.customer).id,
            "payment_type": "inbound",
            "partner_type": "customer",
            "journal_id": self.checks_journal.id,
            "date": self.today,
            "payment_method_line_id": method.id,
            "l10n_latam_new_check_ids": [Command.create({
                "name": number, "payment_date": self.today + timedelta(days=days), "amount": amount,
            }) for number, days, amount in checks],
        })
        payment.action_post()
        return payment.l10n_latam_new_check_ids

    def _transfer(self, checks, journal):
        self.env["l10n_latam.payment.mass.transfer"].with_context(
            active_model="l10n_latam.check", active_ids=checks.ids,
        ).create({"destination_journal_id": journal.id, "payment_date": self.today})._create_payments()

    def _issue_own_checks(self, checks, partner=None):
        method = self.bank.outbound_payment_method_line_ids.filtered(lambda line: line.code == "own_checks")[:1]
        payment = self.env["account.payment"].create({
            "partner_id": (partner or self.vendor).id,
            "payment_type": "outbound",
            "partner_type": "supplier",
            "journal_id": self.bank.id,
            "date": self.today,
            "payment_method_line_id": method.id,
            "l10n_latam_new_check_ids": [Command.create({
                "name": number, "payment_date": self.today + timedelta(days=days), "amount": amount,
            }) for number, days, amount in checks],
        })
        payment.action_post()
        return payment.l10n_latam_new_check_ids
