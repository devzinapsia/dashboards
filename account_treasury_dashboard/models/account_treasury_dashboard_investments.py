from odoo import models
from odoo.exceptions import UserError

from . import treasury_blocks as blocks


class AccountTreasuryDashboard(models.AbstractModel):
    """Section "Investments": each investment account in its own currency
    (the one of its journal or accounting account), valued in the company
    currency at the rate of the day, against its book value."""

    _inherit = "account.treasury.dashboard"

    def _read_last_movements(self, ctx, mediums):
        """{medium_id: {"date", "amount", "move_id"}}: latest entry moving each
        payment mean (in its own currency)."""
        result = {}
        for move in reversed(self._read_move_nets(ctx, mediums, focus=mediums)):
            for medium in mediums:
                net = move["nets"].get(medium.id)
                if medium.id in result or not net or ctx["currency"].is_zero(net["balance"]):
                    continue
                result[medium.id] = {
                    "date": move["date"],
                    "amount": self._medium_amount(medium, net["balance"], net["amount_currency"]),
                    "move_id": move["move_id"],
                }
            if len(result) == len(mediums):
                break
        return result

    def _section_investments(self, ctx):
        currency = ctx["currency"]
        investments = self._get_mediums(ctx["config"], ("investment",))
        books = self._compute_book_balances(ctx, investments)
        last_movements = self._read_last_movements(ctx, investments)
        rows = []
        total_equivalent = 0.0
        total_book = 0.0
        for medium in investments:
            original = books[medium.id]["book"]
            equivalent = self._valued(ctx, medium, original)
            book = books[medium.id]["book_company"]
            total_equivalent += equivalent
            total_book += book
            last = last_movements.get(medium.id)
            rows.append(blocks.row("medium-%s" % medium.id, {
                "name": blocks.value(medium.name),
                "currency": blocks.value(medium.currency_id.name),
                "original": blocks.money(original, medium.currency_id,
                                         drilldown=blocks.drilldown("balance", medium_id=medium.id)),
                "equivalent": blocks.money(equivalent, currency),
                "book": blocks.money(book, currency),
                "difference": blocks.money(equivalent - book, currency),
                "last_date": blocks.value(last["date"] if last else False, "date",
                                          drilldown=blocks.drilldown("last", medium_id=medium.id) if last else None),
                "last_amount": blocks.money(last["amount"], medium.currency_id) if last
                else blocks.value(False, "monetary"),
                "days": blocks.value((ctx["today"] - last["date"]).days if last else False, "days"),
            }))
        rows.append(blocks.row("total", {
            "name": blocks.value(self.env._("Total investments")),
            "currency": blocks.value(currency.name),
            "original": blocks.value(False, "text"),
            "equivalent": blocks.money(total_equivalent, currency),
            "book": blocks.money(total_book, currency),
            "difference": blocks.money(total_equivalent - total_book, currency),
            "last_date": blocks.value(False, "text"),
            "last_amount": blocks.value(False, "text"),
            "days": blocks.value(False, "text"),
        }, style="total"))
        return {"blocks": [
            blocks.cards_block([blocks.card(
                self.env._("Total investments"),
                blocks.money(total_equivalent, currency),
                blocks.value(self.env._("1 investment") if len(investments) == 1
                             else self.env._("%s investments", len(investments)), "text"),
            )]),
            blocks.table_block(
                [
                    blocks.column("name", self.env._("Investment")),
                    blocks.column("currency", self.env._("Currency")),
                    blocks.column("original", self.env._("Balance"), "monetary"),
                    blocks.column("equivalent", self.env._("Equivalent in %s", currency.name), "monetary"),
                    blocks.column("book", self.env._("Book value"), "monetary"),
                    blocks.column("difference", self.env._("Unrecognized exchange difference"), "monetary"),
                    blocks.column("last_date", self.env._("Last movement"), "date"),
                    blocks.column("last_amount", self.env._("Amount"), "monetary"),
                    blocks.column("days", self.env._("Days since"), "days"),
                ],
                rows,
                note=self.env._(
                    "Each investment in the currency of its account, valued in %s at the rate of the day.",
                    currency.name,
                ),
            ),
        ]}

    def _drilldown_investments(self, key, params, ctx):
        medium = self._get_medium(ctx, params.get("medium_id"))
        if key == "balance":
            return self._monthly_popup(ctx, medium, medium.name, parts=("own", "outstanding"))
        if key == "last":
            last = self._read_last_movements(ctx, medium).get(medium.id)
            entries = [(last["move_id"], last["date"], last["amount"])] if last else []
            return self._moves_popup(ctx, self.env._("%s: last movement", medium.name), entries, medium.currency_id)
        raise UserError(self.env._("This figure has no detail."))
