========================
Management P&L Dashboard
========================

Management profit and loss dashboard ("estado de resultados de gestión"),
built on top of ``dashboards_base``. It replaces the spreadsheet usually
kept for this purpose with a grid computed straight from the accounting,
with drill-down down to the journal items, access rights, a comparison
with the accounting budget and a view in a secondary currency.

It is a **management** P&L, not a legal one: income and expenses are
organized in a structure defined by the administrator, in rows that make
sense for the business (Salaries, IT infrastructure, Sales commissions,
...) rather than in the chart of accounts' order.

- Three fixed sections: **Sales**, **Direct costs** and **Indirect costs**.
  Below each one, groups and leaves are freely defined. Every leaf groups
  one or more accounts and shows their balance: income accounts for
  Sales, expense accounts for costs.
- Rows computed from the sections, defined in a single place of the code
  (``COMPUTED_ROWS``) so that more can be added later:

  - Gross profit = Sales - Direct costs
  - Gross profit % = Gross profit / Sales
  - Net profit = Sales - (Direct costs + Indirect costs)
  - Net profit % = Net profit / Sales

  When Sales are 0, percentages are left empty (never a division by
  zero).
- An informative **Unassigned** row (see *Usage*).
- Columns by month for the current month, the current or previous fiscal
  year (with a Total column) or the last 12 months, following the
  company's fiscal year settings, including non-calendar fiscal years.
- Only posted journal entries are counted, by accounting date, for the
  current company only (no consolidation), leaving out the excluded
  journals.

Secondary currency
==================

The dashboard can also be shown in a **secondary currency** (USD by
default), to reflect operations made in a foreign currency properly. The
conversion works journal item by journal item:

a. A journal item **in the secondary currency itself** keeps its
   **original amount** (``amount_currency``), never re-converted. A USD
   1,000.00 invoice shows USD 1,000.00, whatever the rate of the day is
   now.
