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

Clicking a figure (a section, a group, a line, a profit amount or the
Unassigned row) opens a popup, loaded on demand, with **the balance of
each account behind it** for the clicked column, in the currency being
displayed. The accounts always add up to the figure clicked. In a profit
row, cost accounts count negative (e.g. gross profit = Sales accounts -
direct cost accounts). Profit percentages have no drill-down.

- Clicking an account opens Odoo's **General Ledger** for that account and
  the period of the clicked column (the whole period in the Total column),
  without the structure's excluded journals; from the ledger, each line
  opens its journal entry. As usual in Odoo, the ledger starts with the
  account's balance since the beginning of the fiscal year (*Initial
  balance*), followed by the period's movements, which are the ones
  matching the popup.
- **View all journal items** lists every journal item of those accounts
  for the same period.

The General Ledger and the journal item lists are in **company currency**:
they can't total in the secondary currency. In the secondary currency
view the popup says so. With the analytic filter, an account opens its
analytic lines (the share distributed to the selected analytic accounts)
instead of the ledger. Opening ledgers and journal items requires the
usual accounting read access.

Budget
======

With the budget shown, each cell shows the actual figure and, below it,
the budget and the deviation, (actual - budget) / \|budget\|. In the
current month period, the grid shows explicit Actual | Budget |
Deviation % columns. A zero budget shows *n/a*. Colors tell good from bad
news: spending more than budgeted on costs, or selling less than
budgeted, is shown as unfavorable.

Budgets are by account: every leaf adds up the budget of its accounts,
and groups and sections add up their lines; the popup shows each
account's budget too. With the analytic filter, the budget is hidden.

In the **secondary currency**, the budget (in company currency) is first
allotted to each month, then **each month is converted at the rate of
its last day** (for the current month, the most recent rate). The
deviation shown in the secondary currency therefore **includes the
exchange rate effect**: spending exactly the budgeted pesos at a
different rate shows a deviation in dollars. The dashboard reminds it
with a note.
