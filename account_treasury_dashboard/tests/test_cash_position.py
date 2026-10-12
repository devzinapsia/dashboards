from datetime import date

from freezegun import freeze_time

from odoo import Command
from odoo.tests import tagged

from .common import TreasuryDashboardCommon


class TreasuryBankScenario(TreasuryDashboardCommon):
    """A bank with a statement, a line without statement, a matched and two
    unmatched payments and a miscellaneous operation:

    - bank account: 1,000 - 200 (statement) + 50 + 100 (lines without
      statement) + 30 (misc. operation) = 980
    - in transit: +300 receipt, -120 payment
    - book balance: 1,160; last statement: 800; difference: 360
      = 150 (without statement) + 30 (misc.) + 300 - 120
    """

    def setUp(self):
        super().setUp()
        self.Dashboard = self.env["account.treasury.dashboard"]
        self.bank, self.receipts_account, self.payments_account = self._setup_bank_with_outstanding("Bank A", "BKA")
        self.bank_medium = self._create_medium("bank", self.bank)
        self.statement = self._statement(self.bank, [(date(2026, 10, 1), 1000.0), (date(2026, 10, 5), -200.0)])
        self._st_line(self.bank, date(2026, 10, 10), 50.0)
        matched_line = self._st_line(self.bank, date(2026, 10, 12), 100.0)
        self._match(matched_line, self._outstanding_line(self._payment(self.bank, 100.0, date=date(2026, 10, 11))))
        self.pending_receipt = self._payment(self.bank, 300.0, date=date(2026, 10, 13))
        self.pending_payment = self._payment(self.bank, 120.0, "outbound", date=date(2026, 10, 13),
                                             partner=self.vendor)
        self.other_account = self._create_account("3.1.1.01", "Capital", "equity")
        self._entry(date(2026, 10, 13), [(self.bank.default_account_id, 30.0), (self.other_account, -30.0)])

    def _ctx(self):
        return self.Dashboard._prepare_context()


