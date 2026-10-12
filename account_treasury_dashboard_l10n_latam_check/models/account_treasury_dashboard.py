from odoo import models
from odoo.exceptions import UserError
from odoo.fields import Domain
from odoo.tools.translate import LazyTranslate

from odoo.addons.account_treasury_dashboard.models import treasury_blocks as blocks

_lt = LazyTranslate(__name__)

# Brackets of the checks by days from today to their payment date: (key,
# label, minimum days, maximum days), None for no limit. One statement per
# bracket: the translation extractor would otherwise take the keys that
# follow a translated label in the same list for labels too.
_BUCKET_OVERDUE = ("overdue", _lt("Overdue"), None, -1)
_BUCKET_TODAY = ("today", _lt("Today"), 0, 0)
_BUCKET_NEXT_7 = ("next_7", _lt("Next 7 days"), 1, 7)
_BUCKET_NEXT_30 = ("next_30", _lt("Next 8 to 30 days"), 8, 30)
_BUCKET_LATER = ("later", _lt("Later"), 31, None)
CHECK_BUCKETS = [_BUCKET_OVERDUE, _BUCKET_TODAY, _BUCKET_NEXT_7, _BUCKET_NEXT_30, _BUCKET_LATER]

CHECK_GROUPS = ("portfolio", "deposited", "own", "rejected")


