from datetime import date

from odoo.tests import BaseCase, tagged

from odoo.addons.account_treasury_dashboard.models import treasury_dates


@tagged("post_install", "-at_install")
class TestTreasuryDates(BaseCase):

    def test_closing_on_the_31st_in_february(self):
        last, upcoming = treasury_dates.card_closing_dates(date(2026, 2, 15), 31)
        self.assertEqual(last, date(2026, 1, 31))
        self.assertEqual(upcoming, date(2026, 2, 28))
        last, upcoming = treasury_dates.card_closing_dates(date(2028, 3, 1), 31)
        self.assertEqual(last, date(2028, 2, 29))  # leap year
        self.assertEqual(upcoming, date(2028, 3, 31))

    def test_closing_today_belongs_to_the_cycle(self):
        last, upcoming = treasury_dates.card_closing_dates(date(2026, 10, 5), 5)
        self.assertEqual(last, date(2026, 9, 5))
        self.assertEqual(upcoming, date(2026, 10, 5))

    def test_due_date_before_or_after_closing_day(self):
        # Due day lower than the closing day: following month.
        self.assertEqual(treasury_dates.card_due_date(date(2026, 10, 25), 10), date(2026, 11, 10))
        # Equal: following month too.
        self.assertEqual(treasury_dates.card_due_date(date(2026, 10, 10), 10), date(2026, 11, 10))
        # Higher: same month.
        self.assertEqual(treasury_dates.card_due_date(date(2026, 10, 5), 20), date(2026, 10, 20))
        # Clamped: closing on the 31st of February (the 28th), due on the 30th.
        self.assertEqual(treasury_dates.card_due_date(date(2026, 2, 28), 30), date(2026, 3, 30))
        # Closing on the 28th, due on the 31st of February: same day, so next month.
        self.assertEqual(treasury_dates.card_due_date(date(2026, 2, 28), 31), date(2026, 3, 31))

    def test_projection_weeks_monday_to_sunday(self):
        weeks = treasury_dates.projection_weeks(date(2026, 10, 14), 4)  # a Wednesday
        self.assertEqual(weeks, [
            (date(2026, 10, 14), date(2026, 10, 18)),
            (date(2026, 10, 19), date(2026, 10, 25)),
            (date(2026, 10, 26), date(2026, 11, 1)),
            (date(2026, 11, 2), date(2026, 11, 8)),
        ])
        for start, end in weeks[1:]:
            self.assertEqual(start.weekday(), 0)
            self.assertEqual(end.weekday(), 6)
        sunday_weeks = treasury_dates.projection_weeks(date(2026, 10, 18), 2)
        self.assertEqual(sunday_weeks[0], (date(2026, 10, 18), date(2026, 10, 18)))

    def test_week_index(self):
        weeks = treasury_dates.projection_weeks(date(2026, 10, 14), 4)
        self.assertEqual(treasury_dates.week_index(weeks, date(2026, 9, 1)), 0)  # overdue
        self.assertEqual(treasury_dates.week_index(weeks, date(2026, 10, 18)), 0)
        self.assertEqual(treasury_dates.week_index(weeks, date(2026, 10, 19)), 1)
        self.assertEqual(treasury_dates.week_index(weeks, date(2026, 11, 8)), 3)
        self.assertIsNone(treasury_dates.week_index(weeks, date(2026, 11, 9)))

    def test_next_day_of_month(self):
        self.assertEqual(treasury_dates.next_day_of_month(date(2026, 10, 14), 20), date(2026, 10, 20))
        self.assertEqual(treasury_dates.next_day_of_month(date(2026, 10, 14), 14), date(2026, 10, 14))
        self.assertEqual(treasury_dates.next_day_of_month(date(2026, 10, 14), 5), date(2026, 11, 5))
        self.assertEqual(treasury_dates.next_day_of_month(date(2027, 1, 31), 30), date(2027, 2, 28))

    def test_month_bounds(self):
        current, previous, previous_same_day = treasury_dates.month_bounds(date(2026, 3, 31))
        self.assertEqual(current, (date(2026, 3, 1), date(2026, 3, 31)))
        self.assertEqual(previous, (date(2026, 2, 1), date(2026, 2, 28)))
        self.assertEqual(previous_same_day, (date(2026, 2, 1), date(2026, 2, 28)))
