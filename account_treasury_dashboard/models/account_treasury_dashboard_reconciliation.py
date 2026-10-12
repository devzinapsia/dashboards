from datetime import timedelta

from odoo import models
from odoo.exceptions import UserError
from odoo.tools import SQL
from odoo.tools.translate import LazyTranslate

from . import treasury_blocks as blocks

_lt = LazyTranslate(__name__)

# Age brackets of the unreconciled statement lines, by the line's date:
# (key, label, minimum days, maximum days or None for no limit). One
# statement per bracket: the translation extractor would otherwise take the
# keys that follow a translated label in the same list for labels too.
_BUCKET_0_7 = ("0_7", _lt("0-7 days"), 0, 7)
_BUCKET_8_30 = ("8_30", _lt("8-30 days"), 8, 30)
_BUCKET_31_60 = ("31_60", _lt("31-60 days"), 31, 60)
_BUCKET_OVER_60 = ("over_60", _lt("Over 60 days"), 61, None)
AGING_BUCKETS = [_BUCKET_0_7, _BUCKET_8_30, _BUCKET_31_60, _BUCKET_OVER_60]


class AccountTreasuryDashboard(models.AbstractModel):
    """Section "Reconciliation": per bank, the statement lines not
    reconciled yet (account.bank.statement.line.is_reconciled = False) by
    age, and how old the latest statement line is.

    "Latest statement" is the date of the bank's latest posted statement
    line, whether it belongs to a statement or not: online synchronization
    and file imports create lines without a statement, a statement's own
    date is the date of its last line anyway, and the creation date would
    hide an old file imported today.
    """

    _inherit = "account.treasury.dashboard"

    def _bucket_sql(self, today):
        cases = []
        for key, _label, minimum, maximum in AGING_BUCKETS:
            if maximum is None:
                cases.append(SQL("WHEN %s::date - st_line_move.date >= %s THEN %s", today, minimum, key))
            else:
                cases.append(SQL("WHEN %s::date - st_line_move.date BETWEEN %s AND %s THEN %s", today, minimum, maximum, key))
        return SQL("CASE %s END", SQL(" ").join(cases))

    def _unreconciled_domain(self, ctx, journal, bucket=None):
        domain = [
            ("journal_id", "=", journal.id),
            ("is_reconciled", "=", False),
            ("state", "=", "posted"),
            ("date", "<=", ctx["today"]),
        ]
        if bucket:
            _key, _label, minimum, maximum = next(entry for entry in AGING_BUCKETS if entry[0] == bucket)
            domain.append(("date", "<=", ctx["today"] - timedelta(days=minimum)))
            if maximum is not None:
                domain.append(("date", ">=", ctx["today"] - timedelta(days=maximum)))
        return domain

    def _read_unreconciled(self, ctx, journals):
        """{journal_id: {bucket: (count, amount)}}: amounts are what is left
        to reconcile, in the journal's currency (as the report)."""
        self.env["account.bank.statement.line"].flush_model()
        rows = self.env.execute_query(SQL(
            """
            SELECT st_line.journal_id, %(bucket)s AS bucket, COUNT(*), SUM(-st_line.amount_residual)
              FROM account_bank_statement_line st_line
              JOIN account_move st_line_move ON st_line_move.id = st_line.move_id
             WHERE st_line.journal_id = ANY(%(journals)s)
               AND st_line.is_reconciled IS NOT TRUE
               AND st_line_move.state = 'posted'
               AND st_line_move.date <= %(today)s
          GROUP BY 1, 2
            """,
            bucket=self._bucket_sql(ctx["today"]),
            journals=journals.ids,
            today=ctx["today"],
        ))
        result = {}
        for journal_id, bucket, count, amount in rows:
            result.setdefault(journal_id, {})[bucket] = (count, amount or 0.0)
        return result

    def _read_last_statement_line_dates(self, ctx, journals):
        self.env["account.bank.statement.line"].flush_model()
        return dict(self.env.execute_query(SQL(
            """
            SELECT st_line.journal_id, MAX(st_line_move.date)
              FROM account_bank_statement_line st_line
              JOIN account_move st_line_move ON st_line_move.id = st_line.move_id
             WHERE st_line.journal_id = ANY(%(journals)s)
               AND st_line_move.state = 'posted'
               AND st_line_move.date <= %(today)s
          GROUP BY 1
            """,
            journals=journals.ids,
            today=ctx["today"],
        )))

    def _stale_days(self, ctx, medium):
        return medium.stale_days or ctx["config"].statement_stale_days

    def _section_reconciliation(self, ctx):
        config = ctx["config"]
        currency = ctx["currency"]
        banks = self._get_mediums(config, ("bank",))
        unreconciled = self._read_unreconciled(ctx, banks.journal_id)
        last_dates = self._read_last_statement_line_dates(ctx, banks.journal_id)
        alerts = []
        rows = []
        bucket_totals = {key: [0, 0.0] for key, *_rest in AGING_BUCKETS}
        grand_count = 0
        grand_amount = 0.0
        for bank in banks:
            figures = unreconciled.get(bank.journal_id.id, {})
            cells = {"name": blocks.value(bank.name)}
            bank_count = 0
            bank_amount = 0.0
            for key, _label, _minimum, _maximum in AGING_BUCKETS:
                count, amount = figures.get(key, (0, 0.0))
                bank_count += count
                bank_amount += amount
                bucket_totals[key][0] += count
                bucket_totals[key][1] += ctx["rates"].to_company(amount, bank.currency_id)
                cells[key] = blocks.money(
                    amount, bank.currency_id, count=count,
                    drilldown=blocks.drilldown("unreconciled", medium_id=bank.id, bucket=key) if count else None,
                )
            grand_count += bank_count
            grand_amount += ctx["rates"].to_company(bank_amount, bank.currency_id)
            cells["total"] = blocks.money(
                bank_amount, bank.currency_id, count=bank_count,
                drilldown=blocks.drilldown("unreconciled", medium_id=bank.id) if bank_count else None,
            )
            last_date = last_dates.get(bank.journal_id.id)
            threshold = self._stale_days(ctx, bank)
            if not last_date:
                cells["last_date"] = blocks.value(self.env._("No statement"), "text", alert="warning")
                cells["days"] = blocks.value(False, "days")
                alerts.append(blocks.alert("warning", self.env._("%s has no bank statement yet.", bank.name)))
            else:
                days = (ctx["today"] - last_date).days
                stale = days > threshold
                cells["last_date"] = blocks.value(last_date, "date", alert="warning" if stale else None)
                cells["days"] = blocks.value(days, "days", alert="warning" if stale else None)
                if stale:
                    alerts.append(blocks.alert("warning", self.env._(
                        "%(bank)s: no new statement for %(days)s days (alert after %(threshold)s).",
                        bank=bank.name, days=days, threshold=threshold,
                    )))
            rows.append(blocks.row("medium-%s" % bank.id, cells))
        total_cells = {"name": blocks.value(self.env._("Total"))}
        for key, *_rest in AGING_BUCKETS:
            total_cells[key] = blocks.money(bucket_totals[key][1], currency, count=bucket_totals[key][0])
        total_cells["total"] = blocks.money(grand_amount, currency, count=grand_count)
        total_cells["last_date"] = blocks.value(False, "text")
        total_cells["days"] = blocks.value(False, "text")
        rows.append(blocks.row("total", total_cells, style="total"))
        columns = [blocks.column("name", self.env._("Bank"))]
        for key, label, *_rest in AGING_BUCKETS:
            columns.append(blocks.column(key, str(label), "monetary"))
        columns += [
            blocks.column("total", self.env._("Total unreconciled"), "monetary"),
            blocks.column("last_date", self.env._("Latest statement"), "date"),
            blocks.column("days", self.env._("Days since"), "days"),
        ]
        cards = [blocks.card(
            self.env._("Statement lines to reconcile"),
            blocks.value(grand_count, "integer"),
            blocks.money(grand_amount, currency),
        )]
        return {"alerts": alerts, "blocks": [
            blocks.cards_block(cards),
            blocks.table_block(
                columns, rows,
                note=self.env._(
                    "Unreconciled statement lines by age (days since the line's date); the number of lines is "
                    "shown in brackets. Totals in %s at the rate of the day.", currency.name,
                ),
            ),
        ]}

    def _drilldown_reconciliation(self, key, params, ctx):
        if key != "unreconciled":
            raise UserError(self.env._("This figure has no detail."))
        bank = self._get_medium(ctx, params.get("medium_id"))
        bucket = params.get("bucket")
        domain = self._unreconciled_domain(ctx, bank.journal_id, bucket)
        st_lines = self.env["account.bank.statement.line"].sudo().search(domain, order="date, id")
        rows = [{"key": str(st_line.id), "record": ("account.bank.statement.line", st_line.id), "cells": {
            "date": blocks.value(st_line.date, "date"),
            "days": blocks.value((ctx["today"] - st_line.date).days, "days"),
            "label": blocks.value(st_line.payment_ref or ""),
            "partner": blocks.value(st_line.partner_id.display_name or st_line.partner_name or ""),
            "amount": blocks.money(-st_line.amount_residual, bank.currency_id),
        }} for st_line in st_lines]
        bucket_label = None
        for entry_key, label, *_rest in AGING_BUCKETS:
            if entry_key == bucket:
                bucket_label = str(label)
        title = self.env._("%s: statement lines to reconcile", bank.name)
        if bucket_label:
            title = "%s (%s)" % (title, bucket_label)
        return self._popup(
            title,
            [blocks.column("date", self.env._("Date"), "date"),
             blocks.column("days", self.env._("Age"), "days"),
             blocks.column("label", self.env._("Label")),
             blocks.column("partner", self.env._("Partner")),
             blocks.column("amount", self.env._("Amount"), "monetary")],
            rows,
            total=blocks.money(sum(-st_line.amount_residual for st_line in st_lines), bank.currency_id),
            list_model="account.bank.statement.line",
            list_domain=domain,
        )
