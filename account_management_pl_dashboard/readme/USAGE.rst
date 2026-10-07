Go to *Dashboards > Boards > Management P&L*. The company is the one
selected in Odoo's company switcher.

Toolbar
=======

- **Period**: current month, current fiscal year, previous fiscal year
  or last 12 months. Months after the current one are left empty, not 0.
- **Currency**: company currency or secondary currency.
- **Analytic accounts / Projects** (only when the structure uses them):
  restricts every section to the share of each journal item distributed
  to the selected analytic accounts or projects.
- **Budget** (only when the structure compares with a budget).
- **Expand all**, **Collapse all** and **Refresh**. Sections and groups
  also collapse one by one with their arrow.

The Unassigned row
==================

A control row, shown below the profits only when it isn't zero: the
movements of income and expense accounts that no line includes.
It is **not included** in the totals nor in the profits. Its sign is the
effect on the result (income positive), so that **Net profit +
Unassigned = accounting result of the period**, which is how the
dashboard reconciles with the balance. It has a drill-down, like any
other line.

Drill-down
==========

Clicking a figure opens a popup with its detail, loaded on demand, in
the currency being displayed, and always adding up to the figure clicked:

- a section or group lists its leaves, which can be opened in turn;
- a cost leaf lists its accounts (code, name, amount), and an account
  opens its journal items for the period (posted entries, excluded
  journals left out);
- a Sales leaf breaks its accounts' movements down by commercial
  customer (contacts added up to their company); a customer opens its
  journal items;
- on any leaf, **View all journal items** opens every journal item of
  the leaf's accounts for the month (or the whole period, in the Total
  column) of the clicked cell;
- the Total column covers the whole period. Profit rows have no
  drill-down.

The journal item lists are standard Odoo lists, **in company currency**:
they can't total in the secondary currency. In the secondary currency
view the popup says so. With the analytic filter, the lists show the
analytic lines (the share distributed to the selected analytic accounts)
rather than the whole journal items.

Budget
======

With the budget shown, each cell shows the actual figure and, below it,
the budget and the deviation, (actual - budget) / \|budget\|. In the
current month period, the grid shows explicit Actual | Budget |
Deviation % columns. A zero budget shows *n/a*. Colors tell good from bad
news: spending more than budgeted on costs, or selling less than
budgeted, is shown as unfavorable.

Budgets are by account: every leaf adds up the budget of its accounts,
and groups and sections add up their lines. In a Sales leaf's popup, the
customers have no budget of their own ("—"), only the leaf. With the
analytic filter, the budget is hidden.

In the **secondary currency**, the budget (in company currency) is first
allotted to each month, then **each month is converted at the rate of
its last day** (for the current month, the most recent rate). The
deviation shown in the secondary currency therefore **includes the
exchange rate effect**: spending exactly the budgeted pesos at a
different rate shows a deviation in dollars. The dashboard reminds it
with a note.
