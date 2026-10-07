from freezegun import freeze_time

from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tools import format_date

from .common import PlDashboardArsCommon


@tagged("post_install", "-at_install")
@freeze_time("2026-03-15")
class TestPlEngineSecondary(PlDashboardArsCommon):

    def _secondary(self, period="fiscal_year"):
        return self._data(period, display_currency="secondary")

    def _local(self, period="fiscal_year"):
        return self._data(period, display_currency="company")

    def test_structure_defaults_to_usd(self):
        self.assertEqual(self.company.currency_id.name, "ARS")
        self.assertEqual(self.structure.secondary_currency_id, self.usd)

    def test_usd_invoice_keeps_original_amount(self):
        rate = self._rate(self.usd, "2026-02-10", 1000.0)
        self._invoice("2026-02-10", 1234.56, self.usd, self.customer_a)
        # The rate of that day changes afterwards: the secondary view still
        # shows the invoice's original USD amount.
        rate.rate = 1.0 / 1500.0
        secondary = self._line_row(self._secondary(), self.leaf_customers)["values"]
        self.assertEqual(secondary["2026-02"], 1234.56)
        local = self._line_row(self._local(), self.leaf_customers)["values"]
        self.assertAlmostEqual(local["2026-02"], 1234560.0)

    def test_usd_credit_note_reduces_sales(self):
        self._rate(self.usd, "2026-02-01", 1000.0)
        self._invoice("2026-02-10", 1000.0, self.usd, self.customer_a)
        self._invoice("2026-02-20", 200.0, self.usd, self.customer_a, move_type="out_refund")
        data = self._secondary()
        self.assertAlmostEqual(self._line_row(data, self.leaf_customers)["values"]["2026-02"], 800.0)
        self.assertAlmostEqual(self._line_row(data, self.root_income)["values"]["2026-02"], 800.0)

    def test_peso_items_converted_at_their_accounting_date(self):
        self._rate(self.usd, "2026-02-05", 1000.0)
        self._rate(self.usd, "2026-02-20", 2000.0)
        self._entry("2026-02-05", [(self.account_salaries, 1000.0, None)])
        self._entry("2026-02-20", [(self.account_salaries, 2000.0, None)])
        # Same month, two different rates: 1000 / 1000 + 2000 / 2000.
        self.assertAlmostEqual(self._line_row(self._secondary(), self.leaf_salaries)["values"]["2026-02"], 2.0)
        self.assertAlmostEqual(self._line_row(self._local(), self.leaf_salaries)["values"]["2026-02"], 3000.0)

    def test_third_currency_converted_from_balance(self):
        self._rate(self.usd, "2026-02-10", 1500.0)
        # 10 EUR booked at 15000 ARS: converted from the ARS balance at the
        # USD rate of the day, not from the EUR amount.
        self._entry("2026-02-10", [(self.account_commissions, 15000.0, None, self.eur, 10.0)])
        self.assertAlmostEqual(
            self._line_row(self._secondary(), self.leaf_commissions)["values"]["2026-02"], 10.0,
        )

    def test_exchange_difference_is_zero_in_secondary(self):
        self._rate(self.usd, "2026-02-01", 1000.0)
        self._entry("2026-02-10", [(self.account_commissions, 500.0, None, self.usd, 0.0)])
        self.assertEqual(self._line_row(self._secondary(), self.leaf_commissions)["values"]["2026-02"], 0.0)
        self.assertAlmostEqual(self._line_row(self._local(), self.leaf_commissions)["values"]["2026-02"], 500.0)

    def test_missing_rate_raises_in_secondary_only(self):
        self._rate(self.usd, "2026-01-02", 1000.0)
        self._entry("2026-02-10", [(self.account_salaries, 1000.0, None)])
        self._entry("2026-01-01", [(self.account_salaries, 1000.0, None)])
        with self.assertRaises(UserError) as error:
            self._secondary()
        message = str(error.exception)
        # 2026-01-01: no rate at all yet; 2026-02-10: last rate is 39 days old.
        self.assertIn(format_date(self.env, "2026-01-01"), message)
        self.assertIn(format_date(self.env, "2026-02-10"), message)
        self.assertNotIn(format_date(self.env, "2026-01-02"), message)
        # The company currency view of the same period is not affected.
        local = self._line_row(self._local(), self.leaf_salaries)["values"]
        self.assertAlmostEqual(local["total"], 2000.0)

    def test_weekend_uses_last_rate_within_max_age(self):
        self._rate(self.usd, "2026-02-06", 1000.0)  # Friday
        self._entry("2026-02-08", [(self.account_salaries, 1000.0, None)])  # Sunday
        self.assertAlmostEqual(self._line_row(self._secondary(), self.leaf_salaries)["values"]["2026-02"], 1.0)
        self.structure.rate_max_age_days = 1
        with self.assertRaises(UserError):
            self._secondary()

    def test_total_and_percentages_on_converted_values(self):
        self._rate(self.usd, "2026-01-15", 500.0)
        self._rate(self.usd, "2026-02-15", 1000.0)
        self._entry("2026-01-15", [(self.account_salaries, 50000.0, None)])
        self._entry("2026-02-15", [(self.account_salaries, 100000.0, None)])
        self._invoice("2026-02-15", 1000.0, self.usd, self.customer_a)
        data = self._secondary()
        direct = self._line_row(data, self.root_direct)["values"]
        self.assertAlmostEqual(direct["2026-01"], 100.0)
        self.assertAlmostEqual(direct["2026-02"], 100.0)
        self.assertAlmostEqual(direct["total"], direct["2026-01"] + direct["2026-02"])
        gross = self._row(data, "gross_profit")["values"]
        gross_pct = self._row(data, "gross_profit_pct")["values"]
        self.assertAlmostEqual(gross["total"], 800.0)
        self.assertAlmostEqual(gross_pct["total"], 80.0)
        self.assertAlmostEqual(gross_pct["2026-02"], 90.0)
        # In ARS the same period gives another percentage (1,000,000 of sales,
        # 150,000 of costs): the % really is computed on converted values.
        self.assertAlmostEqual(self._row(self._local(), "gross_profit_pct")["values"]["total"], 85.0)

    def test_other_secondary_currency(self):
        self.structure.secondary_currency_id = self.eur
        self._rate(self.eur, "2026-02-10", 1200.0)
        self._entry("2026-02-10", [
            (self.account_commissions, 99999.0, None, self.eur, 10.0),
            (self.account_salaries, 2400.0, None),
        ])
        data = self._secondary()
        self.assertEqual(data["currency_id"], self.eur.id)
        self.assertAlmostEqual(self._line_row(data, self.leaf_commissions)["values"]["2026-02"], 10.0)
        self.assertAlmostEqual(self._line_row(data, self.leaf_salaries)["values"]["2026-02"], 2.0)

    def test_default_display_currency(self):
        self._rate(self.usd, "2026-01-01", 1000.0)
        self.assertEqual(self._data()["display_currency"], "company")
        self.structure.default_display_currency = "secondary"
        data = self._data()
        self.assertEqual(data["display_currency"], "secondary")
        self.assertEqual(data["currency_id"], self.usd.id)
        # The toolbar selector overrides it.
        data = self._data(display_currency="company")
        self.assertEqual(data["display_currency"], "company")
        self.assertEqual(data["currency_id"], self.company.currency_id.id)