@freeze_time("2026-10-14 12:00:00")
@tagged("post_install", "-at_install")
class TestCashPosition(TreasuryBankScenario):

    def test_bank_figures(self):
        figures = self.Dashboard._compute_banks(self._ctx(), self.bank_medium)[self.bank_medium.id]
        self.assertAlmostEqual(figures["liquidity"], 980.0)
        self.assertAlmostEqual(figures["receipts"], 300.0)
        self.assertAlmostEqual(figures["payments"], -120.0)
        self.assertAlmostEqual(figures["book"], 1160.0)
        self.assertAlmostEqual(figures["statement"], 800.0)
        self.assertEqual(figures["statement_date"], date(2026, 10, 5))
        self.assertAlmostEqual(figures["without_statement"], 150.0)
        self.assertAlmostEqual(figures["misc"], 30.0)
        self.assertAlmostEqual(figures["unexplained"], 0.0)
        self.assertAlmostEqual(figures["difference"], 360.0)

    def test_difference_popup_adds_up(self):
        popup = self.Dashboard.get_drilldown("cash_position", "difference", {"medium_id": self.bank_medium.id})
        self.assertAlmostEqual(sum(row["cells"]["amount"]["value"] for row in popup["rows"]), 360.0)
        self.assertAlmostEqual(popup["total"]["value"], 360.0)

    def test_in_transit_popup_lists_pending_payments(self):
        popup = self.Dashboard.get_drilldown("cash_position", "in_transit", {"medium_id": self.bank_medium.id})
        self.assertEqual(len(popup["rows"]), 2)
        self.assertAlmostEqual(popup["total"]["value"], 180.0)
        self.assertEqual({row["record"]["id"] for row in popup["rows"]},
                         {self.pending_receipt.id, self.pending_payment.id})

    def test_liquidity_popup_adds_up(self):
        popup = self.Dashboard.get_drilldown("cash_position", "liquidity", {"medium_id": self.bank_medium.id})
        self.assertAlmostEqual(popup["total"]["value"], 980.0)
        items = self.env["account.move.line"].search(popup["list_action"]["domain"])
        self.assertAlmostEqual(sum(items.mapped("balance")), 980.0)
        # Each month opens that month's journal items.
        for row in popup["rows"]:
            month_items = self.env["account.move.line"].search(row["action"]["domain"])
            self.assertAlmostEqual(sum(month_items.mapped("balance")), row["cells"]["amount"]["value"])
            self.assertEqual(len(set(month_items.mapped(lambda line: line.date.strftime("%Y-%m")))), 1)

    def test_scope_with_in_transit_items(self):
        """Own accounts OR (journal AND outstanding accounts): the popup and
        its list cover the bank account and the pending payments."""
        ctx = self._ctx()
        scope = self.Dashboard._get_scope(self.bank_medium)[self.bank_medium.id]
        items = self.env["account.move.line"].search([
            ("parent_state", "=", "posted"), *self.Dashboard._scope_domain(scope),
        ])
        self.assertEqual(items.account_id, self.bank.default_account_id | self.receipts_account | self.payments_account)
        # Matched payment: its outstanding item and the statement's counterpart cancel out.
        self.assertAlmostEqual(sum(items.mapped("balance")),
                               self.Dashboard._compute_banks(ctx, self.bank_medium)[self.bank_medium.id]["book"])

    def test_bank_without_statement(self):
        empty_bank = self._create_journal("Bank B", "BKB", "bank")
        medium = self._create_medium("bank", empty_bank)
        figures = self.Dashboard._compute_banks(self._ctx(), medium)[medium.id]
        self.assertIsNone(figures["statement"])
        self.assertIsNone(figures["difference"])
        section = self.Dashboard.get_section_data("cash_position")
        self.assertNotIn("error", section)
        banks_table = next(block for block in section["blocks"] if block.get("title") == "Banks")
        row = next(row for row in banks_table["rows"] if row["key"] == "medium-%s" % medium.id)
        self.assertEqual(row["cells"]["statement"]["value"], "No statement")

    def test_cash_and_total_available(self):
        cash = self._create_medium("cash", self.cash_journal)
        self._entry(date(2026, 10, 2), [(self.cash_journal.default_account_id, 500.0), (self.other_account, -500.0)])
        section = self.Dashboard.get_section_data("cash_position")
        total = section["blocks"][0]["items"][0]["main"]["value"]
        self.assertAlmostEqual(total, 1160.0 + 500.0)
        cash_table = next(block for block in section["blocks"] if block.get("title") == "Cash")
        self.assertAlmostEqual(cash_table["rows"][0]["cells"]["liquidity"]["value"], 500.0)

        cash.in_available_total = False
        section = self.Dashboard.get_section_data("cash_position")
        self.assertAlmostEqual(section["blocks"][0]["items"][0]["main"]["value"], 1160.0)
        popup = self.Dashboard.get_drilldown("cash_position", "available", {})
        self.assertAlmostEqual(popup["total"]["value"], 1160.0)

    def test_total_banks_row(self):
        section = self.Dashboard.get_section_data("cash_position")
        banks_table = next(block for block in section["blocks"] if block.get("title") == "Banks")
        total = banks_table["rows"][-1]
        self.assertEqual(total["style"], "total")
        self.assertAlmostEqual(total["cells"]["book"]["value"], 1160.0)

    def test_foreign_currency(self):
        eur = self.setup_other_currency("EUR", rates=[("2026-01-01", 0.6), ("2026-10-14", 0.5)])
        eur_bank = self._create_journal("Bank EUR", "BEUR", "bank", currency=eur)
        eur_medium = self._create_medium("bank", eur_bank)
        # 100 EUR booked at an older rate: 180 in the company currency.
        self._entry(date(2026, 9, 1), [
            (eur_bank.default_account_id, 180.0, {"currency_id": eur.id, "amount_currency": 100.0}),
            (self.other_account, -180.0),
        ])
        figures = self.Dashboard._compute_banks(self._ctx(), eur_medium)[eur_medium.id]
        self.assertAlmostEqual(figures["liquidity"], 100.0)  # in EUR
        section = self.Dashboard.get_section_data("cash_position")
        foreign = next(block for block in section["blocks"] if block.get("title") == "Foreign currency")
        cells = foreign["rows"][0]["cells"]
        self.assertAlmostEqual(cells["original"]["value"], 100.0)
        self.assertAlmostEqual(cells["equivalent"]["value"], 200.0)  # 1 EUR = 2 at today's rate
        self.assertAlmostEqual(cells["book"]["value"], 180.0)
        self.assertAlmostEqual(cells["difference"]["value"], 20.0)
        self.assertAlmostEqual(section["blocks"][0]["items"][0]["main"]["value"], 1160.0 + 200.0)

    def test_missing_rate_only_breaks_its_sections(self):
        gbp = self.setup_other_currency("GBP", rates=[])
        gbp_cash = self._create_journal("Cash GBP", "CGBP", "cash", currency=gbp)
        self._create_medium("cash", gbp_cash)
        section = self.Dashboard.get_section_data("cash_position")
        self.assertIn("no GBP exchange rate", section["error"])
        self.assertNotIn("error", self.Dashboard.get_section_data("reconciliation"))
        self.assertNotIn("error", self.Dashboard.get_section_data("movements"))


