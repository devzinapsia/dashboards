"""Date rules of the treasury dashboard, as plain functions (no ORM), so
that they can be tested on their own."""
import calendar
from datetime import timedelta

from dateutil.relativedelta import relativedelta


def day_in_month(year, month, day):
    """``day`` of the given month, clamped to the month's last day (e.g. the
    31st of February is February 28th or 29th)."""
    return min(day, calendar.monthrange(year, month)[1])


def date_in_month(reference, day):
    """The date of ``reference``'s month falling on ``day`` (clamped)."""
    return reference.replace(day=day_in_month(reference.year, reference.month, day))


def card_closing_dates(today, closing_day):
    """(last closing, next closing) of a credit card closing on
    ``closing_day`` of every month.

    The last closing is strictly before today and the next one is today or
    later: a statement closing today still includes today's purchases.
    """
    this_month = date_in_month(today, closing_day)
    if this_month >= today:
        next_closing = this_month
        last_closing = date_in_month(today - relativedelta(months=1), closing_day)
    else:
        last_closing = this_month
        next_closing = date_in_month(today + relativedelta(months=1), closing_day)
    return last_closing, next_closing


def card_due_date(closing, due_day):
    """Due date of the statement closing on ``closing``: the first
    occurrence of ``due_day`` after the closing (in the same month when it
    falls after the closing day, otherwise in the following month)."""
    same_month = date_in_month(closing, due_day)
    if same_month > closing:
        return same_month
    return date_in_month(closing + relativedelta(months=1), due_day)


def next_day_of_month(today, day):
    """The next occurrence of ``day`` of the month, today included."""
    this_month = date_in_month(today, day)
    if this_month >= today:
        return this_month
    return date_in_month(today + relativedelta(months=1), day)


def projection_weeks(today, count):
    """The projection's weeks, as (start, end) date pairs: week 1 runs from
    today to the next Sunday (today itself if it is a Sunday), the following
    ones from Monday to Sunday."""
    first_end = today + timedelta(days=6 - today.weekday())
    weeks = [(today, first_end)]
    for index in range(1, count):
        start = first_end + timedelta(days=1 + 7 * (index - 1))
        weeks.append((start, start + timedelta(days=6)))
    return weeks


def week_index(weeks, date):
    """Index of the week ``date`` falls in, 0 for dates up to the end of
    week 1 (overdue dates included), None after the last week."""
    if date <= weeks[0][1]:
        return 0
    for index, (start, end) in enumerate(weeks):
        if start <= date <= end:
            return index
    return None


def month_bounds(today):
    """Period bounds of the "period movements" section:
    (current month start, today), (previous month start, previous month
    end) and (previous month start, same day of the previous month)."""
    current_start = today.replace(day=1)
    previous_end = current_start - timedelta(days=1)
    previous_start = previous_end.replace(day=1)
    previous_same_day = date_in_month(previous_start, today.day)
    return (current_start, today), (previous_start, previous_end), (previous_start, previous_same_day)
