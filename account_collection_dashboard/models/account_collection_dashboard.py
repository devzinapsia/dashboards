from collections import defaultdict
from datetime import timedelta

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models


class AccountCollectionDashboard(models.AbstractModel):
    """Backend data provider for the Collection dashboard client action.

    Every method here is meant to be called via RPC from the OWL client
    action (account_collection_dashboard/static/src/collection_dashboard).
    """

    _name = "account.collection.dashboard"
    _description = "Collection Dashboard"
    _inherit = "dashboards.drilldown.mixin"

    @api.model
    def get_active_currencies(self):
        """Currencies offered by the dashboard's currency filter (indicator
        12): every currency active on this database, not hardcoded to any
        specific pair.
        """
        currencies = self.env["res.currency"].search([("active", "=", True)])
        return [{"id": currency.id, "name": currency.name} for currency in currencies]

    def _get_dashboard_config(self):
        return self.env["account.collection.dashboard.config"].sudo()._get_config()

    def _get_open_receivable_domain(self, currency_id=None, extra=None):
        config = self._get_dashboard_config()
        domain = [
            ("account_id.account_type", "=", "asset_receivable"),
            ("parent_state", "=", "posted"),
            ("move_id.move_type", "in", ("out_invoice", "out_refund")),
            ("company_id", "=", self.env.company.id),
            ("reconciled", "=", False),
        ]
        if config.sale_journal_ids:
            domain.append(("journal_id", "in", config.sale_journal_ids.ids))
        if currency_id:
            domain.append(("currency_id", "=", currency_id))
        return domain + (extra or [])

    @api.model
    def get_total_receivable(self, currency_id=None):
        """New indicator: total open (uncollected) receivable balance,
        re-expressed in the selected currency at today's exchange rate.

        Every open invoice's already-booked company-currency residual
        (amount_residual, which Odoo keeps normalized regardless of the
        invoice's own currency) is converted once to the target currency,
        rather than re-deriving each invoice from its own currency — this
        is what lets invoices in any currency be re-expressed correctly in
        whichever currency the user selects.
        """
        company = self.env.company
        target_currency = self.env["res.currency"].browse(currency_id) if currency_id else company.currency_id
        today = fields.Date.context_today(self)

        domain = self._get_open_receivable_domain()
        rows = self.env["account.move.line"]._read_group(
            domain, groupby=["move_id"], aggregates=["amount_residual:sum"]
        )
        total_company_currency = sum(amount or 0.0 for move, amount in rows if move)
        move_ids = [move.id for move, amount in rows if move]
        rate = company.currency_id._get_conversion_rate(company.currency_id, target_currency, company, today)
        total = total_company_currency * rate

        return {
            "amount": total,
            "currency_id": target_currency.id,
            "drilldown": self._get_drilldown_action(
                "account.move",
                domain=[("id", "in", move_ids)],
                name=self.env._("Receivables"),
                view_id=self._invoice_list_view_id(),
                # Group by due date (month) instead of an ad-hoc
                # vencida/no vencida split, which would require a new
                # field on account.move - Odoo already supports grouping
                # by date granularity natively.
                context={"group_by": ["invoice_date_due:month"]},
            ),
        }

    def _ar_balance_as_of(self, date):
        # Deliberately NOT restricted by config.sale_journal_ids: a
        # customer payment's own reconciling entry in the receivable
        # account lives in the payment's journal (e.g. a bank journal),
        # not the invoice's sales journal, so filtering this GL balance by
        # sale_journal_ids would exclude that offsetting entry and make
        # the balance look like it never decreases as invoices get paid.
        # (get_total_receivable and the other indicators don't have this
        # problem: they read amount_residual straight off the invoice's
        # own line, which already nets off payments from any journal.)
        domain = [
            ("account_id.account_type", "=", "asset_receivable"),
            ("parent_state", "=", "posted"),
            ("company_id", "=", self.env.company.id),
            ("date", "<=", date),
        ]
        [(balance,)] = self.env["account.move.line"]._read_group(domain, aggregates=["balance:sum"])
        return balance or 0.0

    def _get_turnover_period_bounds(self, period, company, today):
        if period == "previous_fiscal_year":
            current_bounds = company.compute_fiscalyear_dates(today)
            reference_date = current_bounds["date_from"] - timedelta(days=1)
            bounds = company.compute_fiscalyear_dates(reference_date)
            return bounds["date_from"], bounds["date_to"]
        if period == "last_12_months":
            return today - relativedelta(months=12), today
        # current_fiscal_year (default): the fiscal year's full start-to-end
        # range, matching the other two periods rather than truncating at
        # today.
        bounds = company.compute_fiscalyear_dates(today)
        return bounds["date_from"], bounds["date_to"]

    @api.model
    def get_collection_turnover(self, period="current_fiscal_year"):
        """New indicator: Rotación de cobranza = Ventas netas a crédito /
        Promedio de cuentas por cobrar, over a fixed period selected
        independently of the dashboard's date range (current/previous
        fiscal year, or trailing 12 months).

        "Ventas netas a crédito" is taken net of tax (amount_untaxed) and
        net of credit notes.
        """
        config = self._get_dashboard_config()
        company = self.env.company
        today = fields.Date.context_today(self)
        date_from, date_to = self._get_turnover_period_bounds(period, company, today)

        sales_domain = [
            ("move_type", "in", ("out_invoice", "out_refund")),
            ("state", "=", "posted"),
            ("invoice_date", ">=", date_from),
            ("invoice_date", "<=", date_to),
            ("company_id", "=", company.id),
        ]
        if config.sale_journal_ids:
            sales_domain.append(("journal_id", "in", config.sale_journal_ids.ids))

        net_credit_sales = 0.0
        for move_type, sign in (("out_invoice", 1), ("out_refund", -1)):
            [(untaxed,)] = self.env["account.move"]._read_group(
                sales_domain + [("move_type", "=", move_type)],
                aggregates=["amount_untaxed:sum"],
            )
            net_credit_sales += sign * (untaxed or 0.0)

        average_receivable = (
            self._ar_balance_as_of(date_from) + self._ar_balance_as_of(date_to)
        ) / 2.0

        return {
            "turnover": (net_credit_sales / average_receivable) if average_receivable else 0.0,
            "net_credit_sales": net_credit_sales,
            "average_receivable": average_receivable,
            "currency_id": company.currency_id.id,
        }

    @api.model
    def get_collection_payment_ratio(self, date_from, date_to):
        """New indicator: Ratio Cobro/Pago = amount collected from
        customers / amount paid to suppliers, over the dashboard's
        selected date range.
        """
        config = self._get_dashboard_config()
        company = self.env.company

        collected_domain = [
            ("payment_type", "=", "inbound"),
            ("partner_type", "=", "customer"),
            ("state", "in", ("in_process", "paid")),
            ("date", ">=", date_from),
            ("date", "<=", date_to),
            ("company_id", "=", company.id),
        ]
        if config.sale_journal_ids:
            # reconciled_invoice_ids is a computed field with a custom
            # search method; it only supports plain operators on itself
            # (e.g. "in" with explicit ids), not dotted-path traversal
            # into a related field like ".journal_id".
            sale_invoice_ids = self.env["account.move"].search([
                ("journal_id", "in", config.sale_journal_ids.ids),
                ("move_type", "in", ("out_invoice", "out_refund")),
            ]).ids
            collected_domain.append(("reconciled_invoice_ids", "in", sale_invoice_ids))
        [(collected,)] = self.env["account.payment"]._read_group(collected_domain, aggregates=["amount:sum"])

        paid_domain = [
            ("payment_type", "=", "outbound"),
            ("partner_type", "=", "supplier"),
            ("state", "in", ("in_process", "paid")),
            ("date", ">=", date_from),
            ("date", "<=", date_to),
            ("company_id", "=", company.id),
        ]
        [(paid,)] = self.env["account.payment"]._read_group(paid_domain, aggregates=["amount:sum"])

        collected = collected or 0.0
        paid = paid or 0.0
        return {
            "ratio": (collected / paid) if paid else 0.0,
            "collected": collected,
            "paid": paid,
            "currency_id": company.currency_id.id,
        }

    @api.model
    def get_rejected_checks(self, currency_id=None):
        """New indicator: third-party checks currently sitting in a
        journal configured as a "rejected checks" journal (see the
        rejected_check_journal_ids help text for why this is the only
        way to detect rejection), re-expressed in the selected currency
        at today's rate.
        """
        config = self._get_dashboard_config()
        if not config.rejected_check_journal_ids:
            return None

        company = self.env.company
        target_currency = self.env["res.currency"].browse(currency_id) if currency_id else company.currency_id
        today = fields.Date.context_today(self)
        domain = [("current_journal_id", "in", config.rejected_check_journal_ids.ids)]
        Check = self.env["l10n_latam.check"]

        total = 0.0
        count = 0
        for currency, line_count, amount in Check._read_group(
            domain, groupby=["currency_id"], aggregates=["__count", "amount:sum"]
        ):
            rate = currency._get_conversion_rate(currency, target_currency, company, today)
            total += (amount or 0.0) * rate
            count += line_count

        return {
            "amount": total,
            "count": count,
            "currency_id": target_currency.id,
            "drilldown": self._get_drilldown_action(
                "l10n_latam.check", domain=domain, name=self.env._("Rejected Checks")
            ),
        }

    def _residual_field(self, currency_id):
        return "amount_residual_currency" if currency_id else "amount_residual"

    @api.model
    def get_due_soon_by_followup_level(self, currency_id=None):
        """Indicator 2: not-yet-due receivables, grouped by the Follow-up
        level already assigned to them. Only lines with a (possibly
        pre-due) Follow-up level assigned show up here; lines with no
        level assigned yet are not part of this breakdown.
        """
        today = fields.Date.context_today(self)
        domain = self._get_open_receivable_domain(currency_id, [
            ("date_maturity", ">=", today),
            ("followup_line_id", "!=", False),
        ])
        residual_field = self._residual_field(currency_id)
        rows = self.env["account.move.line"]._read_group(
            domain, groupby=["followup_line_id"], aggregates=[f"{residual_field}:sum"]
        )
        return [
            {
                "level_id": level.id,
                "level_name": level.name,
                "amount": amount or 0.0,
                "currency_id": currency_id or self.env.company.currency_id.id,
                "drilldown": self._get_drilldown_action(
                    "account.move.line",
                    domain=domain + [("followup_line_id", "=", level.id)],
                    name=level.name,
                ),
            }
            for level, amount in rows
        ]

    @api.model
    def get_top_slow_paying_customers(self, period="current_fiscal_year", limit=10):
        """Bottom chart 1: the customers who took the longest, on average,
        to fully settle an invoice (settlement date - invoice date),
        averaged over every fully-paid invoice issued within the selected
        period (same period selector as "Collection turnover").

        "Settlement date" is the latest reconciliation date
        (account.partial.reconcile.max_date) among every partial that
        cleared the invoice's receivable line - this covers payments,
        credit notes or any other counterpart, not just account.payment.
        """
        config = self._get_dashboard_config()
        company = self.env.company
        today = fields.Date.context_today(self)
        date_from, date_to = self._get_turnover_period_bounds(period, company, today)

        domain = [
            ("account_id.account_type", "=", "asset_receivable"),
            ("parent_state", "=", "posted"),
            ("move_id.move_type", "in", ("out_invoice", "out_refund")),
            ("company_id", "=", company.id),
            ("reconciled", "=", True),
            ("move_id.invoice_date", ">=", date_from),
            ("move_id.invoice_date", "<=", date_to),
        ]
        if config.sale_journal_ids:
            domain.append(("journal_id", "in", config.sale_journal_ids.ids))

        days_by_partner = defaultdict(list)
        for line in self.env["account.move.line"].search(domain):
            invoice_date = line.move_id.invoice_date
            partials = line.matched_debit_ids | line.matched_credit_ids
            if not invoice_date or not partials:
                continue
            settlement_date = max(partials.mapped("max_date"))
            days_by_partner[line.partner_id].append((settlement_date - invoice_date).days)

        averages = [
            (partner, sum(days) / len(days))
            for partner, days in days_by_partner.items()
            if partner
        ]
        averages.sort(key=lambda row: row[1], reverse=True)
        return [
            {"partner_id": partner.id, "partner_name": partner.name, "days": round(avg_days, 1)}
            for partner, avg_days in averages[:limit]
        ]

    @api.model
    def get_collection_projection(self, currency_id=None):
        """Bottom chart 2: open receivable balance bucketed by days left
        until due (date_maturity), with already-overdue debt folded into
        the first bucket (it needs collecting now, same as anything due
        within the next 15 days). Each bucket also carries its share of
        the total as a percentage.
        """
        today = fields.Date.context_today(self)
        domain = self._get_open_receivable_domain(currency_id)
        residual_field = self._residual_field(currency_id)
        lines = self.env["account.move.line"].search_read(domain, ["date_maturity", residual_field])

        buckets = [
            {"label": self.env._("0-15 days"), "max_days": 15, "amount": 0.0},
            {"label": self.env._("16-30 days"), "max_days": 30, "amount": 0.0},
            {"label": self.env._("31-60 days"), "max_days": 60, "amount": 0.0},
            {"label": self.env._("61-90 days"), "max_days": 90, "amount": 0.0},
            {"label": self.env._("+90 days"), "max_days": None, "amount": 0.0},
        ]
        for line in lines:
            date_maturity = line["date_maturity"] or today
            days_until_due = max((date_maturity - today).days, 0)
            for bucket in buckets:
                if bucket["max_days"] is None or days_until_due <= bucket["max_days"]:
                    bucket["amount"] += line[residual_field]
                    break

        total = sum(bucket["amount"] for bucket in buckets)
        for bucket in buckets:
            bucket["currency_id"] = currency_id or self.env.company.currency_id.id
            bucket["percentage"] = (bucket["amount"] / total * 100) if total else 0.0
        return buckets

    @api.model
    def get_overdue_debt(self, currency_id=None):
        """Indicator: total amount of receivables that are overdue
        (date_maturity < today). Drill-down opens the matching sales
        invoices, using the same invoice list view as "Not yet due".
        """
        today = fields.Date.context_today(self)
        domain = self._get_open_receivable_domain(currency_id, [("date_maturity", "<", today)])
        residual_field = self._residual_field(currency_id)
        total, move_ids = self._receivable_amount_and_moves(domain, residual_field)
        return {
            "amount": total,
            "currency_id": currency_id or self.env.company.currency_id.id,
            "drilldown": self._get_drilldown_action(
                "account.move", domain=[("id", "in", move_ids)], name=self.env._("Overdue Debt"),
                view_id=self._invoice_list_view_id(),
            ),
        }

    def _invoice_list_view_id(self):
        return self.env.ref("account_collection_dashboard.view_account_collection_dashboard_invoice_list").id

    def _receivable_amount_and_moves(self, domain, residual_field):
        rows = self.env["account.move.line"]._read_group(
            domain, groupby=["move_id"], aggregates=[f"{residual_field}:sum"]
        )
        total = sum(amount or 0.0 for move, amount in rows if move)
        move_ids = [move.id for move, amount in rows if move]
        return total, move_ids

    @api.model
    def get_undue_debt(self, currency_id=None):
        """Indicator: total amount of receivables not yet due
        (date_maturity >= today), regardless of whether a Follow-up level
        has been assigned yet - a broader total than the "Due soon, by
        Follow-up level" breakdown, which only covers lines that already
        have a level. Drill-down opens the matching sales invoices.
        """
        today = fields.Date.context_today(self)
        domain = self._get_open_receivable_domain(currency_id, [("date_maturity", ">=", today)])
        residual_field = self._residual_field(currency_id)
        total, move_ids = self._receivable_amount_and_moves(domain, residual_field)
        return {
            "amount": total,
            "currency_id": currency_id or self.env.company.currency_id.id,
            "drilldown": self._get_drilldown_action(
                "account.move", domain=[("id", "in", move_ids)], name=self.env._("Undue Debt"),
                view_id=self._invoice_list_view_id(),
            ),
        }

    @api.model
    def get_due_today(self, currency_id=None):
        """Indicator: amount of receivables due exactly today. Drill-down
        opens the matching sales invoices.
        """
        today = fields.Date.context_today(self)
        domain = self._get_open_receivable_domain(currency_id, [("date_maturity", "=", today)])
        residual_field = self._residual_field(currency_id)
        total, move_ids = self._receivable_amount_and_moves(domain, residual_field)
        return {
            "amount": total,
            "currency_id": currency_id or self.env.company.currency_id.id,
            "drilldown": self._get_drilldown_action(
                "account.move", domain=[("id", "in", move_ids)], name=self.env._("Due Today"),
                view_id=self._invoice_list_view_id(),
            ),
        }

    @api.model
    def get_due_next_7_days(self, currency_id=None):
        """Indicator: amount of receivables due within the next 7 days,
        today included (so it overlaps with the "Due today" indicator by
        design). Drill-down opens the matching sales invoices.
        """
        today = fields.Date.context_today(self)
        domain = self._get_open_receivable_domain(currency_id, [
            ("date_maturity", ">=", today),
            ("date_maturity", "<=", today + timedelta(days=7)),
        ])
        residual_field = self._residual_field(currency_id)
        total, move_ids = self._receivable_amount_and_moves(domain, residual_field)
        return {
            "amount": total,
            "currency_id": currency_id or self.env.company.currency_id.id,
            "drilldown": self._get_drilldown_action(
                "account.move", domain=[("id", "in", move_ids)], name=self.env._("Due in Next 7 Days"),
                view_id=self._invoice_list_view_id(),
            ),
        }

    @api.model
    def get_collection_by_user(self, date_from, date_to):
        """Indicator 11: collected amount for the period, grouped by the
        salesperson (invoice_user_id) of the invoice(s) each payment
        reconciles.

        Simplification: when a single payment reconciles invoices from more
        than one salesperson, the whole payment amount is attributed to the
        salesperson of the first reconciled invoice, rather than being
        split proportionally. This is documented as a known limitation.
        """
        payments = self.env["account.payment"].search([
            ("payment_type", "=", "inbound"),
            ("partner_type", "=", "customer"),
            ("state", "in", ("in_process", "paid")),
            ("date", ">=", date_from),
            ("date", "<=", date_to),
            ("company_id", "=", self.env.company.id),
        ])
        buckets = {}
        for payment in payments:
            invoice = payment.reconciled_invoice_ids[:1]
            user = invoice.invoice_user_id if invoice else self.env["res.users"]
            key = user.id or False
            bucket = buckets.setdefault(
                key, {"user_id": key, "user_name": user.name or self.env._("Unassigned"), "amount": 0.0, "payment_ids": []}
            )
            bucket["amount"] += payment.amount
            bucket["payment_ids"].append(payment.id)

        results = []
        for bucket in sorted(buckets.values(), key=lambda r: r["amount"], reverse=True):
            payment_ids = bucket.pop("payment_ids")
            bucket["drilldown"] = self._get_drilldown_action(
                "account.payment",
                domain=[("id", "in", payment_ids)],
                name=bucket["user_name"],
            )
            results.append(bucket)
        return results
