from odoo import models
from odoo.exceptions import UserError
from odoo.fields import Domain
from odoo.tools import format_date, formatLang

from . import treasury_blocks as blocks
from . import treasury_dates

OVERDUE_RECEIVABLES = "overdue_receivables"


class AccountTreasuryDashboard(models.AbstractModel):
    """Section "Cash projection", week by week (week 1 from today to Sunday,
    then Monday to Sunday).

    The starting balance is the balance of the BANK ACCOUNTS (the journals'
    default accounts) of the bank and cash payment means in the available
    total, on purpose not their book balance: what is recorded but not in
    the bank yet (the in-transit items) comes in as a flow in week 1. Using
    the book balance and adding those flows would count them twice.

    Flows come from providers (see _projection_flow_providers()), each
    returning flows {"date", "amount" (signed, company currency),
    "category", "label", "partner", "document", "res_model", "res_id"}.
    Another module adds flows by adding a provider and its category, and
    can take journal items out of the generic in-transit flows with
    _in_transit_exclusion_domain() (e.g. deferred checks it projects on
    their own date). A paid invoice has no residual left, so a payment
    already reconciled with its invoice only shows as in transit, never
    also as a receivable or payable.
    """

    _inherit = "account.treasury.dashboard"

    # -------------------------------------------------------------------------
    # Extension points
    # -------------------------------------------------------------------------

    def _projection_categories(self, ctx):
        """Rows of the projection, in order: [{"key", "label", "direction"
        ("in" or "out"), "sequence"}]. Overdue receivables are a row of
        their own that doesn't add to the projected balance (unless the
        configuration includes them in week 1)."""
        categories = [
            {"key": "receivables", "label": self.env._("Customer receivables"), "direction": "in", "sequence": 10},
            {"key": "in_transit_receipts", "label": self.env._("Receipts in transit"), "direction": "in",
             "sequence": 20},
            {"key": "payables", "label": self.env._("Vendor payables"), "direction": "out", "sequence": 30},
            {"key": "in_transit_payments", "label": self.env._("Payments in transit"), "direction": "out",
             "sequence": 40},
            {"key": "credit_cards", "label": self.env._("Credit card statements"), "direction": "out",
             "sequence": 50},
        ]
        for index, commitment in enumerate(self._get_commitments(ctx)):
            categories.append({"key": "commitment_%s" % commitment.id, "label": commitment.name,
                               "direction": "out", "sequence": 60 + index})
        return sorted(categories, key=lambda category: category["sequence"])

    def _projection_flow_providers(self):
        """Methods returning flows (see the class docstring). Extension point."""
        return [
            "_flows_receivables",
            "_flows_payables",
            "_flows_in_transit",
            "_flows_credit_cards",
            "_flows_commitments",
        ]

    def _in_transit_exclusion_domain(self, ctx):
        """Journal items (account.move.line domain) left out of the generic
        in-transit flows because another provider projects them on their
        own. Extension point: empty by default."""
        return []

    # -------------------------------------------------------------------------
    # Flow providers
    # -------------------------------------------------------------------------

    def _get_commitments(self, ctx):
        return ctx["config"].commitment_ids.filtered("active")

    def _flow(self, ctx, date, amount, category, label, partner="", document="", record=None):
        return {
            "date": date,
            "amount": amount,
            "category": category,
            "label": label,
            "partner": partner,
            "document": document,
            "res_model": record[0] if record else False,
            "res_id": record[1] if record else False,
        }

    def _read_open_items(self, ctx, domain):
        """Open journal items (posted, residual not zero) grouped by entry,
        partner, due date and currency: [(move, partner, date, amount)], the
        amount being the residual in the company currency, the residual of a
        foreign currency item valued at the rate of the day."""
        rows = self.env["account.move.line"].sudo()._read_group(
            [
                ("company_id", "=", ctx["company"].id),
                ("parent_state", "=", "posted"),
                ("reconciled", "=", False),
                ("amount_residual", "!=", 0),
                *domain,
            ],
            groupby=["move_id", "partner_id", "date_maturity:day", "date:day", "currency_id"],
            aggregates=["amount_residual:sum", "amount_residual_currency:sum"],
        )
        result = []
        for move, partner, date_maturity, date, currency, residual, residual_currency in rows:
            if currency and currency != ctx["currency"]:
                amount = ctx["rates"].to_company(residual_currency, currency)
            else:
                amount = residual
            result.append((move, partner, date_maturity or date, amount))
        return result

    def _commitment_account_ids(self, ctx):
        return self._get_commitments(ctx).account_ids.ids

    def _open_items_flows(self, ctx, domain, category, overdue_category=None):
        flows = []
        for move, partner, date, amount in self._read_open_items(ctx, domain):
            overdue = date < ctx["today"]
            flow_category = overdue_category if overdue and overdue_category else category
            flows.append(self._flow(
                ctx, date, amount, flow_category, move.name,
                partner=partner.display_name or "", document=move.name, record=("account.move", move.id),
            ))
        return flows

    def _flows_receivables(self, ctx):
        include_overdue = ctx["config"].include_overdue_receivables
        return self._open_items_flows(
            ctx,
            [("account_id.account_type", "=", "asset_receivable"),
             ("account_id", "not in", self._commitment_account_ids(ctx))],
            "receivables",
            overdue_category=None if include_overdue else OVERDUE_RECEIVABLES,
        )

    def _flows_payables(self, ctx):
        # Overdue payables stay in their category: dated in the past, they
        # fall in week 1 (prudent criterion).
        return self._open_items_flows(
            ctx,
            [("account_id.account_type", "=", "liability_payable"),
             ("account_id", "not in", self._commitment_account_ids(ctx))],
            "payables",
        )

    def _flows_in_transit(self, ctx):
        mediums = self._get_mediums(ctx["config"], ("bank", "cash"), available_only=True)
        lines = self._read_outstanding_lines(ctx, mediums)
        exclusion = self._in_transit_exclusion_domain(ctx)
        if exclusion and lines:
            excluded = set(self.env["account.move.line"].sudo().search(Domain.AND([
                [("id", "in", [line["id"] for line in lines])], exclusion,
            ])).ids)
            lines = [line for line in lines if line["id"] not in excluded]
        partners = self.env["res.partner"].sudo().browse({line["partner_id"] for line in lines if line["partner_id"]})
        partner_names = {partner.id: partner.display_name for partner in partners}
        flows = []
        for line in lines:
            currency = self.env["res.currency"].browse(line["currency_id"])
            if line["currency_id"] != ctx["currency"].id:
                residual = line["amount_residual_currency"] if line["is_account_reconcile"] else line["amount_currency"]
                amount = ctx["rates"].to_company(residual, currency)
            else:
                amount = line["amount_residual"] if line["is_account_reconcile"] else line["balance"]
            record = ("account.payment", line["payment_id"]) if line["payment_id"] else ("account.move", line["move_id"])
            flows.append(self._flow(
                ctx, ctx["today"], amount,
                "in_transit_receipts" if line["balance"] > 0 else "in_transit_payments",
                line["move_name"] or "", partner=partner_names.get(line["partner_id"], ""),
                document=line["move_name"] or "", record=record,
            ))
        return flows

    def _flows_credit_cards(self, ctx):
        """Statements of the credit cards: what is owed for the closed cycle
        is paid on its due date (week 1 if already due), and the current
        cycle's purchases up to today on the following due date. An estimate:
        purchases of the rest of the cycle aren't known yet."""
        cards = self._get_mediums(ctx["config"], ("credit_card",))
        if not cards:
            return []
        figures = self._compute_cards(ctx, cards)
        flows = []
        for card in cards:
            card_figures = figures[card.id]
            parts = [
                (max(card_figures["last_due"], ctx["today"]), card_figures["closed_unpaid"],
                 self.env._("%(card)s: statement closed on %(date)s", card=card.name,
                            date=format_date(self.env, card_figures["last_closing"]))),
                (card_figures["next_due"], card_figures["consumption"],
                 self.env._("%(card)s: current cycle (closing on %(date)s)", card=card.name,
                            date=format_date(self.env, card_figures["next_closing"]))),
            ]
            for date, amount, label in parts:
                if not card.currency_id.is_zero(amount):
                    flows.append(self._flow(ctx, date, -self._valued(ctx, card, amount), "credit_cards", label,
                                            document=card.name))
        return flows

    def _flows_commitments(self, ctx):
        flows = []
        for commitment in self._get_commitments(ctx):
            category = "commitment_%s" % commitment.id
            if commitment.mode == "open_items":
                flows += self._open_items_flows(ctx, [("account_id", "in", commitment.account_ids.ids)], category)
                continue
            balance = self.env["account.move.line"].sudo()._read_group(
                [
                    ("company_id", "=", ctx["company"].id),
                    ("parent_state", "=", "posted"),
                    ("date", "<=", ctx["today"]),
                    ("account_id", "in", commitment.account_ids.ids),
                ],
                aggregates=["balance:sum"],
            )[0][0] or 0.0
            if balance < 0 and not ctx["currency"].is_zero(balance):
                date = treasury_dates.next_day_of_month(ctx["today"], commitment.payment_day)
                flows.append(self._flow(
                    ctx, date, balance, category,
                    self.env._("%s: account balance", commitment.name), document=commitment.name,
                ))
        return flows

    # -------------------------------------------------------------------------
    # Projection
    # -------------------------------------------------------------------------

    def _opening_balances(self, ctx):
        """{medium: balance of its bank account, in the company currency}."""
        mediums = self._get_mediums(ctx["config"], ("bank", "cash"), available_only=True)
        liquidity = self._read_liquidity_balances(ctx, mediums)
        return {
            medium: self._valued(ctx, medium, self._medium_amount(
                medium, liquidity[medium.id]["balance"], liquidity[medium.id]["amount_currency"]))
            for medium in mediums
        }

    def _compute_projection(self, ctx):
        weeks = treasury_dates.projection_weeks(ctx["today"], ctx["config"].projection_weeks)
        categories = self._projection_categories(ctx)
        known = {category["key"] for category in categories} | {OVERDUE_RECEIVABLES}
        flows = []
        for provider in self._projection_flow_providers():
            for flow in getattr(self, provider)(ctx):
                if flow["category"] not in known:
                    continue
                index = treasury_dates.week_index(weeks, flow["date"])
                if index is None:
                    continue  # beyond the projection's horizon
                flows.append({**flow, "week": index})
        cells = {key: [0.0] * len(weeks) for key in known}
        for flow in flows:
            cells[flow["category"]][flow["week"]] += flow["amount"]
        opening = sum(self._opening_balances(ctx).values())
        openings, closings, nets = [], [], []
        balance = opening
        for index in range(len(weeks)):
            net = sum(cells[category["key"]][index] for category in categories)
            openings.append(balance)
            balance += net
            nets.append(net)
            closings.append(balance)
        return {
            "weeks": weeks,
            "categories": categories,
            "flows": flows,
            "cells": cells,
            "opening": opening,
            "openings": openings,
            "nets": nets,
            "closings": closings,
        }

    def _week_label(self, index, week):
        return self.env._("Week %(number)s (%(start)s - %(end)s)", number=index + 1,
                          start=format_date(self.env, week[0], date_format="dd/MM"),
                          end=format_date(self.env, week[1], date_format="dd/MM"))

    def _section_projection(self, ctx):
        currency = ctx["currency"]
        projection = self._compute_projection(ctx)
        weeks = projection["weeks"]
        week_keys = ["week_%s" % index for index in range(len(weeks))]
        alerts = []

        def flows_drill(category, week):
            return blocks.drilldown("flows", category=category, week=week)

        rows = [blocks.row("opening", {
            "label": blocks.value(self.env._("Opening balance")),
            **{key: blocks.money(projection["openings"][index], currency,
                                 drilldown=blocks.drilldown("opening") if index == 0 else None)
               for index, key in enumerate(week_keys)},
            "total": blocks.money(projection["opening"], currency),
        }, style="subtotal")]
        for category in projection["categories"]:
            values = projection["cells"][category["key"]]
            rows.append(blocks.row(category["key"], {
                "label": blocks.value(category["label"]),
                **{key: blocks.money(values[index], currency,
                                     drilldown=flows_drill(category["key"], index) if values[index] else None)
                   for index, key in enumerate(week_keys)},
                "total": blocks.money(sum(values), currency,
                                      drilldown=flows_drill(category["key"], "total") if any(values) else None),
            }))
        rows.append(blocks.row("net", {
            "label": blocks.value(self.env._("Net")),
            **{key: blocks.money(projection["nets"][index], currency) for index, key in enumerate(week_keys)},
            "total": blocks.money(sum(projection["nets"]), currency),
        }, style="subtotal"))
        rows.append(blocks.row("closing", {
            "label": blocks.value(self.env._("Projected balance")),
            **{key: blocks.money(projection["closings"][index], currency,
                                 alert="danger" if projection["closings"][index] < 0 else None)
               for index, key in enumerate(week_keys)},
            "total": blocks.money(projection["closings"][-1], currency),
        }, style="total"))
        overdue = projection["cells"][OVERDUE_RECEIVABLES]
        if not ctx["config"].include_overdue_receivables:
            rows.append(blocks.row(OVERDUE_RECEIVABLES, {
                "label": blocks.value(self.env._("Overdue receivables (not included)")),
                **{key: blocks.money(overdue[index], currency,
                                     drilldown=flows_drill(OVERDUE_RECEIVABLES, index) if overdue[index] else None)
                   for index, key in enumerate(week_keys)},
                "total": blocks.money(sum(overdue), currency),
            }, style="muted"))

        negative_weeks = [index for index, closing in enumerate(projection["closings"]) if closing < 0]
        for index in negative_weeks:
            alerts.append(blocks.alert("danger", self.env._(
                "Negative projected balance in %(week)s: %(amount)s.",
                week=self._week_label(index, weeks[index]),
                amount=self._format_amount(projection["closings"][index], currency),
            )))
        minimum_index = min(range(len(weeks)), key=lambda index: projection["closings"][index])
        cards = [
            blocks.card(self.env._("Opening balance"),
                        blocks.money(projection["opening"], currency, drilldown=blocks.drilldown("opening")),
                        blocks.value(self.env._("Bank accounts as of today"), "text")),
            blocks.card(self.env._("Minimum projected balance"),
                        blocks.money(projection["closings"][minimum_index], currency,
                                     alert="danger" if projection["closings"][minimum_index] < 0 else None),
                        blocks.value(self._week_label(minimum_index, weeks[minimum_index]), "text"),
                        alert=blocks.alert("danger", self.env._("Negative balance"))
                        if projection["closings"][minimum_index] < 0 else None),
            blocks.card(self.env._("Projected balance at the end"),
                        blocks.money(projection["closings"][-1], currency),
                        blocks.value(format_date(self.env, weeks[-1][1]), "text")),
        ]
        if not ctx["config"].include_overdue_receivables and any(overdue):
            cards.append(blocks.card(
                self.env._("Overdue receivables"),
                blocks.money(sum(overdue), currency, drilldown=flows_drill(OVERDUE_RECEIVABLES, "total")),
                blocks.value(self.env._("Not included in the projected balance"), "text"),
            ))
        labels = [self._week_label(index, week) for index, week in enumerate(weeks)]
        columns = [blocks.column("label", "")]
        columns += [blocks.column(key, labels[index], "monetary") for index, key in enumerate(week_keys)]
        columns.append(blocks.column("total", self.env._("Total"), "monetary"))
        return {"alerts": alerts, "blocks": [
            blocks.cards_block(cards),
            blocks.table_block(
                columns, rows,
                note=self.env._(
                    "Starts from the bank accounts' balance: recorded receipts and payments not in the bank yet "
                    "come in as in-transit flows in week 1. Overdue vendor payables fall in week 1. Foreign "
                    "currency residuals valued at the rate of the day; credit card statements estimated from the "
                    "purchases up to today. Flows after the last week are left out."
                ),
            ),
            blocks.chart_block(
                labels,
                [
                    {"label": self.env._("Net"), "kind": "bar", "values": projection["nets"]},
                    {"label": self.env._("Projected balance"), "kind": "line", "values": projection["closings"]},
                ],
                currency=currency,
            ),
        ]}

    def _format_amount(self, amount, currency):
        return formatLang(self.env, amount, currency_obj=currency)

    # -------------------------------------------------------------------------
    # Drill-down
    # -------------------------------------------------------------------------

    def _drilldown_projection(self, key, params, ctx):
        currency = ctx["currency"]
        if key == "opening":
            openings = self._opening_balances(ctx)
            rows = [{"key": str(medium.id), "cells": {
                "name": blocks.value(medium.name),
                "amount": blocks.money(amount, currency),
            }} for medium, amount in openings.items()]
            return self._popup(
                self.env._("Opening balance: bank accounts"),
                [blocks.column("name", self.env._("Payment mean")),
                 blocks.column("amount", self.env._("Bank account balance"), "monetary")],
                rows,
                total=blocks.money(sum(openings.values()), currency),
            )
        if key != "flows":
            raise UserError(self.env._("This figure has no detail."))
        projection = self._compute_projection(ctx)
        category, week = params.get("category"), params.get("week")
        flows = [flow for flow in projection["flows"]
                 if flow["category"] == category and (week == "total" or flow["week"] == week)]
        flows.sort(key=lambda flow: (flow["date"], flow["document"]))
        labels = {entry["key"]: entry["label"] for entry in projection["categories"]}
        labels[OVERDUE_RECEIVABLES] = self.env._("Overdue receivables")
        title = labels.get(category, category)
        if week != "total":
            title = "%s - %s" % (title, self._week_label(week, projection["weeks"][week]))
        rows = [{
            "key": str(index),
            "record": (flow["res_model"], flow["res_id"]) if flow["res_model"] else None,
            "cells": {
                "document": blocks.value(flow["document"] or flow["label"]),
                "partner": blocks.value(flow["partner"]),
                "date": blocks.value(flow["date"], "date"),
                "amount": blocks.money(flow["amount"], currency),
            },
        } for index, flow in enumerate(flows)]
        return self._popup(
            title,
            [blocks.column("document", self.env._("Document")),
             blocks.column("partner", self.env._("Partner")),
             blocks.column("date", self.env._("Expected date"), "date"),
             blocks.column("amount", self.env._("Amount"), "monetary")],
            rows,
            total=blocks.money(sum(flow["amount"] for flow in flows), currency),
        )
