from contextlib import contextmanager
from datetime import date

from odoo import Command
from odoo.exceptions import ValidationError

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


class TreasuryDashboardCommon(AccountTestInvoicingCommon):
    """Shared fixtures: the standard accounting test company, with an empty
    treasury configuration and the Administrator group on the test user."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.company_data["company"]
        cls.env.user.group_ids += cls.env.ref("account_treasury_dashboard.group_treasury_dashboard_manager")
        cls.Config = cls.env["account.treasury.config"]
        cls.Medium = cls.env["account.treasury.medium"]
        cls.Commitment = cls.env["account.treasury.commitment"]
        cls.config = cls.Config.create({"company_id": cls.company.id})

        cls.bank_journal = cls.company_data["default_journal_bank"]
        cls.cash_journal = cls.company_data["default_journal_cash"]
        cls.credit_journal = cls.company_data["default_journal_credit"]
        cls.misc_journal = cls.company_data["default_journal_misc"]
        # Partners without payment terms, so that due dates are the ones set.
        cls.customer = cls.env["res.partner"].create({"name": "Treasury customer"})
        cls.vendor = cls.env["res.partner"].create({"name": "Treasury vendor"})
        cls.today = date(2026, 10, 14)  # a Wednesday; tests run frozen on this day

    @classmethod
    def _create_account(cls, code, name, account_type, reconcile=False, currency=None):
        return cls.env["account.account"].create({
            "code": code,
            "name": name,
            "account_type": account_type,
            "reconcile": reconcile,
            "currency_id": currency.id if currency else False,
            "company_ids": [Command.link(cls.company.id)],
        })

    @classmethod
    def _create_journal(cls, name, code, journal_type, currency=None):
        return cls.env["account.journal"].create({
            "name": name,
            "code": code,
            "type": journal_type,
            "currency_id": currency.id if currency else False,
            "company_id": cls.company.id,
        })

    @classmethod
    def _create_medium(cls, kind, journal=None, accounts=None, **values):
        return cls.Medium.create({
            "config_id": cls.config.id,
            "name": values.pop("name", journal.name if journal else kind),
            "kind": kind,
            "journal_id": journal.id if journal else False,
            "account_ids": [Command.set(accounts.ids)] if accounts else [],
            **values,
        })

    @contextmanager
    def assertValidationError(self, pattern):
        """Like assertRaisesRegex(ValidationError, pattern), but through
        Odoo's assertRaises, which rolls back a savepoint: unittest's
        assertRaisesRegex doesn't, so the record of a failed create would
        stay in the database for the rest of the test."""
        with self.assertRaises(ValidationError) as context:
            yield context
        self.assertRegex(str(context.exception), pattern)

    # -------------------------------------------------------------------------
    # Accounting fixtures
    # -------------------------------------------------------------------------

    @classmethod
    def _setup_bank_with_outstanding(cls, name, code, currency=None):
        """A bank journal whose payments go through its own outstanding
        receipts/payments accounts (as with Odoo's bank reconciliation)."""
        journal = cls._create_journal(name, code, "bank", currency=currency)
        receipts = cls._create_account("1.1.8.%s1" % code, "Outstanding receipts %s" % name, "asset_current",
                                       reconcile=True)
        payments = cls._create_account("1.1.8.%s2" % code, "Outstanding payments %s" % name, "asset_current",
                                       reconcile=True)
        journal.inbound_payment_method_line_ids.payment_account_id = receipts
        journal.outbound_payment_method_line_ids.payment_account_id = payments
        return journal, receipts, payments

    def _entry(self, date, lines, journal=None, ref=None):
        """A posted journal entry: lines = [(account, balance, {extra})]."""
        move = self.env["account.move"].create({
            "move_type": "entry",
            "date": date,
            "ref": ref,
            "journal_id": (journal or self.misc_journal).id,
            "line_ids": [Command.create({
                "account_id": account.id,
                "balance": balance,
                "name": ref or "/",
                **(extra[0] if extra else {}),
            }) for account, balance, *extra in lines],
        })
        move.action_post()
        return move

    def _payment(self, journal, amount, payment_type="inbound", date=None, partner=None, **values):
        payment = self.env["account.payment"].create({
            "journal_id": journal.id,
            "payment_type": payment_type,
            "partner_type": "customer" if payment_type == "inbound" else "supplier",
            "amount": amount,
            "date": date or self.today,
            "partner_id": (partner or self.customer).id,
            **values,
        })
        payment.action_post()
        return payment

    def _st_line(self, journal, date, amount, statement=None, label="Bank line", **values):
        return self.env["account.bank.statement.line"].create({
            "journal_id": journal.id,
            "date": date,
            "amount": amount,
            "payment_ref": label,
            "statement_id": statement.id if statement else False,
            **values,
        })

    def _statement(self, journal, lines, balance_start=0.0):
        """A statement with lines = [(date, amount)]."""
        st_lines = self.env["account.bank.statement.line"]
        for date, amount in lines:
            st_lines |= self._st_line(journal, date, amount)
        statement = self.env["account.bank.statement"].create({
            "journal_id": journal.id,
            "balance_start": balance_start,
            "line_ids": [Command.set(st_lines.ids)],
        })
        statement.balance_end_real = statement.balance_end
        return statement

    def _match(self, st_line, move_line):
        """Reconcile a statement line with a journal item (e.g. a payment's
        outstanding item): its suspense counterpart is moved to the item's
        account and both are reconciled - what the reconciliation widget
        does, without depending on account_accountant."""
        _liquidity, suspense, _other = st_line._seek_for_lines()
        st_line.move_id.with_context(skip_readonly_check=True).write({"line_ids": [
            Command.update(suspense.id, {"account_id": move_line.account_id.id,
                                         "partner_id": move_line.partner_id.id}),
        ]})
        counterpart = st_line.move_id.line_ids.filtered(lambda line: line.account_id == move_line.account_id)
        (counterpart | move_line).reconcile()

    def _invoice(self, move_type, amount, due_date, partner=None, date=None, currency=None):
        invoice = self.env["account.move"].create({
            "move_type": move_type,
            "partner_id": (partner or (self.customer if move_type.startswith("out") else self.vendor)).id,
            "invoice_date": date or due_date,
            "date": date or due_date,
            "invoice_date_due": due_date,
            "currency_id": (currency or self.company.currency_id).id,
            "invoice_line_ids": [Command.create({
                "name": "Service",
                "quantity": 1,
                "price_unit": amount,
                "tax_ids": [Command.clear()],
            })],
        })
        invoice.action_post()
        return invoice

    @classmethod
    def _outstanding_line(cls, payment):
        return payment.move_id.line_ids.filtered(lambda line: line.account_id == payment.outstanding_account_id)
