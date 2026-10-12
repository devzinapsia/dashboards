from odoo import models
from odoo.exceptions import UserError
from odoo.fields import Domain
from odoo.tools import SQL, format_date

from . import treasury_blocks as blocks
from . import treasury_dates


class AccountTreasuryDashboard(models.AbstractModel):
    """Section "Cash position", as of today.

    Banks follow Odoo's bank reconciliation report (account_reports):

    - bank account balance: the journal's default account (statement lines
      are posted to it as soon as they are imported);
    - in transit: outstanding receipts/payments (see _read_in_transit);
    - book balance = bank account balance + in transit;
    - last statement balance: ending balance of the statement of the
      latest statement line that belongs to a statement;
    - difference = book balance - last statement balance, explained by the
      transactions without statement, the miscellaneous operations on the
      bank account, the in-transit items and the unexplained remainder
      (the report's "journal balance" warning).
    """

    _inherit = "account.treasury.dashboard"

    # -------------------------------------------------------------------------
    # Bank reconciliation figures
    # -------------------------------------------------------------------------

    def _read_last_statements(self, ctx, journals):
        """{journal_id: account.bank.statement} of the statement of each
        journal's latest statement line with a statement (as the report)."""
        if not journals:
            return {}
        self.env["account.bank.statement.line"].flush_model()
        rows = self.env.execute_query(SQL(
            """
            SELECT DISTINCT ON (st_line.journal_id) st_line.journal_id, st_line.statement_id
              FROM account_bank_statement_line st_line
              JOIN account_move move ON move.id = st_line.move_id
             WHERE st_line.journal_id = ANY(%(journals)s)
               AND st_line.statement_id IS NOT NULL
               AND move.date <= %(today)s
          ORDER BY st_line.journal_id, move.date DESC, st_line.id DESC
            """,
            journals=journals.ids,
            today=ctx["today"],
        ))
        Statement = self.env["account.bank.statement"].sudo()
        return {journal_id: Statement.browse(statement_id) for journal_id, statement_id in rows}

    def _read_transactions_without_statement(self, ctx, journals):
        """{journal_id: sum of the posted statement lines not in a statement}."""
        if not journals:
            return {}
        self.env["account.bank.statement.line"].flush_model()
        return dict(self.env.execute_query(SQL(
            """
            SELECT st_line.journal_id, SUM(st_line.amount)
              FROM account_bank_statement_line st_line
              JOIN account_move move ON move.id = st_line.move_id
             WHERE st_line.journal_id = ANY(%(journals)s)
               AND st_line.statement_id IS NULL
               AND move.state = 'posted'
               AND move.date <= %(today)s
          GROUP BY st_line.journal_id
            """,
            journals=journals.ids,
            today=ctx["today"],
        )))

    def _misc_operations_domain(self, ctx, journal):
        """Journal items on the bank account that don't come from a bank
        statement line, as the report's "Misc. operations": after the fiscal
        lock date, without the opening entry nor the exchange difference
        journal."""
        company = ctx["company"]
        domain = [
            ("company_id", "=", company.id),
            ("account_id", "=", journal.default_account_id.id),
            ("statement_line_id", "=", False),
            ("parent_state", "=", "posted"),
            ("date", "<=", ctx["today"]),
        ]
        lock_date = company._get_user_fiscal_lock_date(journal)
        if lock_date and lock_date.year > 1:
            domain.append(("date", ">", lock_date))
        if company.account_opening_move_id:
            domain.append(("move_id", "!=", company.account_opening_move_id.id))
        if company.currency_exchange_journal_id:
            domain.append(("journal_id", "!=", company.currency_exchange_journal_id.id))
        return domain

    def _read_misc_operations(self, ctx, journal):
        lines = self.env["account.move.line"].sudo().search_fetch(
            self._misc_operations_domain(ctx, journal), ["amount_currency", "balance"],
        )
        return sum(line.amount_currency or line.balance for line in lines)

    def _compute_banks(self, ctx, mediums):
        """Figures of each bank and cash payment mean, in its own currency:
        {medium_id: {"liquidity", "receipts", "payments", "book", "statement",
        "statement_date", "without_statement", "misc", "unexplained",
        "difference", "in_transit_lines"}}."""
        liquidity = self._read_liquidity_balances(ctx, mediums)
        in_transit = self._read_in_transit(ctx, mediums)
        bank_mediums = mediums.filtered(lambda medium: medium.kind == "bank")
        statements = self._read_last_statements(ctx, bank_mediums.journal_id)
        without_statement = self._read_transactions_without_statement(ctx, bank_mediums.journal_id)
        result = {}
        for medium in mediums:
            balance = liquidity[medium.id]
            bank_balance = self._medium_amount(medium, balance["balance"], balance["amount_currency"])
            transit = in_transit[medium.id]
            figures = {
                "liquidity": bank_balance,
                "liquidity_company": balance["balance"],
                "receipts": transit["receipts"],
                "payments": transit["payments"],
                "in_transit": transit["receipts"] + transit["payments"],
                "in_transit_company": transit["receipts_company"] + transit["payments_company"],
                "book": bank_balance + transit["receipts"] + transit["payments"],
                "book_company": balance["balance"] + transit["receipts_company"] + transit["payments_company"],
                "in_transit_lines": transit["lines"],
                "statement": None,
                "statement_date": None,
                "statement_id": False,
                "difference": None,
            }
            if medium.kind == "bank":
                statement = statements.get(medium.journal_id.id)
                figures["without_statement"] = without_statement.get(medium.journal_id.id) or 0.0
                figures["misc"] = self._read_misc_operations(ctx, medium.journal_id)
                if statement:
                    figures["statement"] = statement.balance_end_real
                    figures["statement_date"] = statement.date
                    figures["statement_id"] = statement.id
                    figures["unexplained"] = bank_balance - (
                        statement.balance_end_real + figures["without_statement"] + figures["misc"]
                    )
                    figures["difference"] = figures["book"] - statement.balance_end_real
            result[medium.id] = figures
        return result

    def _compute_book_balances(self, ctx, mediums):
        """Book balance (own accounts + in transit) of any payment means:
        {medium_id: {"book" (own currency), "book_company" (accounting)}}."""
        liquidity = self._read_liquidity_balances(ctx, mediums)
        in_transit = self._read_in_transit(ctx, mediums)
        result = {}
        for medium in mediums:
            balance = liquidity[medium.id]
            transit = in_transit[medium.id]
            result[medium.id] = {
                "book": self._medium_amount(medium, balance["balance"], balance["amount_currency"])
                + transit["receipts"] + transit["payments"],
                "book_company": balance["balance"] + transit["receipts_company"] + transit["payments_company"],
            }
        return result

    def _valued(self, ctx, medium, amount):
        """An amount in the payment mean's currency valued in the company
        currency at the rate of the day."""
        return ctx["rates"].to_company(amount, medium.currency_id)

    # -------------------------------------------------------------------------
    # Petty cash funds, prepaid cards and credit cards
    # -------------------------------------------------------------------------

    def _read_last_refills(self, ctx, mediums):
        """{medium_id: {"date", "amount", "move_id"}} of the last refill of
        each petty cash fund / prepaid card: the latest internal transfer
        bringing money into it. A prepaid card without a journal has no
        transfer of its own to follow: its last load is approximated by the
        latest entry debiting its accounts."""
        if not mediums:
            return {}
        liquid = self._get_liquid_mediums(ctx["config"])
        moves = self._read_move_nets(ctx, liquid | mediums, focus=mediums)
        liquid_ids = set(liquid.ids)
        result = {}
        for move in reversed(moves):
            for medium in mediums:
                if medium.id in result:
                    continue
                net = move["nets"].get(medium.id)
                if not net or net["balance"] <= 0:
                    continue
                if medium.journal_id and not self._is_internal_transfer(ctx, move, liquid_ids):
                    continue
                result[medium.id] = {
                    "date": move["date"],
                    "amount": self._medium_amount(medium, net["balance"], net["amount_currency"]),
                    "move_id": move["move_id"],
                }
            if len(result) == len(mediums):
                break
        return result

    def _card_dates(self, medium, today):
        last_closing, next_closing = treasury_dates.card_closing_dates(today, medium.closing_day)
        return {
            "last_closing": last_closing,
            "next_closing": next_closing,
            "last_due": treasury_dates.card_due_date(last_closing, medium.due_day),
            "next_due": treasury_dates.card_due_date(next_closing, medium.due_day),
        }

    def _card_cycle_moves(self, ctx, card, date_from):
        """Entries of the card's current cycle (after ``date_from``, the last
        closing) that are purchases or refunds, i.e. not a payment of the
        card from a bank or cash (an entry also moving a liquid payment mean
        or the internal transfer account)."""
        liquid = self._get_liquid_mediums(ctx["config"])
        liquid_ids = set(liquid.ids)
        currency = ctx["currency"]
        moves = self._read_move_nets(ctx, liquid | card, date_from=date_from, focus=card)
        return [
            move for move in moves
            if move["date"] > date_from
            and card.id in move["nets"]
            and not move["has_transfer_account"]
            and not any(not currency.is_zero(net["balance"])
                        for medium_id, net in move["nets"].items() if medium_id in liquid_ids)
        ]

    def _compute_cards(self, ctx, cards):
        """Figures of each credit card in its own currency: consumption of the
        current cycle (net credits since the last closing, card payments
        left out), total debt, cycle dates, limit and available credit."""
        books = self._compute_book_balances(ctx, cards)
        result = {}
        for card in cards:
            dates = self._card_dates(card, ctx["today"])
            moves = self._card_cycle_moves(ctx, card, dates["last_closing"])
            consumption = -sum(
                self._medium_amount(card, move["nets"][card.id]["balance"], move["nets"][card.id]["amount_currency"])
                for move in moves
            )
            debt = -books[card.id]["book"]
            closed_unpaid = max(debt - consumption, 0.0)
            # The next statement to pay: the closed one while it isn't paid
            # and not past due, otherwise the current cycle's.
            if closed_unpaid > 0 and dates["last_due"] >= ctx["today"]:
                next_due = dates["last_due"]
            else:
                next_due = dates["next_due"]
            result[card.id] = {
                **dates,
                "consumption": consumption,
                "debt": debt,
                "closed_unpaid": closed_unpaid,
                "next_payment_due": next_due,
                "days_to_due": (next_due - ctx["today"]).days,
                "limit": card.credit_limit,
                "available": card.credit_limit - debt,
                "moves": moves,
            }
        return result

    # -------------------------------------------------------------------------
    # Section
    # -------------------------------------------------------------------------

    def _section_cash_position(self, ctx):
        config = ctx["config"]
        currency = ctx["currency"]
        rates = ctx["rates"]
        alerts = []
        result_blocks = []
        bank_cash = self._get_mediums(config, ("bank", "cash"))
        funds = self._get_mediums(config, ("petty_cash", "prepaid"))
        cards = self._get_mediums(config, ("credit_card",))
        available = self._get_mediums(config, available_only=True)

        # Total available and foreign currencies.
        books = self._compute_book_balances(ctx, available)
        total_available = sum(self._valued(ctx, medium, books[medium.id]["book"]) for medium in available)
        cards_items = [blocks.card(
            self.env._("Total available"),
            blocks.money(total_available, currency, drilldown=blocks.drilldown("available")),
            blocks.value(self.env._("1 payment mean") if len(available) == 1
                         else self.env._("%s payment means", len(available)), "text"),
        )]
        foreign = {}
        for medium in available.filtered(lambda medium: medium.currency_id != currency):
            entry = foreign.setdefault(medium.currency_id, {"original": 0.0, "book": 0.0})
            entry["original"] += books[medium.id]["book"]
            entry["book"] += books[medium.id]["book_company"]
        foreign_rows = []
        for foreign_currency, entry in sorted(foreign.items(), key=lambda item: item[0].name):
            rate, rate_date = rates.get(foreign_currency)
            equivalent = entry["original"] * rate
            difference = equivalent - entry["book"]
            stale = rates.is_stale(foreign_currency)
            foreign_rows.append(blocks.row(foreign_currency.name, {
                "currency": blocks.value(foreign_currency.name),
                "original": blocks.money(entry["original"], foreign_currency,
                                         drilldown=blocks.drilldown("currency", currency_id=foreign_currency.id)),
                "rate": blocks.value(rate, "float", note=self.env._(
                    "Rate of %s", format_date(self.env, rate_date)), alert="warning" if stale else None),
                "equivalent": blocks.money(equivalent, currency),
                "book": blocks.money(entry["book"], currency),
                "difference": blocks.money(difference, currency),
            }))
            if stale:
                alerts.append(blocks.alert("info", self.env._(
                    "%(currency)s valued at the rate of %(date)s, the latest one loaded.",
                    currency=foreign_currency.name, date=format_date(self.env, rate_date),
                )))
        result_blocks.append(blocks.cards_block(cards_items))

        # Banks and cash.
        if bank_cash:
            banks = self._compute_banks(ctx, bank_cash)
            banks_only = bank_cash.filtered(lambda medium: medium.kind == "bank")
            if banks_only:
                result_blocks.append(
                    self._bank_cash_table(ctx, "bank", self.env._("Banks"), banks_only, banks, alerts))
            cash_only = bank_cash.filtered(lambda medium: medium.kind == "cash")
            if cash_only:
                result_blocks.append(
                    self._bank_cash_table(ctx, "cash", self.env._("Cash"), cash_only, banks, alerts))

        if foreign_rows:
            result_blocks.append(blocks.table_block(
                [
                    blocks.column("currency", self.env._("Currency")),
                    blocks.column("original", self.env._("Original amount"), "monetary"),
                    blocks.column("rate", self.env._("Rate of the day"), "float"),
                    blocks.column("equivalent", self.env._("Equivalent in %s", currency.name), "monetary"),
                    blocks.column("book", self.env._("Book value"), "monetary"),
                    blocks.column("difference", self.env._("Unrecognized exchange difference"), "monetary"),
                ],
                foreign_rows,
                title=self.env._("Foreign currency"),
                note=self.env._(
                    "Payment means in the available total whose account is in a foreign currency. The difference "
                    "between the equivalent at the rate of the day and the book value is the exchange difference "
                    "not booked yet."
                ),
            ))

        if funds:
            result_blocks.append(self._funds_table(ctx, funds))
        if cards:
            result_blocks.append(self._cards_table(ctx, cards, alerts))
        return {"alerts": alerts, "blocks": result_blocks}

    def _bank_cash_table(self, ctx, kind, title, mediums, banks, alerts):
        currency = ctx["currency"]
        is_bank = kind == "bank"
        rows = []
        totals = dict.fromkeys(("liquidity", "in_transit", "book", "statement", "difference"), 0.0)
        for medium in mediums:
            figures = banks[medium.id]
            medium_currency = medium.currency_id

            def drill(key, medium=medium):
                return blocks.drilldown(key, medium_id=medium.id)

            cells = {
                "name": blocks.value(medium.name),
                "currency": blocks.value(medium_currency.name),
                "liquidity": blocks.money(figures["liquidity"], medium_currency, drilldown=drill("liquidity")),
                "in_transit": blocks.money(figures["in_transit"], medium_currency, drilldown=drill("in_transit")),
                "book": blocks.money(figures["book"], medium_currency),
            }
            for key in ("liquidity", "in_transit", "book"):
                totals[key] += self._valued(ctx, medium, figures[key])
            if is_bank:
                if figures["statement_id"]:
                    cells["statement"] = blocks.money(figures["statement"], medium_currency, drilldown=drill("statement"))
                    cells["statement_date"] = blocks.value(figures["statement_date"], "date")
                    cells["difference"] = blocks.money(
                        figures["difference"], medium_currency, drilldown=drill("difference"),
                        alert="warning" if not medium_currency.is_zero(figures["difference"]) else None,
                    )
                    totals["statement"] += self._valued(ctx, medium, figures["statement"])
                    totals["difference"] += self._valued(ctx, medium, figures["difference"])
                else:
                    cells["statement"] = blocks.value(self.env._("No statement"), "text")
                    cells["statement_date"] = blocks.value(False, "date")
                    cells["difference"] = blocks.value(False, "monetary")
            rows.append(blocks.row("medium-%s" % medium.id, cells))
        total_label = self.env._("Total banks") if is_bank else self.env._("Total cash")
        total_cells = {
            "name": blocks.value(total_label),
            "currency": blocks.value(currency.name),
            **{key: blocks.money(totals[key], currency) for key in ("liquidity", "in_transit", "book")},
        }
        if is_bank:
            total_cells.update({
                "statement": blocks.money(totals["statement"], currency),
                "statement_date": blocks.value(False, "text"),
                "difference": blocks.money(totals["difference"], currency),
            })
        rows.append(blocks.row("total-%s" % kind, total_cells, style="total"))
        columns = [
            blocks.column("name", self.env._("Payment mean")),
            blocks.column("currency", self.env._("Currency")),
            blocks.column("liquidity", self.env._("Bank account balance") if is_bank
                          else self.env._("Account balance"), "monetary"),
            blocks.column("in_transit", self.env._("In transit"), "monetary"),
            blocks.column("book", self.env._("Book balance"), "monetary"),
        ]
        if is_bank:
            columns += [
                blocks.column("statement", self.env._("Last statement balance"), "monetary"),
                blocks.column("statement_date", self.env._("Statement date"), "date"),
                blocks.column("difference", self.env._("Difference"), "monetary"),
            ]
        note = None
        if len(mediums.currency_id) > 1 or mediums.currency_id != currency:
            note = self.env._("Totals in %s, foreign currencies valued at the rate of the day.", currency.name)
        return blocks.table_block(columns, rows, title=title, note=note)

    def _funds_table(self, ctx, funds):
        books = self._compute_book_balances(ctx, funds)
        refills = self._read_last_refills(ctx, funds)
        rows = []
        for medium in funds:
            refill = refills.get(medium.id)
            cells = {
                "name": blocks.value(medium.name),
                "kind": blocks.value(medium._kind_label()),
                "balance": blocks.money(books[medium.id]["book"], medium.currency_id,
                                        drilldown=blocks.drilldown("liquidity", medium_id=medium.id)),
            }
            if refill:
                cells.update({
                    "refill_date": blocks.value(refill["date"], "date",
                                                drilldown=blocks.drilldown("refill", medium_id=medium.id)),
                    "refill_amount": blocks.money(refill["amount"], medium.currency_id),
                    "refill_days": blocks.value((ctx["today"] - refill["date"]).days, "days"),
                })
            else:
                cells.update({
                    "refill_date": blocks.value(self.env._("No refills"), "text"),
                    "refill_amount": blocks.value(False, "monetary"),
                    "refill_days": blocks.value(False, "days"),
                })
            rows.append(blocks.row("medium-%s" % medium.id, cells))
        return blocks.table_block(
            [
                blocks.column("name", self.env._("Payment mean")),
                blocks.column("kind", self.env._("Type")),
                blocks.column("balance", self.env._("Balance"), "monetary"),
                blocks.column("refill_date", self.env._("Last refill"), "date"),
                blocks.column("refill_amount", self.env._("Refill amount"), "monetary"),
                blocks.column("refill_days", self.env._("Days since"), "days"),
            ],
            rows,
            title=self.env._("Petty cash funds and prepaid cards"),
            note=self.env._(
                "The last refill is the latest internal transfer into the fund or card. For a prepaid card without "
                "a journal, the latest entry debiting its accounts."
            ),
        )

    def _cards_table(self, ctx, cards, alerts):
        figures = self._compute_cards(ctx, cards)
        rows = []
        for card in cards:
            card_figures = figures[card.id]
            card_currency = card.currency_id
            over_limit = card.credit_limit and card_figures["available"] < 0
            if over_limit:
                alerts.append(blocks.alert("danger", self.env._("%s is over its credit limit.", card.name)))
            rows.append(blocks.row("medium-%s" % card.id, {
                "name": blocks.value(card.name),
                "consumption": blocks.money(card_figures["consumption"], card_currency,
                                            drilldown=blocks.drilldown("card_cycle", medium_id=card.id)),
                "debt": blocks.money(card_figures["debt"], card_currency,
                                     drilldown=blocks.drilldown("card_debt", medium_id=card.id)),
                "last_closing": blocks.value(card_figures["last_closing"], "date"),
                "next_closing": blocks.value(card_figures["next_closing"], "date"),
                "next_due": blocks.value(card_figures["next_payment_due"], "date"),
                "days_to_due": blocks.value(card_figures["days_to_due"], "days",
                                            alert="warning" if card_figures["days_to_due"] <= 3 else None),
                "limit": blocks.money(card.credit_limit, card_currency),
                "available": blocks.money(card_figures["available"], card_currency,
                                          alert="danger" if over_limit else None),
            }))
        return blocks.table_block(
            [
                blocks.column("name", self.env._("Credit card")),
                blocks.column("consumption", self.env._("Current cycle"), "monetary"),
                blocks.column("debt", self.env._("Total debt"), "monetary"),
                blocks.column("last_closing", self.env._("Last closing"), "date"),
                blocks.column("next_closing", self.env._("Next closing"), "date"),
                blocks.column("next_due", self.env._("Next due date"), "date"),
                blocks.column("days_to_due", self.env._("Days to due date"), "days"),
                blocks.column("limit", self.env._("Limit"), "monetary"),
                blocks.column("available", self.env._("Available"), "monetary"),
            ],
            rows,
            title=self.env._("Credit cards"),
            note=self.env._(
                "Current cycle: purchases net of refunds since the last closing (payments of the card are left "
                "out). Available: limit minus total debt."
            ),
        )

    # -------------------------------------------------------------------------
    # Drill-down
    # -------------------------------------------------------------------------

    def _get_medium(self, ctx, medium_id):
        medium = ctx["config"].medium_ids.filtered(lambda medium: medium.id == medium_id and medium.active)
        if not medium:
            raise UserError(self.env._("This payment mean is no longer configured. Refresh the dashboard."))
        return medium

    def _scope_domain(self, medium_scope, parts=("own", "outstanding")):
        """account.move.line domain of a payment mean's scope (see
        _get_scope()), as a list."""
        domains = []
        if "own" in parts and medium_scope["own"]:
            domains.append(Domain("account_id", "in", medium_scope["own"]))
        if "outstanding" in parts:
            for journal_id, account_ids in medium_scope["outstanding"]:
                domains.append(Domain("journal_id", "=", journal_id) & Domain("account_id", "in", account_ids))
        return list(Domain.OR(domains)) if domains else list(Domain.FALSE)

    def _monthly_popup(self, ctx, medium, title, parts=("own",), sign=1, date_to=None):
        """Popup of a payment mean's balance split by month, with the journal
        items list behind it."""
        scope = self._get_scope(medium)[medium.id]
        domain = list(Domain.AND([
            [("company_id", "=", ctx["company"].id),
             ("parent_state", "=", "posted"),
             ("date", "<=", date_to or ctx["today"])],
            self._scope_domain(scope, parts),
        ]))
        foreign = medium.currency_id != ctx["currency"]
        rows = self.env["account.move.line"].sudo()._read_group(
            domain, groupby=["date:month"], aggregates=["balance:sum", "amount_currency:sum"], order="date:month",
        )
        popup_rows = []
        total = 0.0
        for month, balance, amount_currency in rows:
            amount = sign * (amount_currency if foreign else balance)
            total += amount
            popup_rows.append({"key": str(month), "cells": {
                "month": blocks.value(format_date(self.env, month, date_format="MMMM yyyy")),
                "amount": blocks.money(amount, medium.currency_id),
            }})
        return self._popup(
            title,
            [blocks.column("month", self.env._("Month")),
             blocks.column("amount", self.env._("Movements"), "monetary")],
            popup_rows,
            total=blocks.money(total, medium.currency_id),
            list_model="account.move.line",
            list_domain=domain,
            list_name=title,
        )

    def _moves_popup(self, ctx, title, entries, currency, list_domain=None):
        """Popup listing journal entries: entries = [(move_id, date, amount)]."""
        described = self._describe_moves([move_id for move_id, _date, _amount in entries])
        rows = [{
            "key": str(move_id),
            "cells": {
                "date": blocks.value(date, "date"),
                "document": blocks.value(described[move_id]["name"]),
                "reference": blocks.value(described[move_id]["ref"]),
                "partner": blocks.value(described[move_id]["partner"]),
                "amount": blocks.money(amount, currency),
            },
            "record": ("account.move", move_id),
        } for move_id, date, amount in entries]
        return self._popup(
            title,
            [blocks.column("date", self.env._("Date"), "date"),
             blocks.column("document", self.env._("Document")),
             blocks.column("reference", self.env._("Reference")),
             blocks.column("partner", self.env._("Partner")),
             blocks.column("amount", self.env._("Amount"), "monetary")],
            rows,
            total=blocks.money(sum(amount for _move, _date, amount in entries), currency),
            list_model="account.move.line" if list_domain else None,
            list_domain=list_domain,
        )

    def _in_transit_popup(self, ctx, medium, lines, title):
        rows = []
        for line in lines:
            record = ("account.payment", line["payment_id"]) if line["payment_id"] else ("account.move", line["move_id"])
            rows.append({"key": str(line["id"]), "record": record, "cells": {
                "date": blocks.value(line["date"], "date"),
                "document": blocks.value(line["move_name"] or ""),
                "partner": blocks.value(
                    self.env["res.partner"].sudo().browse(line["partner_id"]).display_name if line["partner_id"] else ""),
                "kind": blocks.value(self.env._("Receipt") if line["balance"] > 0 else self.env._("Payment")),
                "amount": blocks.money(line["medium_amount"], medium.currency_id),
            }})
        return self._popup(
            title,
            [blocks.column("date", self.env._("Date"), "date"),
             blocks.column("document", self.env._("Document")),
             blocks.column("partner", self.env._("Partner")),
             blocks.column("kind", self.env._("Type")),
             blocks.column("amount", self.env._("Amount"), "monetary")],
            rows,
            total=blocks.money(sum(line["medium_amount"] for line in lines), medium.currency_id),
            list_model="account.move.line",
            list_domain=[("id", "in", [line["id"] for line in lines])],
        )

    def _drilldown_cash_position(self, key, params, ctx):
        currency = ctx["currency"]
        if key == "available":
            available = self._get_mediums(ctx["config"], available_only=True)
            books = self._compute_book_balances(ctx, available)
            rows = [{"key": str(medium.id), "cells": {
                "name": blocks.value(medium.name),
                "kind": blocks.value(medium._kind_label()),
                "book": blocks.money(books[medium.id]["book"], medium.currency_id),
                "amount": blocks.money(self._valued(ctx, medium, books[medium.id]["book"]), currency),
            }} for medium in available]
            return self._popup(
                self.env._("Total available"),
                [blocks.column("name", self.env._("Payment mean")),
                 blocks.column("kind", self.env._("Type")),
                 blocks.column("book", self.env._("Book balance"), "monetary"),
                 blocks.column("amount", self.env._("In %s", currency.name), "monetary")],
                rows,
                total=blocks.money(sum(row["cells"]["amount"]["value"] for row in rows), currency),
            )
        if key == "currency":
            foreign_currency = self.env["res.currency"].browse(params["currency_id"])
            available = self._get_mediums(ctx["config"], available_only=True).filtered(
                lambda medium: medium.currency_id == foreign_currency)
            books = self._compute_book_balances(ctx, available)
            rows = [{"key": str(medium.id), "cells": {
                "name": blocks.value(medium.name),
                "amount": blocks.money(books[medium.id]["book"], foreign_currency),
            }} for medium in available]
            return self._popup(
                self.env._("Payment means in %s", foreign_currency.name),
                [blocks.column("name", self.env._("Payment mean")),
                 blocks.column("amount", self.env._("Book balance"), "monetary")],
                rows,
                total=blocks.money(sum(books[medium.id]["book"] for medium in available), foreign_currency),
            )

        medium = self._get_medium(ctx, params.get("medium_id"))
        if key == "liquidity":
            parts = ("own",) if medium.kind in ("bank", "cash") else ("own", "outstanding")
            return self._monthly_popup(ctx, medium, medium.name, parts=parts)
        if key == "card_debt":
            return self._monthly_popup(ctx, medium, self.env._("%s: total debt", medium.name),
                                       parts=("own", "outstanding"), sign=-1)
        if key == "in_transit":
            lines = self._read_in_transit(ctx, medium)[medium.id]["lines"]
            return self._in_transit_popup(ctx, medium, lines, self.env._("%s: in transit", medium.name))
        if key == "statement":
            figures = self._compute_banks(ctx, medium)[medium.id]
            statement = self.env["account.bank.statement"].sudo().browse(figures["statement_id"])
            st_lines = statement.line_ids.filtered(lambda st_line: st_line.state == "posted")
            rows = [{"key": str(st_line.id), "record": ("account.bank.statement.line", st_line.id), "cells": {
                "date": blocks.value(st_line.date, "date"),
                "label": blocks.value(st_line.payment_ref or ""),
                "partner": blocks.value(st_line.partner_id.display_name or ""),
                "reconciled": blocks.value(self.env._("Yes") if st_line.is_reconciled else self.env._("No")),
                "amount": blocks.money(st_line.amount, medium.currency_id),
            }} for st_line in st_lines.sorted(lambda st_line: (st_line.date, st_line.id))]
            rows.insert(0, {"key": "start", "cells": {
                "date": blocks.value(False, "date"),
                "label": blocks.value(self.env._("Starting balance")),
                "partner": blocks.value(""),
                "reconciled": blocks.value(""),
                "amount": blocks.money(statement.balance_start, medium.currency_id),
            }})
            return self._popup(
                self.env._("%(bank)s: statement %(statement)s", bank=medium.name, statement=statement.display_name),
                [blocks.column("date", self.env._("Date"), "date"),
                 blocks.column("label", self.env._("Label")),
                 blocks.column("partner", self.env._("Partner")),
                 blocks.column("reconciled", self.env._("Reconciled")),
                 blocks.column("amount", self.env._("Amount"), "monetary")],
                rows,
                total=blocks.money(statement.balance_end_real, medium.currency_id),
                list_model="account.bank.statement.line",
                list_domain=[("statement_id", "=", statement.id)],
            )
        if key == "difference":
            figures = self._compute_banks(ctx, medium)[medium.id]
            components = [
                ("without_statement", self.env._("Transactions without statement"), figures["without_statement"]),
                ("misc", self.env._("Miscellaneous operations on the bank account"), figures["misc"]),
                ("unexplained", self.env._("Unexplained difference"), figures["unexplained"]),
                ("receipts", self.env._("(+) Outstanding receipts"), figures["receipts"]),
                ("payments", self.env._("(-) Outstanding payments"), figures["payments"]),
            ]
            rows = [{"key": component_key, "cells": {
                "component": blocks.value(label),
                "amount": blocks.money(amount, medium.currency_id),
            }} for component_key, label, amount in components]
            return self._popup(
                self.env._("%s: book balance vs last statement", medium.name),
                [blocks.column("component", self.env._("Item")),
                 blocks.column("amount", self.env._("Amount"), "monetary")],
                rows,
                total=blocks.money(figures["difference"], medium.currency_id),
            )
        if key == "refill":
            refill = self._read_last_refills(ctx, medium).get(medium.id)
            entries = [(refill["move_id"], refill["date"], refill["amount"])] if refill else []
            return self._moves_popup(ctx, self.env._("%s: last refill", medium.name), entries, medium.currency_id)
        if key == "card_cycle":
            figures = self._compute_cards(ctx, medium)[medium.id]
            entries = [(move["move_id"], move["date"], -self._medium_amount(
                medium, move["nets"][medium.id]["balance"], move["nets"][medium.id]["amount_currency"]))
                for move in figures["moves"]]
            return self._moves_popup(
                ctx, self.env._("%s: current cycle", medium.name), entries, medium.currency_id,
                list_domain=list(Domain.AND([
                    [("move_id", "in", [move["move_id"] for move in figures["moves"]])],
                    self._scope_domain(self._get_scope(medium)[medium.id]),
                ])),
            )
        raise UserError(self.env._("This figure has no detail."))
