Go to *Dashboards > Boards > Management P&L*. The company is the one
selected in Odoo's company switcher.

Toolbar
=======

- **Period**: current month, current fiscal year, previous fiscal year
  or last 12 months. Months after the current one are left empty, not 0.
- **Currency**: company currency or secondary currency.
- **Analytic filter**: pick an **analytic plan** (Odoo's *Projects* plan
  is one of them), then one or more of its **analytic accounts or
  projects**. Every section is then restricted to the share of each
  journal item distributed to them (a 1,000 item split 60% / 40% between
  two projects counts 600 for the first one), so that the projects add up
  to the company's total. Choosing a plan alone filters nothing yet. The
  analytic accounts must be of a single plan: with several plans, a
  journal item is split at 100% on each plan.
- **Budget**: the accounting budget to compare with, among the company's
  (*No budget*: no comparison).
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

Clicking a figure (a section, a group, a line or the Unassigned row)
opens a popup, loaded on demand, with **the balance of each account
behind it** for the clicked column, in the currency being displayed. The
accounts always add up to the figure clicked. Profit rows (amounts and
percentages) have no drill-down.

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
view the popup says so.

With the analytic filter, the popup's balances are the period's
movements distributed to the selected analytic accounts (no opening
balance), and an account opens the General Ledger with the same analytic
filter. Odoo's ledger lists the journal items carrying those analytic
accounts at their **full** amount: it matches the popup for items fully
distributed to them, not for items split with other analytic accounts.
**View all journal items** then lists the analytic lines, with the exact
shares. Users without analytic accounting rights get the analytic lines
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
