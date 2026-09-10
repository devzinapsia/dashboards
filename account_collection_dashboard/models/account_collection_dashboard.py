from datetime import timedelta

from odoo import api, fields, models
from odoo.tools.safe_eval import safe_eval


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

    def _get_invoice_domain(self, date_from, date_to, currency_id=None):
        domain = [
            ("move_type", "in", ("out_invoice", "out_refund")),
            ("state", "=", "posted"),
            ("invoice_date", ">=", date_from),
            ("invoice_date", "<=", date_to),
            ("company_id", "=", self.env.company.id),
        ]
        if currency_id:
            domain.append(("currency_id", "=", currency_id))
        return domain

    @api.model
    def get_invoiced_vs_collected(self, date_from, date_to, currency_id=None):
        """Indicator 1: invoiced amount for the period vs. amount already
        collected from those same invoices (regardless of when they were
        paid), netting out credit notes.
        """
        domain = self._get_invoice_domain(date_from, date_to, currency_id)
        invoiced = 0.0
        collected = 0.0
        for move_type, sign in (("out_invoice", 1), ("out_refund", -1)):
            [(total, residual)] = self.env["account.move"]._read_group(
                domain + [("move_type", "=", move_type)],
                aggregates=["amount_total:sum", "amount_residual:sum"],
            )
            invoiced += sign * (total or 0.0)
            collected += sign * ((total or 0.0) - (residual or 0.0))

        return {
            "invoiced": invoiced,
            "collected": collected,
            "percentage": (collected / invoiced * 100.0) if invoiced else 0.0,
            "currency_id": currency_id or self.env.company.currency_id.id,
            "drilldown": self._get_drilldown_action(
                "account.move",
                domain=domain,
                name=self.env._("Invoices"),
            ),
        }

    def _get_open_receivable_domain(self, currency_id=None, extra=None):
        domain = [
            ("account_id.account_type", "=", "asset_receivable"),
            ("parent_state", "=", "posted"),
            ("move_id.move_type", "in", ("out_invoice", "out_refund")),
            ("company_id", "=", self.env.company.id),
            ("reconciled", "=", False),
        ]
        if currency_id:
            domain.append(("currency_id", "=", currency_id))
        return domain + (extra or [])

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

    def _age_bucket_domain(self, bucket, today):
        bucket_domain = [("date_maturity", "<=", today - timedelta(days=bucket["min"]))]
        if bucket["max"] is not None:
            bucket_domain.append(("date_maturity", ">=", today - timedelta(days=bucket["max"])))
        return bucket_domain

    @api.model
    def get_overdue_by_age(self, currency_id=None):
        """Indicator 3: overdue, uncollected receivables, bucketed by age
        (0-30 / 31-60 / 61-90 / +90 days overdue).
        """
        today = fields.Date.context_today(self)
        domain = self._get_open_receivable_domain(currency_id, [("date_maturity", "<", today)])
        residual_field = self._residual_field(currency_id)
        lines = self.env["account.move.line"].search_read(domain, ["date_maturity", residual_field])

        buckets = [
            {"label": self.env._("0-30 days"), "min": 0, "max": 30, "amount": 0.0},
            {"label": self.env._("31-60 days"), "min": 31, "max": 60, "amount": 0.0},
            {"label": self.env._("61-90 days"), "min": 61, "max": 90, "amount": 0.0},
            {"label": self.env._("+90 days"), "min": 91, "max": None, "amount": 0.0},
        ]
        for line in lines:
            days_overdue = (today - line["date_maturity"]).days
            for bucket in buckets:
                if days_overdue >= bucket["min"] and (bucket["max"] is None or days_overdue <= bucket["max"]):
                    bucket["amount"] += line[residual_field]
                    break

        for bucket in buckets:
            bucket["currency_id"] = currency_id or self.env.company.currency_id.id
            bucket["drilldown"] = self._get_drilldown_action(
                "account.move.line",
                domain=domain + self._age_bucket_domain(bucket, today),
                name=bucket["label"],
            )
        return buckets

    @api.model
    def get_top_overdue_partners(self, currency_id=None, limit=10):
        """Indicator 4: top overdue customers by amount owed. Drill-down
        reuses the standard Partner Ledger report, opened unfiltered (this
        report's partner filter cannot be pre-seeded from the action
        context in this Odoo version, only set interactively).
        """
        today = fields.Date.context_today(self)
        domain = self._get_open_receivable_domain(currency_id, [("date_maturity", "<", today)])
        residual_field = self._residual_field(currency_id)
        rows = self.env["account.move.line"]._read_group(
            domain,
            groupby=["partner_id"],
            aggregates=[f"{residual_field}:sum"],
            order=f"{residual_field}:sum desc",
            limit=limit,
        )
        return [
            {
                "partner_id": partner.id,
                "partner_name": partner.name,
                "amount": amount or 0.0,
                "currency_id": currency_id or self.env.company.currency_id.id,
                # NOTE: the Partner Ledger report's partner filter is a
                # purely interactive client-side widget in this Odoo
                # version (there is no context/option key that pre-seeds
                # it on the initial action call, confirmed by inspecting
                # AccountReportController and every other core caller of
                # this action). So this opens the report unfiltered,
                # reusing the standard action as requested; the user
                # still has to pick the partner from the report's own
                # "Partners" filter.
                "drilldown": self._get_native_drilldown_action(
                    "account_reports.action_account_report_partner_ledger"
                ),
            }
            for partner, amount in rows
            if partner
        ]

    @api.model
    def get_late_payments(self, date_from, date_to, currency_id=None):
        """Indicator 5: customer payments collected after the due date of
        the invoice(s) they settle.
        """
        domain = [
            ("payment_type", "=", "inbound"),
            ("partner_type", "=", "customer"),
            ("state", "in", ("in_process", "paid")),
            ("date", ">=", date_from),
            ("date", "<=", date_to),
            ("company_id", "=", self.env.company.id),
        ]
        if currency_id:
            domain.append(("currency_id", "=", currency_id))
        payments = self.env["account.payment"].search(domain)
        late_payments = payments.filtered(
            lambda p: any(
                invoice.invoice_date_due and invoice.invoice_date_due < p.date
                for invoice in p.reconciled_invoice_ids
            )
        )
        return {
            "count": len(late_payments),
            "amount": sum(late_payments.mapped("amount")),
            "currency_id": currency_id or self.env.company.currency_id.id,
            "drilldown": self._get_drilldown_action(
                "account.payment",
                domain=[("id", "in", late_payments.ids)],
                name=self.env._("Late Payments"),
            ),
        }

    @api.model
    def get_cash_collections(self, date_from, date_to):
        """Indicator 9: cash/transfer customer collections for the period,
        restricted to the journals selected in the settings.
        """
        config = self.env["account.collection.dashboard.config"].sudo()._get_config()
        if not config.cash_collection_journal_ids:
            return None
        domain = [
            ("payment_type", "=", "inbound"),
            ("partner_type", "=", "customer"),
            ("state", "in", ("in_process", "paid")),
            ("date", ">=", date_from),
            ("date", "<=", date_to),
            ("company_id", "=", self.env.company.id),
            ("journal_id", "in", config.cash_collection_journal_ids.ids),
        ]
        [(count, total)] = self.env["account.payment"]._read_group(
            domain, aggregates=["__count", "amount:sum"]
        )
        return {
            "count": count,
            "amount": total or 0.0,
            "currency_id": self.env.company.currency_id.id,
            "drilldown": self._get_drilldown_action(
                "account.payment", domain=domain, name=self.env._("Cash/Transfer Collections")
            ),
        }

    @api.model
    def get_pending_reconciliation(self):
        """Indicator 10: journal items pending reconciliation, reusing the
        standard "Journal Items to reconcile" domain/action.
        """
        action = self.env.ref("account_accountant.action_move_line_posted_unreconciled", raise_if_not_found=False)
        if not action:
            return None
        domain = (safe_eval(action.domain) if action.domain else []) + [
            ("company_id", "=", self.env.company.id)
        ]
        [(count, total)] = self.env["account.move.line"]._read_group(
            domain, aggregates=["__count", "balance:sum"]
        )
        return {
            "count": count,
            "amount": total or 0.0,
            "currency_id": self.env.company.currency_id.id,
            "drilldown": self._get_native_drilldown_action(
                "account_accountant.action_move_line_posted_unreconciled"
            ),
        }

    @api.model
    def get_bank_balances(self):
        """Indicator 7: one balance per journal selected in the settings as
        a "bank balance" journal.
        """
        config = self.env["account.collection.dashboard.config"].sudo()._get_config()
        results = []
        for journal in config.bank_balance_journal_ids:
            results.append(self._build_journal_balance(journal))
        return results

    @api.model
    def get_fixed_fund_balance(self):
        """Indicator 8: balance of the journal configured as "Fixed fund"."""
        config = self.env["account.collection.dashboard.config"].sudo()._get_config()
        if not config.fixed_fund_journal_id:
            return None
        return self._build_journal_balance(config.fixed_fund_journal_id)

    def _build_journal_balance(self, journal):
        account = journal.default_account_id
        return {
            "journal_id": journal.id,
            "journal_name": journal.name,
            "balance": account.current_balance if account else 0.0,
            "currency_id": journal.currency_id.id or self.env.company.currency_id.id,
            "drilldown": self._get_drilldown_action(
                "account.move.line",
                domain=[("account_id", "=", account.id), ("parent_state", "=", "posted")],
                name=journal.name,
            )
            if account
            else None,
        }

    @api.model
    def get_third_party_checks_in_portfolio(self):
        """Indicator 6: third-party checks currently in portfolio (received
        from customers, not yet deposited or transferred out), for the
        journals configured as such in the settings.

        Amounts are aggregated per currency (never summed across
        different currencies); "overdue" means the check's cash-in date
        has already passed.
        """
        config = self.env["account.collection.dashboard.config"].sudo()._get_config()
        if not config.third_party_check_journal_ids:
            return None

        today = fields.Date.context_today(self)
        domain = [("current_journal_id", "in", config.third_party_check_journal_ids.ids)]
        Check = self.env["l10n_latam.check"]

        by_currency = []
        for currency, count, amount in Check._read_group(
            domain, groupby=["currency_id"], aggregates=["__count", "amount:sum"]
        ):
            [(overdue_count, overdue_amount)] = Check._read_group(
                domain + [("currency_id", "=", currency.id), ("payment_date", "<", today)],
                aggregates=["__count", "amount:sum"],
            )
            by_currency.append({
                "currency_id": currency.id,
                "count": count,
                "amount": amount or 0.0,
                "overdue_count": overdue_count,
                "overdue_amount": overdue_amount or 0.0,
            })

        return {
            "by_currency": by_currency,
            "drilldown": self._get_drilldown_action(
                "l10n_latam.check", domain=domain, name=self.env._("Third-Party Checks in Portfolio")
            ),
        }

    @api.model
    def get_pending_exchange_difference(self):
        """Indicator 13: invoices with an open (unreconciled) foreign
        currency balance whose value at today's exchange rate no longer
        matches the amount already booked in company currency — i.e. an
        unrealized exchange gain/loss not yet recognized.

        Same criterion as Odoo's own "Multicurrency Revaluation" report
        (account_reports): revalue amount_residual_currency at today's
        rate and compare it to the booked amount_residual.
        """
        company = self.env.company
        company_currency = company.currency_id
        today = fields.Date.context_today(self)
        domain = [
            ("account_id.account_type", "in", ("asset_receivable", "liability_payable")),
            ("parent_state", "=", "posted"),
            ("company_id", "=", company.id),
            ("currency_id", "!=", company_currency.id),
            ("amount_residual_currency", "!=", 0.0),
        ]
        lines = self.env["account.move.line"].search(domain)

        affected_move_ids = set()
        total_adjustment = 0.0
        for line in lines:
            revalued = line.currency_id._convert(line.amount_residual_currency, company_currency, company, today)
            adjustment = revalued - line.amount_residual
            if not company_currency.is_zero(adjustment):
                affected_move_ids.add(line.move_id.id)
                total_adjustment += adjustment

        return {
            "count": len(affected_move_ids),
            "amount": total_adjustment,
            "currency_id": company_currency.id,
            "drilldown": self._get_drilldown_action(
                "account.move",
                domain=[("id", "in", list(affected_move_ids))],
                name=self.env._("Invoices with Pending Exchange Difference"),
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