@freeze_time("2026-10-14 12:00:00")
@tagged("post_install", "-at_install")
class TestFundsAndCards(TreasuryDashboardCommon):

    def setUp(self):
        super().setUp()
        self.Dashboard = self.env["account.treasury.dashboard"]
        self.bank_medium = self._create_medium("bank", self.bank_journal)
        self.bank_account = self.bank_journal.default_account_id
        self.expense = self.company_data["default_account_expense"]

    def test_petty_cash_refill_by_internal_transfer(self):
        petty_journal = self._create_journal("Petty cash", "PC1", "cash")
        petty = self._create_medium("petty_cash", petty_journal)
        petty_account = petty_journal.default_account_id
        self._entry(date(2026, 10, 8), [(petty_account, 200.0), (self.bank_account, -200.0)])
        self._entry(date(2026, 10, 10), [(self.expense, 50.0), (petty_account, -50.0)])
        ctx = self.Dashboard._prepare_context()
        refill = self.Dashboard._read_last_refills(ctx, petty)[petty.id]
        self.assertEqual(refill["date"], date(2026, 10, 8))
        self.assertAlmostEqual(refill["amount"], 200.0)
        self.assertAlmostEqual(self.Dashboard._compute_book_balances(ctx, petty)[petty.id]["book"], 150.0)

    def test_refill_through_the_transfer_account(self):
        petty_journal = self._create_journal("Petty cash", "PC1", "cash")
        petty = self._create_medium("petty_cash", petty_journal)
        transfer_account = self.company.transfer_account_id
        self._entry(date(2026, 10, 9), [(petty_journal.default_account_id, 75.0), (transfer_account, -75.0)])
        refill = self.Dashboard._read_last_refills(self.Dashboard._prepare_context(), petty)[petty.id]
        self.assertEqual(refill["date"], date(2026, 10, 9))
        self.assertAlmostEqual(refill["amount"], 75.0)

    def test_no_refills(self):
        petty_journal = self._create_journal("Petty cash", "PC1", "cash")
        petty = self._create_medium("petty_cash", petty_journal)
        self._entry(date(2026, 10, 10), [(self.expense, 50.0), (petty_journal.default_account_id, -50.0)])
        self.assertFalse(self.Dashboard._read_last_refills(self.Dashboard._prepare_context(), petty))
        section = self.Dashboard.get_section_data("cash_position")
        funds = next(block for block in section["blocks"] if block.get("title") == "Petty cash funds and prepaid cards")
        self.assertEqual(funds["rows"][0]["cells"]["refill_date"]["value"], "No refills")

    def test_prepaid_without_journal(self):
        prepaid_account = self._create_account("1.1.9.01", "Prepaid card", "asset_current")
        prepaid = self._create_medium("prepaid", accounts=prepaid_account, name="Prepaid")
        self._entry(date(2026, 10, 2), [(prepaid_account, 300.0), (self.bank_account, -300.0)])
        self._entry(date(2026, 10, 6), [(self.expense, 40.0), (prepaid_account, -40.0)])
        ctx = self.Dashboard._prepare_context()
        refill = self.Dashboard._read_last_refills(ctx, prepaid)[prepaid.id]
        self.assertEqual(refill["date"], date(2026, 10, 2))
        self.assertAlmostEqual(refill["amount"], 300.0)
        self.assertAlmostEqual(self.Dashboard._compute_book_balances(ctx, prepaid)[prepaid.id]["book"], 260.0)

    def _setup_card(self):
        card = self._create_medium("credit_card", self.credit_journal, closing_day=5, due_day=15, credit_limit=1000)
        card_account = self.credit_journal.default_account_id
        self._entry(date(2026, 9, 20), [(self.expense, 400.0), (card_account, -400.0)])  # closed cycle
        self._entry(date(2026, 10, 8), [(self.expense, 250.0), (card_account, -250.0)])  # current cycle
        self._entry(date(2026, 10, 10), [(card_account, 50.0), (self.expense, -50.0)])  # refund
        self._entry(date(2026, 10, 12), [(card_account, 100.0), (self.bank_account, -100.0)])  # payment
        return card

    def test_credit_card(self):
        card = self._setup_card()
        figures = self.Dashboard._compute_cards(self.Dashboard._prepare_context(), card)[card.id]
        self.assertEqual(figures["last_closing"], date(2026, 10, 5))
        self.assertEqual(figures["next_closing"], date(2026, 11, 5))
        self.assertEqual(figures["next_due"], date(2026, 11, 15))
        self.assertAlmostEqual(figures["consumption"], 200.0)  # payment left out
        self.assertAlmostEqual(figures["debt"], 500.0)
        self.assertAlmostEqual(figures["closed_unpaid"], 300.0)
        self.assertEqual(figures["next_payment_due"], date(2026, 10, 15))
        self.assertEqual(figures["days_to_due"], 1)
        self.assertAlmostEqual(figures["available"], 500.0)

    def test_card_with_two_journals_on_the_same_account(self):
        """One payment mean for the card account, two cardholders' journals:
        the account's balance counted once, the in-transit items of both
        journals included."""
        card_account = self._create_account("2.1.2.01.011", "Visa card payable", "liability_credit_card")
        journals = self.env["account.journal"]
        for name, code in (("Visa - Chelo", "VCH"), ("Visa - Pablo", "VPA")):
            journal = self._create_journal(name, code, "credit")
            journal.default_account_id = card_account
            journals |= journal
        card = self._create_medium("credit_card", name="Visa Galicia", closing_day=5, due_day=15,
                                   credit_limit=1000, journal_ids=[Command.set(journals.ids)])
        self._entry(date(2026, 10, 8), [(self.expense, 250.0), (card_account, -250.0)], journal=journals[0])
        self._entry(date(2026, 10, 9), [(self.expense, 100.0), (card_account, -100.0)], journal=journals[1])
        ctx = self.Dashboard._prepare_context()
        self.assertEqual(card._get_journals(), journals)
        figures = self.Dashboard._compute_cards(ctx, card)[card.id]
        self.assertAlmostEqual(figures["debt"], 350.0)
        self.assertAlmostEqual(figures["consumption"], 350.0)
        scope = self.Dashboard._get_scope(card)[card.id]
        self.assertEqual({journal_id for journal_id, _accounts in scope["outstanding"]},
                         set(journal.id for journal in journals if journal._get_journal_outbound_outstanding_payment_accounts()
                             | journal._get_journal_inbound_outstanding_payment_accounts()))

    def test_credit_card_popups(self):
        card = self._setup_card()
        cycle = self.Dashboard.get_drilldown("cash_position", "card_cycle", {"medium_id": card.id})
        self.assertEqual(len(cycle["rows"]), 2)
        self.assertAlmostEqual(cycle["total"]["value"], 200.0)
        debt = self.Dashboard.get_drilldown("cash_position", "card_debt", {"medium_id": card.id})
        self.assertAlmostEqual(debt["total"]["value"], 500.0)
