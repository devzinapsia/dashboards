from freezegun import freeze_time

from odoo.exceptions import UserError
from odoo.tests import tagged

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
        secondary = self._line_row(self._secondary(), self.leaf_sales)["values"]
        self.assertEqual(secondary["2026-02"], 1234.56)
        local = self._line_row(self._local(), self.leaf_sales)["values"]
        self.assertAlmostEqual(local["2026-02"], 1234560.0)

    def test_usd_credit_note_reduces_sales(self):
        self._rate(self.usd, "2026-02-01", 1000.0)
        self._invoice("2026-02-10", 1000.0, self.usd, self.customer_a)
        self._invoice("2026-02-20", 200.0, self.usd, self.customer_a, move_type="out_refund")
        data = self._secondary()
        self.assertAlmostEqual(self._line_row(data, self.leaf_sales)["values"]["2026-02"], 800.0)
        self.assertAlmostEqual(self._line_row(data, self.root_income)["values"]["2026-02"], 800.0)

    def test_peso_items_converted_at_the_latest_rate(self):
        self._rate(self.usd, "2026-01-10", 500.0)
        self._rate(self.usd, "2026-02-05", 1000.0)
        self._rate(self.usd, "2026-03-13", 2000.0)  # latest loaded rate
        # A rate dated after today is not loaded yet as far as the dashboard
        # is concerned.
        self._rate(self.usd, "2026-04-01", 9999.0)
        self._entry("2026-01-10", [(self.account_salaries, 1000.0, None)])
        self._entry("2026-02-05", [(self.account_salaries, 3000.0, None)])
        data = self._secondary()
        salaries = self._line_row(data, self.leaf_salaries)["values"]
        # Every month at the latest rate, whatever the rate of its own dates.
        self.assertAlmostEqual(salaries["2026-01"], 0.5)
        self.assertAlmostEqual(salaries["2026-02"], 1.5)
        self.assertEqual(data["secondary_rate"]["date"], "2026-03-13")
        self.assertAlmostEqual(data["secondary_rate"]["value"], 2000.0)
        self.assertAlmostEqual(self._line_row(self._local(), self.leaf_salaries)["values"]["2026-02"], 3000.0)
        self.assertFalse(self._local()["secondary_rate"])

    def test_company_rate_wins_over_shared_rate(self):
        self._rate(self.usd, "2026-02-01", 1000.0)
        self.env["res.currency.rate"].create({
            "currency_id": self.usd.id, "name": "2026-03-01", "rate": 1.0 / 4000.0, "company_id": False,
        })
        self._entry("2026-02-05", [(self.account_salaries, 1000.0, None)])
        self.assertAlmostEqual(self._line_row(self._secondary(), self.leaf_salaries)["values"]["2026-02"], 1.0)

    def test_third_currency_converted_from_balance(self):
        self._rate(self.usd, "2026-02-10", 1500.0)
        # 10 EUR booked at 15000 ARS: converted from the ARS balance at the
        # USD rate, not from the EUR amount.
        self._entry("2026-02-10", [(self.account_commissions, 15000.0, None, self.eur, 10.0)])
        self.assertAlmostEqual(
            self._line_row(self._secondary(), self.leaf_commissions)["values"]["2026-02"], 10.0,
        )

    def test_exchange_difference_is_zero_in_secondary(self):
        self._rate(self.usd, "2026-02-01", 1000.0)
        self._entry("2026-02-10", [(self.account_commissions, 500.0, None, self.usd, 0.0)])
        self.assertEqual(self._line_row(self._secondary(), self.leaf_commissions)["values"]["2026-02"], 0.0)
        self.assertAlmostEqual(self._line_row(self._local(), self.leaf_commissions)["values"]["2026-02"], 500.0)

    def test_no_rate_at_all_raises_in_secondary_only(self):
        self._entry("2026-02-10", [(self.account_salaries, 1000.0, None)])
        with self.assertRaisesRegex(UserError, "no USD exchange rate"):
            self._secondary()
        # The company currency view of the same period is not affected.
        self.assertAlmostEqual(self._line_row(self._local(), self.leaf_salaries)["values"]["total"], 1000.0)
        # Any rate, however old, is enough.
        self._rate(self.usd, "2020-01-01", 100.0)
        self.assertAlmostEqual(self._line_row(self._secondary(), self.leaf_salaries)["values"]["2026-02"], 10.0)

    def test_total_and_percentages_on_converted_values(self):
        self._rate(self.usd, "2026-02-15", 1000.0)
        self._entry("2026-01-15", [(self.account_salaries, 100000.0, None)])
        self._entry("2026-02-15", [(self.account_salaries, 100000.0, None)])
        self._invoice("2026-02-15", 1000.0, self.usd, self.customer_a)
        self._entry("2026-02-16", [(self.account_sales, -500000.0, self.customer_b)])
        data = self._secondary()
        direct = self._line_row(data, self.root_direct)["values"]
        self.assertAlmostEqual(direct["2026-01"], 100.0)
        self.assertAlmostEqual(direct["total"], direct["2026-01"] + direct["2026-02"])
        gross = self._row(data, "gross_profit")["values"]
        gross_pct = self._row(data, "gross_profit_pct")["values"]
        # Sales: USD 1,000 original + ARS 500,000 / 1,000.
        self.assertAlmostEqual(gross["total"], 1300.0)
        self.assertAlmostEqual(gross_pct["total"], 1300.0 / 1500.0 * 100.0)

    def test_other_secondary_currency(self):
        self.structure.secondary_currency_id = self.eur
        self._rate(self.eur, "2026-02-10", 1200.0)
        self._rate(self.usd, "2026-03-01", 3000.0)  # not the secondary currency anymore
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
