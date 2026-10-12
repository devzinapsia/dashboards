from collections import defaultdict

from odoo import models
from odoo.tools import SQL

from .account_treasury_medium import LIQUID_KINDS


class AccountTreasuryDashboard(models.AbstractModel):
    """Data layer shared by the sections: which journal items belong to
    which payment mean, and their balances.

    A payment mean's journal items ("scope") are:
    - liquidity: the items of its own accounts (its journal's default
      account and its extra accounts), whatever their journal;
    - in transit: the items of its journals (its own journal, and the other
      journals booking on its accounts) on each journal's outstanding
      receipts/payments accounts (the payment method lines' accounts).
      Those accounts are usually shared by several journals, so they are
      always filtered by journal, as Odoo's bank reconciliation report does.

    Every method here runs a fixed number of SQL queries, whatever the
    number of journal items.
    """

    _inherit = "account.treasury.dashboard"

    # -------------------------------------------------------------------------
    # Scope
    # -------------------------------------------------------------------------

    def _get_outstanding_accounts(self, journal, own_accounts):
        accounts = (journal._get_journal_inbound_outstanding_payment_accounts()
                    | journal._get_journal_outbound_outstanding_payment_accounts())
        # A cash journal may use its own cash account as payment account:
        # it is then liquidity, not in transit.
        return accounts - own_accounts

    def _get_scope(self, mediums):
        """{medium_id: {"own": account ids, "outstanding": [(journal id,
        account ids)]}}: the in-transit accounts of each of the payment
        mean's journals (see account.treasury.medium._get_journals()),
        filtered by that journal."""
        mediums = mediums.sudo()
        all_own = self.env["account.account"]
        for medium in mediums:
            all_own |= medium._get_own_accounts()
        scope = {}
        for medium in mediums:
            outstanding = []
            for journal in medium._get_journals():
                accounts = self._get_outstanding_accounts(journal, all_own)
                if accounts:
                    outstanding.append((journal.id, accounts.ids))
            scope[medium.id] = {"own": medium._get_own_accounts().ids, "outstanding": outstanding}
        return scope

    def _scope_sql(self, scope, alias="aml", parts=("own", "outstanding")):
        """(condition, medium id CASE expression) selecting the scope's
        journal items in an account_move_line query."""
        conditions = []
        cases = []
        for medium_id, medium_scope in scope.items():
            if "own" in parts and medium_scope["own"]:
                condition = SQL("%s.account_id = ANY(%s)", SQL.identifier(alias), medium_scope["own"])
                conditions.append(condition)
                cases.append(SQL("WHEN %s THEN %s", condition, medium_id))
            if "outstanding" in parts:
                for journal_id, account_ids in medium_scope["outstanding"]:
                    condition = SQL(
                        "(%s.journal_id = %s AND %s.account_id = ANY(%s))",
                        SQL.identifier(alias), journal_id, SQL.identifier(alias), account_ids,
                    )
                    conditions.append(condition)
                    cases.append(SQL("WHEN %s THEN %s", condition, medium_id))
        if not conditions:
            return SQL("FALSE"), SQL("NULL::int")
        return SQL("(%s)", SQL(" OR ").join(conditions)), SQL("CASE %s END", SQL(" ").join(cases))

    def _medium_amount(self, medium, balance, amount_currency):
        """An amount in the payment mean's own currency: the original amount
        for a foreign currency payment mean, the accounting balance otherwise."""
        return amount_currency if medium.currency_id != medium.company_id.currency_id else balance

    # -------------------------------------------------------------------------
    # Balances
    # -------------------------------------------------------------------------

    def _read_liquidity_balances(self, ctx, mediums, date_to=None):
        """Balance of each payment mean's own accounts up to ``date_to``
        (posted entries): {medium_id: {"balance", "amount_currency"}}."""
        result = {medium.id: {"balance": 0.0, "amount_currency": 0.0} for medium in mediums}
        scope = self._get_scope(mediums)
        condition, medium_case = self._scope_sql(scope, parts=("own",))
        self.env["account.move.line"].flush_model()
        rows = self.env.execute_query_dict(SQL(
            """
            SELECT %(medium_case)s AS medium_id,
                   SUM(aml.balance) AS balance,
                   SUM(aml.amount_currency) AS amount_currency
              FROM account_move_line aml
             WHERE aml.company_id = %(company)s
               AND aml.parent_state = 'posted'
               AND aml.date <= %(date_to)s
               AND %(condition)s
          GROUP BY 1
            """,
            medium_case=medium_case,
            company=ctx["company"].id,
            date_to=date_to or ctx["today"],
            condition=condition,
        ))
        for row in rows:
            if row["medium_id"] in result:
                result[row["medium_id"]] = {"balance": row["balance"] or 0.0,
                                            "amount_currency": row["amount_currency"] or 0.0}
        return result

    def _read_outstanding_lines(self, ctx, mediums, extra_condition=None):
        """Recorded receipts/payments of each payment mean's journal not
        matched with a bank statement yet (Odoo's bank reconciliation report
        "Outstanding receipts/payments"): items of the journal's outstanding
        accounts, not fully reconciled, with a residual amount.

        :return: one dict per journal item, with its medium_id and amounts.
        """
        scope = self._get_scope(mediums)
        condition, medium_case = self._scope_sql(scope, parts=("outstanding",))
        self.env["account.move.line"].flush_model()
        return self.env.execute_query_dict(SQL(
            """
            SELECT %(medium_case)s AS medium_id,
                   aml.id, aml.move_id, aml.payment_id, aml.partner_id, aml.date, aml.date_maturity,
                   aml.move_name, aml.ref, aml.name AS label, aml.currency_id, aml.account_id,
                   account.reconcile AS is_account_reconcile,
                   aml.balance, aml.amount_currency, aml.amount_residual, aml.amount_residual_currency
              FROM account_move_line aml
              JOIN account_account account ON account.id = aml.account_id
             WHERE aml.company_id = %(company)s
               AND aml.parent_state = 'posted'
               AND aml.date <= %(today)s
               AND aml.full_reconcile_id IS NULL
               AND aml.amount_residual_currency != 0
               AND %(condition)s
               AND %(extra)s
          ORDER BY aml.date, aml.id
            """,
            medium_case=medium_case,
            company=ctx["company"].id,
            today=ctx["today"],
            condition=condition,
            extra=extra_condition or SQL("TRUE"),
        ))

    def _outstanding_amounts(self, ctx, medium, line):
        """(amount in the payment mean's currency, amount in the company
        currency) of an outstanding item, as the bank reconciliation report
        computes it: its residual (or, on an account that can't be
        reconciled, its amount), in the item's own currency when it is the
        journal's, converted otherwise."""
        reconcile = line["is_account_reconcile"]
        company_amount = line["amount_residual"] if reconcile else line["balance"]
        if line["currency_id"] == medium.currency_id.id:
            medium_amount = line["amount_residual_currency"] if reconcile else line["amount_currency"]
        else:
            rate, _date = ctx["rates"].get(medium.currency_id)
            medium_amount = company_amount / rate
        return medium_amount, company_amount

    def _read_in_transit(self, ctx, mediums):
        """{medium_id: {"receipts", "payments"} in the payment mean's currency
        and {"receipts_company", "payments_company"}}, plus the lines."""
        result = {
            medium.id: {"receipts": 0.0, "payments": 0.0, "receipts_company": 0.0, "payments_company": 0.0,
                        "lines": []}
            for medium in mediums
        }
        by_id = {medium.id: medium for medium in mediums}
        for line in self._read_outstanding_lines(ctx, mediums):
            medium = by_id.get(line["medium_id"])
            if not medium:
                continue
            medium_amount, company_amount = self._outstanding_amounts(ctx, medium, line)
            key = "receipts" if line["balance"] > 0 else "payments"
            result[medium.id][key] += medium_amount
            result[medium.id][key + "_company"] += company_amount
            result[medium.id]["lines"].append({**line, "medium_amount": medium_amount,
                                               "company_amount": company_amount})
        return result

    # -------------------------------------------------------------------------
    # Movements by journal entry
    # -------------------------------------------------------------------------

    def _get_liquid_mediums(self, config):
        """Payment means holding money of the company, whatever their
        "available total" flag: movements between two of them are internal
        transfers."""
        return self._get_mediums(config, LIQUID_KINDS)

    def _read_move_nets(self, ctx, mediums, date_from=None, date_to=None, focus=None):
        """Net movement of each journal entry on each payment mean's scope
        (own accounts and in-transit accounts together), in the period.

        Netting by entry is what keeps a bank statement reconciliation (an
        entry moving an amount from the outstanding account to the bank
        account of the same journal) out of the figures: its net is zero.

        :param focus: payment means whose entries are wanted; the nets of
            every payment mean in ``mediums`` are still returned for those
            entries, so that transfers can be told apart.
        :return: list of {"move_id", "date", "nets": {medium_id: {"balance",
            "amount_currency"}}, "has_transfer_account"}, by date.
        """
        scope = self._get_scope(mediums)
        condition, medium_case = self._scope_sql(scope)
        focus_condition = SQL("TRUE")
        if focus is not None:
            focus_scope = {medium_id: scope[medium_id] for medium_id in focus.ids if medium_id in scope}
            focus_sql, _case = self._scope_sql(focus_scope, alias="focus_aml")
            focus_condition = SQL(
                "aml.move_id IN (SELECT focus_aml.move_id FROM account_move_line focus_aml "
                "WHERE focus_aml.company_id = %s AND %s)",
                ctx["company"].id, focus_sql,
            )
        transfer_account = ctx["company"].transfer_account_id
        self.env["account.move.line"].flush_model()
        rows = self.env.execute_query_dict(SQL(
            """
            SELECT aml.move_id, aml.date,
                   %(medium_case)s AS medium_id,
                   SUM(aml.balance) AS balance,
                   SUM(aml.amount_currency) AS amount_currency,
                   EXISTS(
                       SELECT 1 FROM account_move_line transfer_aml
                        WHERE transfer_aml.move_id = aml.move_id
                          AND transfer_aml.account_id = %(transfer_account)s
                   ) AS has_transfer_account
              FROM account_move_line aml
             WHERE aml.company_id = %(company)s
               AND aml.parent_state = 'posted'
               AND aml.date >= %(date_from)s
               AND aml.date <= %(date_to)s
               AND %(condition)s
               AND %(focus)s
          GROUP BY aml.move_id, aml.date, 3
          ORDER BY aml.date, aml.move_id
            """,
            medium_case=medium_case,
            transfer_account=transfer_account.id or 0,
            company=ctx["company"].id,
            date_from=date_from or "1900-01-01",
            date_to=date_to or ctx["today"],
            condition=condition,
            focus=focus_condition,
        ))
        moves = {}
        for row in rows:
            move = moves.setdefault(row["move_id"], {
                "move_id": row["move_id"],
                "date": row["date"],
                "nets": {},
                "has_transfer_account": row["has_transfer_account"],
            })
            move["nets"][row["medium_id"]] = {"balance": row["balance"] or 0.0,
                                              "amount_currency": row["amount_currency"] or 0.0}
        return list(moves.values())

    def _is_internal_transfer(self, ctx, move, liquid_ids):
        """Whether a journal entry is an internal transfer:

        - it has an item on the company's internal transfer account (Odoo's
          bank reconciliation "internal transfer" model, and the paired
          payments of internal transfer modules such as ingadhoc's
          account_internal_transfer, which use that account as counterpart);
        - or it moves money between at least two of the company's liquid
          payment means (bank, cash, petty cash, prepaid card, investment;
          never a credit card, so paying a card statement is an outflow)
          and nets to zero across them.
        """
        if move["has_transfer_account"]:
            return True
        currency = ctx["currency"]
        liquid_nets = [net["balance"] for medium_id, net in move["nets"].items()
                       if medium_id in liquid_ids and not currency.is_zero(net["balance"])]
        return len(liquid_nets) >= 2 and currency.is_zero(sum(liquid_nets))

    def _describe_moves(self, move_ids):
        """{move_id: {"name", "ref", "partner"}} of journal entries, read once."""
        moves = self.env["account.move"].sudo().browse(move_ids)
        return {move.id: {"name": move.name, "ref": move.ref or "", "partner": move.partner_id.display_name or ""}
                for move in moves}
