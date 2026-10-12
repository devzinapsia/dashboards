from odoo import models
from odoo.exceptions import UserError
from odoo.fields import Domain
from odoo.tools import format_date

from . import treasury_blocks as blocks
from . import treasury_dates

PERIODS = ("current", "previous_same_day", "previous")


class AccountTreasuryDashboard(models.AbstractModel):
    """Section "Period movements": money in and out of the payment means
    included in the available total, in the company currency (accounting
    amounts), for the current month to date, the previous month to the same
    day and the whole previous month.

    Movements are netted by journal entry over the payment means' journal
    items (own accounts and in-transit accounts): an entry adding money is
    an inflow, one taking money out an outflow. Internal transfers (see
    _is_internal_transfer) are left out of both and shown on their own.
    """

    _inherit = "account.treasury.dashboard"

    def _movement_periods(self, ctx):
        current, previous, previous_same_day = treasury_dates.month_bounds(ctx["today"])
        return {"current": current, "previous": previous, "previous_same_day": previous_same_day}

    def _classify_movements(self, ctx):
        """{period: {"income": [(move_id, date, amount)], "expense": [...],
        "transfer": [...]}}, amounts positive."""
        config = ctx["config"]
        available = self._get_mediums(config, available_only=True)
        liquid = self._get_liquid_mediums(config)
        liquid_ids = set(liquid.ids)
        available_ids = set(available.ids)
        periods = self._movement_periods(ctx)
        date_from = min(bounds[0] for bounds in periods.values())
        moves = self._read_move_nets(ctx, liquid | available, date_from=date_from, focus=available)
        currency = ctx["currency"]
        result = {period: {"income": [], "expense": [], "transfer": []} for period in periods}
        for move in moves:
            if self._is_internal_transfer(ctx, move, liquid_ids):
                kind = "transfer"
                # The money arriving to a payment mean (the leaving side of a
                # transfer made of two entries is its pair's arriving side).
                amount = sum(net["balance"] for medium_id, net in move["nets"].items()
                             if medium_id in liquid_ids and net["balance"] > 0)
            else:
                net = sum(net["balance"] for medium_id, net in move["nets"].items() if medium_id in available_ids)
                kind = "income" if net > 0 else "expense"
                amount = abs(net)
            if currency.is_zero(amount):
                continue
            for period, (start, end) in periods.items():
                if start <= move["date"] <= end:
                    result[period][kind].append((move["move_id"], move["date"], amount))
        return result

    def _variation(self, current, previous):
        if not previous:
            return None
        return (current - previous) / abs(previous) * 100

    def _section_movements(self, ctx):
        currency = ctx["currency"]
        movements = self._classify_movements(ctx)
        totals = {
            period: {kind: sum(amount for _move, _date, amount in entries)
                     for kind, entries in kinds.items()}
            for period, kinds in movements.items()
        }
        for period_totals in totals.values():
            period_totals["net"] = period_totals["income"] - period_totals["expense"]

        def drill(period, kind):
            return blocks.drilldown("moves", period=period, kind=kind)

        row_labels = {}
        row_labels["income"] = self.env._("Inflows")
        row_labels["expense"] = self.env._("Outflows")
        row_labels["net"] = self.env._("Net")
        rows = []
        for kind, label in row_labels.items():
            cells = {"label": blocks.value(label)}
            for period in PERIODS:
                cells[period] = blocks.money(
                    totals[period][kind], currency,
                    drilldown=drill(period, kind) if kind != "net" else None,
                )
            variation = self._variation(totals["current"][kind], totals["previous_same_day"][kind])
            cells["variation"] = blocks.value(variation, "percent")
            rows.append(blocks.row(kind, cells, style="total" if kind == "net" else None))
        transfer_cells = {"label": blocks.value(self.env._("Internal transfers"))}
        for period in PERIODS:
            transfer_cells[period] = blocks.money(
                totals[period]["transfer"], currency, count=len(movements[period]["transfer"]),
                drilldown=drill(period, "transfer"),
            )
        transfer_cells["variation"] = blocks.value(False, "text")
        rows.append(blocks.row("transfer", transfer_cells, style="muted"))

        current = totals["current"]

        def versus(kind):
            variation = self._variation(current[kind], totals["previous_same_day"][kind])
            if variation is None:
                return blocks.value(self.env._("No movements the previous month to date"), "text")
            return blocks.value(self.env._("%(sign)s%(variation).1f%% vs the previous month to date",
                                           sign="+" if variation >= 0 else "", variation=variation), "text")

        cards = [
            blocks.card(self.env._("Inflows this month"),
                        blocks.money(current["income"], currency, drilldown=drill("current", "income")),
                        versus("income")),
            blocks.card(self.env._("Outflows this month"),
                        blocks.money(current["expense"], currency, drilldown=drill("current", "expense")),
                        versus("expense")),
            blocks.card(self.env._("Net this month"), blocks.money(current["net"], currency), versus("net")),
            blocks.card(self.env._("Internal transfers this month"),
                        blocks.money(current["transfer"], currency, drilldown=drill("current", "transfer")),
                        blocks.value(self.env._("1 transfer") if len(movements["current"]["transfer"]) == 1
                                     else self.env._("%s transfers", len(movements["current"]["transfer"])), "text")),
        ]
        periods = self._movement_periods(ctx)
        return {"blocks": [
            blocks.cards_block(cards),
            blocks.table_block(
                [
                    blocks.column("label", ""),
                    blocks.column("current", self.env._("This month to date"), "monetary"),
                    blocks.column("previous_same_day", self.env._("Previous month up to day %s", periods["previous_same_day"][1].day),
                                  "monetary"),
                    blocks.column("variation", self.env._("Variation"), "percent"),
                    blocks.column("previous", self.env._("Whole previous month"), "monetary"),
                ],
                rows,
                note=self.env._(
                    "Movements of the payment means in the available total, in %s (accounting amounts). Internal "
                    "transfers between payment means are left out of inflows and outflows.", currency.name,
                ),
            ),
        ]}

    def _drilldown_movements(self, key, params, ctx):
        if key != "moves" or params.get("period") not in PERIODS or params.get("kind") not in (
                "income", "expense", "transfer"):
            raise UserError(self.env._("This figure has no detail."))
        entries = self._classify_movements(ctx)[params["period"]][params["kind"]]
        start, end = self._movement_periods(ctx)[params["period"]]
        labels = {}
        labels["income"] = self.env._("Inflows")
        labels["expense"] = self.env._("Outflows")
        labels["transfer"] = self.env._("Internal transfers")
        mediums = self._get_mediums(ctx["config"], available_only=True)
        if params["kind"] == "transfer":
            mediums = self._get_liquid_mediums(ctx["config"])
        scope_domain = Domain.OR([self._scope_domain(medium_scope)
                                  for medium_scope in self._get_scope(mediums).values()])
        return self._moves_popup(
            ctx,
            "%s (%s - %s)" % (labels[params["kind"]], format_date(self.env, start), format_date(self.env, end)),
            entries,
            ctx["currency"],
            list_domain=list(Domain.AND([
                [("move_id", "in", [move_id for move_id, _date, _amount in entries])], scope_domain,
            ])),
        )