class AccountTreasuryDashboard(models.AbstractModel):
    """Checks (l10n_latam_check) in the treasury dashboard.

    - Third-party checks in portfolio: their current journal is one of the
      configured third-party check journals.
    - Deposited third-party checks not credited yet: moved to a bank by a
      payment not matched with a bank statement yet.
    - Own checks pending debit: issue_state "handed".
    - Rejected checks: their current journal is a configured rejected check
      journal (Odoo has no "rejected" state); shown, never projected.

    In the cash projection, checks in portfolio come in on their payment
    date (week 1 when it has passed). The bank's outstanding items of check
    payments (own checks handed, third-party checks deposited) are taken out
    of the generic in-transit flows, which put everything in week 1, and
    projected on their own due date, the check's date: never counted twice.
    """

    _inherit = "account.treasury.dashboard"

    # -------------------------------------------------------------------------
    # Registry and projection hooks
    # -------------------------------------------------------------------------

    def _get_section_providers(self):
        return [*super()._get_section_providers(), {
            "id": "checks", "title": _lt("Checks"), "sequence": 25,
            "toggle": "show_checks", "is_configured": "_is_checks_configured",
        }]

    def _is_checks_configured(self, config):
        return bool(config._get_check_journals() or self._get_mediums(config, ("bank",)))

    def _projection_categories(self, ctx):
        categories = super()._projection_categories(ctx)
        categories.append({"key": "third_party_checks", "label": self.env._("Third-party checks"),
                           "direction": "in", "sequence": 15})
        categories.append({"key": "own_checks", "label": self.env._("Own checks"),
                           "direction": "out", "sequence": 45})
        return sorted(categories, key=lambda category: category["sequence"])

    def _projection_flow_providers(self):
        return [*super()._projection_flow_providers(), "_flows_checks_in_portfolio", "_flows_checks_in_transit"]

    def _check_payment_domain(self):
        """Journal items of checks: linked to a check (own checks split one
        item per check in an entry of their own, and l10n_latam_check_ux does
        it for every check payment), or of a payment that moves checks."""
        return Domain.OR([
            [("l10n_latam_check_ids", "!=", False)],
            [("payment_id.l10n_latam_new_check_ids", "!=", False)],
            [("payment_id.l10n_latam_move_check_ids", "!=", False)],
        ])

    def _in_transit_exclusion_domain(self, ctx):
        return list(Domain.OR([super()._in_transit_exclusion_domain(ctx) or Domain.FALSE,
                               self._check_payment_domain()]))

    # -------------------------------------------------------------------------
    # Checks
    # -------------------------------------------------------------------------

    def _check_base_domain(self, ctx):
        return [
            ("company_id", "=", ctx["company"].id),
            ("payment_id.state", "not in", ("draft", "canceled")),
        ]

    def _read_checks(self, ctx, group):
        """The checks of a group (see CHECK_GROUPS)."""
        Check = self.env["l10n_latam.check"].sudo()
        config = ctx["config"]
        if group == "own":
            return Check.search([*self._check_base_domain(ctx), ("issue_state", "=", "handed"),
                                 ("payment_id.payment_method_line_id.code", "=", "own_checks")])
        if group in ("portfolio", "rejected"):
            journals = config.third_party_check_journal_ids if group == "portfolio" else config.rejected_check_journal_ids
            if not journals:
                return Check
            return Check.search([*self._check_base_domain(ctx), ("current_journal_id", "in", journals.ids),
                                 ("payment_id.payment_method_line_id.code", "!=", "own_checks")])
        if group == "deposited":
            payments = self.env["account.payment"].sudo().search([
                ("company_id", "=", ctx["company"].id),
                ("journal_id.type", "=", "bank"),
                ("payment_type", "=", "inbound"),
                ("state", "not in", ("draft", "canceled")),
                ("is_matched", "=", False),
                ("l10n_latam_move_check_ids", "!=", False),
            ])
            checks = Check
            for payment in payments:
                checks |= payment.l10n_latam_move_check_ids.filtered(
                    lambda check, payment=payment: check.current_journal_id == payment.journal_id)
            return checks
        raise UserError(self.env._("Unknown group of checks: %s", group))

    def _check_bucket(self, ctx, check):
        days = (check.payment_date - ctx["today"]).days
        for key, _label, minimum, maximum in CHECK_BUCKETS:
            if (minimum is None or days >= minimum) and (maximum is None or days <= maximum):
                return key
        return CHECK_BUCKETS[-1][0]

    def _check_amount(self, ctx, check):
        return ctx["rates"].to_company(check.amount, check.currency_id)

    def _group_label(self, group):
        if group == "portfolio":
            return self.env._("Third-party checks in portfolio")
        if group == "deposited":
            return self.env._("Deposited, not credited yet")
        if group == "own":
            return self.env._("Own checks pending debit")
        return self.env._("Rejected checks")

    def _section_checks(self, ctx):
        currency = ctx["currency"]
        alerts = []
        rows = []
        cards = []
        for group in CHECK_GROUPS:
            checks = self._read_checks(ctx, group)
            totals = {key: [0, 0.0] for key, *_rest in CHECK_BUCKETS}
            for check in checks:
                bucket = totals[self._check_bucket(ctx, check)]
                bucket[0] += 1
                bucket[1] += self._check_amount(ctx, check)
            count = sum(entry[0] for entry in totals.values())
            amount = sum(entry[1] for entry in totals.values())
            overdue_count = totals["overdue"][0]
            if group == "portfolio" and overdue_count:
                overdue_amount = self._format_amount(totals["overdue"][1], currency)
                if overdue_count == 1:
                    alert_message = self.env._(
                        "1 check in portfolio with a payment date already passed: %s.", overdue_amount)
                else:
                    alert_message = self.env._(
                        "%(count)s checks in portfolio with a payment date already passed: %(amount)s.",
                        count=overdue_count, amount=overdue_amount,
                    )
                alerts.append(blocks.alert("warning", alert_message))
            if group == "rejected" and count:
                rejected_amount = self._format_amount(amount, currency)
                if count == 1:
                    rejected_message = self.env._("1 rejected check: %s.", rejected_amount)
                else:
                    rejected_message = self.env._("%(count)s rejected checks: %(amount)s.", count=count,
                                                  amount=rejected_amount)
                alerts.append(blocks.alert("danger", rejected_message))
            cells = {"label": blocks.value(self._group_label(group))}
            for key, *_rest in CHECK_BUCKETS:
                bucket_count, bucket_amount = totals[key]
                cells[key] = blocks.money(
                    bucket_amount, currency, count=bucket_count,
                    alert="warning" if key == "overdue" and group == "portfolio" and bucket_count else None,
                    drilldown=blocks.drilldown("checks", group=group, bucket=key) if bucket_count else None,
                )
            cells["total"] = blocks.money(amount, currency, count=count,
                                          drilldown=blocks.drilldown("checks", group=group) if count else None)
            rows.append(blocks.row(group, cells, style="muted" if group == "rejected" else None))
            cards.append(blocks.card(
                self._group_label(group),
                blocks.money(amount, currency, drilldown=blocks.drilldown("checks", group=group) if count else None),
                blocks.value(self.env._("1 check") if count == 1 else self.env._("%s checks", count), "text"),
                alert=blocks.alert("warning", self.env._("%s overdue", overdue_count))
                if group == "portfolio" and overdue_count else None,
            ))
        columns = [blocks.column("label", "")]
        for key, label, *_rest in CHECK_BUCKETS:
            columns.append(blocks.column(key, str(label), "monetary"))
        columns.append(blocks.column("total", self.env._("Total"), "monetary"))
        return {"alerts": alerts, "blocks": [
            blocks.cards_block(cards),
            blocks.table_block(
                columns, rows,
                note=self.env._(
                    "By payment date (debit date for own checks); the number of checks is shown in brackets. "
                    "Amounts in %s, foreign currency checks valued at the rate of the day. Rejected checks are "
                    "not projected.", currency.name,
                ),
            ),
        ]}

    def _drilldown_checks(self, key, params, ctx):
        group = params.get("group")
        if key != "checks" or group not in CHECK_GROUPS:
            raise UserError(self.env._("This figure has no detail."))
        bucket = params.get("bucket")
        checks = self._read_checks(ctx, group)
        if bucket:
            checks = checks.filtered(lambda check: self._check_bucket(ctx, check) == bucket)
        checks = checks.sorted(lambda check: (check.payment_date, check.name or ""))
        currency = ctx["currency"]
        rows = [{"key": str(check.id), "record": ("l10n_latam.check", check.id), "cells": {
            "number": blocks.value(check.name or ""),
            "bank": blocks.value(check.bank_id.name or ""),
            "partner": blocks.value(check.partner_id.display_name or ""),
            "journal": blocks.value(check.current_journal_id.name or check.original_journal_id.name or ""),
            "date": blocks.value(check.payment_date, "date"),
            "days": blocks.value((check.payment_date - ctx["today"]).days, "days"),
            "amount": blocks.money(self._check_amount(ctx, check), currency),
        }} for check in checks]
        title = self._group_label(group)
        for entry_key, label, *_rest in CHECK_BUCKETS:
            if entry_key == bucket:
                title = "%s (%s)" % (title, str(label))
        return self._popup(
            title,
            [blocks.column("number", self.env._("Number")),
             blocks.column("bank", self.env._("Bank")),
             blocks.column("partner", self.env._("Partner")),
             blocks.column("journal", self.env._("Journal")),
             blocks.column("date", self.env._("Payment date"), "date"),
             blocks.column("days", self.env._("Days to payment date"), "days"),
             blocks.column("amount", self.env._("Amount"), "monetary")],
            rows,
            total=blocks.money(sum(self._check_amount(ctx, check) for check in checks), currency),
            list_model="l10n_latam.check",
            list_domain=[("id", "in", checks.ids)],
        )

    # -------------------------------------------------------------------------
    # Projection flows
    # -------------------------------------------------------------------------

    def _flows_checks_in_portfolio(self, ctx):
        flows = []
        for check in self._read_checks(ctx, "portfolio"):
            flows.append(self._flow(
                ctx, max(check.payment_date, ctx["today"]), self._check_amount(ctx, check), "third_party_checks",
                check.name or "", partner=check.partner_id.display_name or "",
                document=self.env._("Check %s", check.name or ""), record=("l10n_latam.check", check.id),
            ))
        return flows

    def _flows_checks_in_transit(self, ctx):
        """The banks' outstanding items of check payments, left out of the
        generic in-transit flows, on their checks' dates: own checks pending
        debit go out, deposited checks come in.

        Each item is split among its checks (in proportion to their amounts):
        with ingadhoc's l10n_latam_check_ux there is one item per check, due
        on the check's date, but Odoo's own deposit makes a single item for
        all the deposited checks, due on the deposit date.
        """
        mediums = self._get_mediums(ctx["config"], ("bank", "cash"), available_only=True)
        lines = self._read_outstanding_lines(ctx, mediums)
        if not lines:
            return []
        MoveLine = self.env["account.move.line"].sudo()
        check_lines = MoveLine.search(Domain.AND([
            [("id", "in", [line["id"] for line in lines])], self._check_payment_domain(),
        ]))
        flows = []
        for line in lines:
            if line["id"] not in check_lines.ids:
                continue
            if line["currency_id"] != ctx["currency"].id:
                residual = line["amount_residual_currency"] if line["is_account_reconcile"] else line["amount_currency"]
                amount = ctx["rates"].to_company(residual, self.env["res.currency"].browse(line["currency_id"]))
            else:
                amount = line["amount_residual"] if line["is_account_reconcile"] else line["balance"]
            category = "own_checks" if line["balance"] < 0 else "third_party_checks"
            record = MoveLine.browse(line["id"])
            checks = (record.l10n_latam_check_ids or record.payment_id.l10n_latam_new_check_ids
                      or record.payment_id.l10n_latam_move_check_ids)
            total = sum(checks.mapped("amount"))
            if not checks or not total:
                partner = record.partner_id.display_name or ""
                flows.append(self._flow(
                    ctx, max(line["date_maturity"] or line["date"], ctx["today"]), amount, category,
                    line["label"] or line["move_name"] or "", partner=partner,
                    document=line["move_name"] or "", record=("account.move", line["move_id"]),
                ))
                continue
            for check in checks:
                flows.append(self._flow(
                    ctx, max(check.payment_date, ctx["today"]), amount * check.amount / total, category,
                    check.name or "", partner=check.partner_id.display_name or "",
                    document=self.env._("Check %s", check.name or ""), record=("l10n_latam.check", check.id),
                ))
        return flows
