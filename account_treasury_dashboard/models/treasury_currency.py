from odoo.exceptions import UserError
from odoo.tools import format_date


class TreasuryRates:
    """Values foreign currency amounts in the company currency at the rate of
    the day: the latest rate loaded up to today (the same one Odoo's own
    conversions use), company-specific rates (root company) winning over the
    shared ones.

    Unlike res.currency._convert(), which silently falls back to the oldest
    rate, or to 1.0 when a currency has no rate at all, a currency with no
    rate up to today raises an error: the dashboard section then shows it
    instead of a wrong amount. A rate older than today (weekends, holidays,
    or before the daily update) is used, and reported by is_stale().
    """

    def __init__(self, env, company, today):
        self.env = env
        self.company = company
        self.company_currency = company.currency_id
        self.today = today
        self._cache = {}

    def _latest_rate(self, currency):
        """(rate, date) of the latest rate up to today, or (None, None)."""
        Rate = self.env["res.currency.rate"].sudo()
        for company_domain in ([("company_id", "=", self.company.root_id.id)], [("company_id", "=", False)]):
            rate = Rate.search([
                ("currency_id", "=", currency.id),
                ("name", "<=", self.today),
                *company_domain,
            ], order="name desc", limit=1)
            if rate:
                return rate.rate, rate.name
        return None, None

    def get(self, currency):
        """(company currency units per unit of ``currency``, rate date)."""
        if not currency or currency == self.company_currency:
            return 1.0, None
        if currency.id not in self._cache:
            rate, rate_date = self._latest_rate(currency)
            if not rate:
                raise UserError(self.env._(
                    "There is no %(currency)s exchange rate loaded up to %(date)s: amounts in %(currency)s can't "
                    "be valued. Load the rate and refresh the dashboard.",
                    currency=currency.name,
                    date=format_date(self.env, self.today),
                ))
            # The company currency is normally the reference (rate 1, often
            # with no rate records at all), as in Odoo's own _get_rates.
            company_rate, _date = self._latest_rate(self.company_currency)
            self._cache[currency.id] = ((company_rate or 1.0) / rate, rate_date)
        return self._cache[currency.id]

    def to_company(self, amount, currency):
        """``amount`` in ``currency`` valued in the company currency."""
        return (amount or 0.0) * self.get(currency)[0]

    def is_stale(self, currency):
        rate_date = self.get(currency)[1]
        return bool(rate_date) and rate_date < self.today