b. **Any other journal item** (in pesos, or in a third currency such as
   EUR) has its company-currency balance converted at the **latest loaded
   rate** of the secondary currency (up to today, the company's rates
   first, then the shared ones, like Odoo's own conversion), **the same
   for every month**. With a latest rate of 1,450 ARS/USD, ARS 1,000,000
   shows USD 689.66 whatever its date, so past months change in USD when
   a new rate is loaded. A EUR journal item is converted from its pesos,
   not from its euros. The dashboard shows the rate used and its date.
c. **Exchange difference journal items** (in the secondary currency, with
   an amount in that currency of 0 and a pesos balance) contribute **0**
   in the secondary currency view: no dollar was gained or lost, only
   pesos. They show their normal amount in the company currency view.
d. Signs and formulas are the same as in the company currency (costs:
   debit - credit; Sales: credit - debit, so credit notes subtract on
   their own), applied to the amounts already expressed in the secondary
   currency.

The Total column is the sum of the converted months, and the profit
percentages are computed on converted amounts. Amounts are only rounded
when they are displayed.

Exchange rates come exclusively from Odoo's currency rates
(``res.currency.rate``), never from a separate table. With
``currency_rate_bna`` (repository ``account-financial-tools``), those are
Banco Nación's **"Divisas" selling rate** for USD, loaded once a day
through Odoo's automatic currency rate update.

A missing rate never turns into a silently wrong amount: if the secondary
currency has no rate loaded at all, the secondary currency view shows a
clear warning instead of converting at 1. The company currency view is
not affected.

Configuration
=============

Access rights
-------------

Two groups, under *Settings > Users & Companies > Users > Dashboards >
Management P&L*:

- **User**: sees the dashboard, with no access to the configuration (nor
  to the accounting itself: the dashboard reads the journal items on its
  own, for the user's current company only).
- **Administrator**: also configures the structures (implies User).

Opening the general ledger or the journal items behind a figure still requires the usual
accounting read access.

Building the structure
----------------------

Go to *Dashboards > Configuration > Management P&L*: it opens the
structure of the current company directly, like a company setting (one
structure per company, created on first use). It has three sections:
Sales, Direct costs and Indirect costs. They can be renamed but not
deleted or moved.

Add the lines in the *Lines* tab, which shows the tree indented:

- Use **+ Sub-line** on a section or group to add a line below it.
  **Add a line** adds a line at the same level as the selected row,
  right after it (at the end of the section when a section is selected,
  at the end of Indirect costs when no row is selected): it never creates
  a section, there are always exactly three. Drag the handle to reorder
  lines among their siblings. The *Parent line*
  column is hidden by default; show it from the list's optional columns
  to move a line elsewhere.
- **View**, at the end of each row (like in the chart of accounts),
  opens the line's form, with its accounts in a full list.
- A line with sub-lines is a **group**: its amount is the sum of its
  sub-lines, and it can't have accounts.
- A line without sub-lines is a **leaf**: it gets **accounts** (income
  accounts for Sales, expense accounts for costs) and shows their
  balance. A leaf with accounts can't receive sub-lines.
- A leaf without accounts is flagged *Without accounts* and shows 0 in
  the dashboard.

**An account can only be used once** in a structure, whatever the
section: otherwise the same amount would be counted twice (e.g. a
commissions account under direct costs and again under indirect costs).
Saving such a structure fails with a message naming the line that
already uses it. Accounts must be income or expense accounts available
to the structure's company.

Parameters
----------

- **Excluded journals**: their entries are ignored, typically the
  year-end closing entries, which would otherwise empty the previous
  fiscal year's columns.
- **Secondary currency**: optional display currency (USD by default when
  active). It must be active and different from the company currency.
- **Open dashboard in**: currency the dashboard opens in.

Budgets
-------

The budget to compare with is picked in the dashboard's toolbar (see
*Usage*), among the company's **accounting budgets** (``account_reports``,
Enterprise): one amount per account and per month. They are created and
edited from *Accounting > Reporting > Profit and Loss*, with its *Budget*
filter (amounts are typed straight into the report's budget column).
Analytic budgets (*Accounting > Budgets*, ``account_budget``) are by
analytic account only, without accounts, so they can't be compared with
a structure built on accounts.

Usage
=====

Go to *Dashboards > Boards > Management P&L*. The company is the one
selected in Odoo's company switcher.

Toolbar
-------

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
- **Export**: downloads the grid as shown (same period, currency,
  analytic filter and budget, every row expanded) as an Excel file.
- **Expand all**, **Collapse all** and **Refresh**. Sections and groups
  also collapse one by one with their arrow.

The Unassigned row
------------------

A control row, shown below the profits only when it isn't zero: the
movements of income and expense accounts that no line includes.
It is **not included** in the totals nor in the profits. Its sign is the
effect on the result (income positive), so that **Net profit +
Unassigned = accounting result of the period**, which is how the
dashboard reconciles with the balance. It has a drill-down, like any
other line.

Drill-down
----------

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
------

With the budget shown, each cell shows the actual figure and, below it,
the budget and the deviation, (actual - budget) / \|budget\|. In the
current month period, the grid shows explicit Actual | Budget |
Deviation % columns. A zero budget shows *n/a*. Colors tell good from bad
news: spending more than budgeted on costs, or selling less than
budgeted, is shown as unfavorable.

Budgets are by account: every leaf adds up the budget of its accounts,
and groups and sections add up their lines; the popup shows each
account's budget too. With the analytic filter, the budget is hidden.

In the **secondary currency**, the budget (in company currency) is
converted at the same latest rate as the actual figures, so spending
exactly the budgeted pesos shows no deviation in dollars either.

Bug Tracker
===========

Bugs are tracked on `GitHub Issues <https://github.com/devzinapsia/dashboards/issues>`_.
In case of trouble, please check there if your issue has already been
reported, mentioning the ``account_management_pl_dashboard`` module in the
issue title.

Credits
=======

Authors
-------

* Zinapsia
