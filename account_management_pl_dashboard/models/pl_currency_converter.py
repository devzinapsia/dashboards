from odoo import fields
from odoo.exceptions import UserError


class PlCurrencyConverter:
    """Expresses company-currency journal items in a secondary currency:

    a. a journal item whose own currency is the secondary currency keeps its
       original amount (amount_currency), without any conversion;
    b. any other journal item (company currency, or a third currency) has its
       company-currency balance converted at the **latest loaded rate** of
       the secondary currency, the same one for every month (so the figures
       of past months change when a new rate is loaded).

    Rates come from res.currency.rate only. Like Odoo's own
    ``res.currency._get_rates``, the company-specific rates (root company)
    win over the shared ones (company_id empty). A currency with no rate at
    all raises an error rather than silently converting at 1.0.
    """

    def __init__(self, env, company, target_currency):
        self.env = env
        self.company = company
        self.company_currency = company.currency_id
        self.target_currency = target_currency
        today = fields.Date.context_today(env["res.users"])
        target_rate, self.rate_date = self._latest_rate(target_currency, today)
        if not target_rate:
            raise UserError(self.env._(
                "There is no %(currency)s exchange rate loaded yet. Load one, or view the dashboard in the "
                "company currency.",
                currency=target_currency.name,
            ))
        # The company currency is normally the reference (rate 1, often with
        # no rate records at all), exactly like in Odoo's own _get_rates.
        company_rate, _date = self._latest_rate(self.company_currency, today)
        self.factor = target_rate / (company_rate or 1.0)

    def _latest_rate(self, currency, today):
        """(rate, date) of the latest rate loaded up to today, or (None, None)."""
        Rate = self.env["res.currency.rate"].sudo()
        for company_domain in ([("company_id", "=", self.company.root_id.id)], [("company_id", "=", False)]):
            rate = Rate.search([
                ("currency_id", "=", currency.id),
                ("name", "<=", today),
                *company_domain,
            ], order="name desc", limit=1)
            if rate:
                return rate.rate, rate.name
        return None, None

    @property
    def company_units_per_unit(self):
        """The rate as usually quoted: company-currency units per unit of the
        secondary currency (e.g. 1,450 ARS per USD)."""
        return 1.0 / self.factor

    def convert_balance(self, amount):
        """Company-currency amount in the target currency."""
        return (amount or 0.0) * self.factor

    def convert_move_lines(self, currency_id, balance, amount_currency):
        """Amount in the target currency of a group of journal items sharing
        the same currency, keeping the accounting sign (debit positive)."""
        if currency_id == self.target_currency.id:
            # Original amount, never re-converted. Exchange difference items
            # (amount_currency = 0, balance != 0) therefore contribute 0.
            return amount_currency or 0.0
        return self.convert_balance(balance)
