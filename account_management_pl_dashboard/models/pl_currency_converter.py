from bisect import bisect_right
from collections import defaultdict
from datetime import timedelta

from odoo.exceptions import UserError
from odoo.tools import format_date

# Maximum number of missing dates listed in the error message.
MAX_MISSING_DATES_IN_MESSAGE = 10


class PlCurrencyConverter:
    """Expresses company-currency journal items in a secondary currency,
    following the "hybrid" criterion of the management P&L:

    a. a journal item whose own currency is the secondary currency keeps its
       original amount (amount_currency), without any conversion;
    b. any other journal item (company currency, or a third currency) has its
       company-currency balance converted at the rate of its accounting date.

    Rates come from res.currency.rate only, resolved the same way as Odoo's
    own ``res.currency._get_rates``: among the rates on or before the date,
    the company-specific ones (root company) win over the shared ones
    (company_id empty), and the most recent of them is used. Unlike Odoo,
    which silently falls back to the oldest known rate (or 1.0), a date with
    no rate, or whose most recent rate is older than ``max_age_days``, is
    recorded as missing and ``raise_if_missing`` reports it: a missing rate
    must never turn into a silently wrong amount.

    All rates needed for a dashboard request are loaded with a single query
    and looked up in memory, whatever the number of journal items.
    """

    def __init__(self, env, company, target_currency, max_age_days, date_to):
        self.env = env
        self.company = company
        self.company_currency = company.currency_id
        self.target_currency = target_currency
        self.max_age_days = max_age_days
        self.missing_dates = set()
        self._factor_cache = {}
        self._rates = self._load_rates(date_to)

    def _load_rates(self, date_to):
        """{currency_id: {"company": ([dates], [rates]), "shared": ([dates], [rates])}}"""
        root_company = self.company.root_id
        records = self.env["res.currency.rate"].sudo().search_read(
            [
                ("currency_id", "in", (self.target_currency | self.company_currency).ids),
                ("company_id", "in", (False, root_company.id)),
                ("name", "<=", date_to),
            ],
            ["currency_id", "company_id", "name", "rate"],
            order="name asc",
        )
        grouped = defaultdict(lambda: {"company": ([], []), "shared": ([], [])})
        for record in records:
            scope = "company" if record["company_id"] else "shared"
            dates, rates = grouped[record["currency_id"][0]][scope]
            dates.append(record["name"])
            rates.append(record["rate"])
        return grouped

    def _rate_at(self, currency, date):
        """Most recent (rate, rate_date) on or before ``date``, or (None, None)."""
        for scope in ("company", "shared"):
            dates, rates = self._rates[currency.id][scope]
            index = bisect_right(dates, date)
            if index:
                return rates[index - 1], dates[index - 1]
        return None, None

    def factor(self, date):
        """Multiplier converting a company-currency amount of ``date`` into
        the target currency, or None when the rate is missing."""
        if date in self._factor_cache:
            return self._factor_cache[date]
        target_rate, target_rate_date = self._rate_at(self.target_currency, date)
        # The company currency is normally the reference (rate 1, often with
        # no rate records at all), exactly like in Odoo's own _get_rates.
        company_rate, _company_rate_date = self._rate_at(self.company_currency, date)
        if not target_rate or (date - target_rate_date) > timedelta(days=self.max_age_days):
            self.missing_dates.add(date)
            factor = None
        else:
            factor = target_rate / (company_rate or 1.0)
        self._factor_cache[date] = factor
        return factor

    def convert_balance(self, amount, date):
        """Company-currency amount of ``date`` in the target currency (0.0,
        and the date recorded as missing, when there is no usable rate)."""
        if not amount:
            return 0.0
        factor = self.factor(date)
        return amount * factor if factor is not None else 0.0

    def convert_move_lines(self, date, currency_id, balance, amount_currency):
        """Amount in the target currency of a group of journal items sharing
        the same accounting date and currency, keeping the accounting sign
        (debit positive)."""
        if currency_id == self.target_currency.id:
            # Original amount, never re-converted. Exchange difference items
            # (amount_currency = 0, balance != 0) therefore contribute 0.
            return amount_currency or 0.0
        return self.convert_balance(balance, date)

    def raise_if_missing(self):
        if not self.missing_dates:
            return
        dates = sorted(self.missing_dates)
        listed = ", ".join(format_date(self.env, date) for date in dates[:MAX_MISSING_DATES_IN_MESSAGE])
        if len(dates) > MAX_MISSING_DATES_IN_MESSAGE:
            listed = self.env._("%(dates)s and %(count)s more", dates=listed, count=len(dates) - MAX_MISSING_DATES_IN_MESSAGE)
        raise UserError(self.env._(
            "%(currency)s exchange rates are missing for these dates (no rate within the previous %(days)s days): "
            "%(dates)s. Load the missing rates, or view the dashboard in the company currency.",
            currency=self.target_currency.name,
            days=self.max_age_days,
            dates=listed,
        ))
