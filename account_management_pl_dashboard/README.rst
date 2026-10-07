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
conversion follows a **hybrid criterion**, journal item by journal item:

a. A journal item **in the secondary currency itself** keeps its
   **original amount** (``amount_currency``), never re-converted. A USD
   1,000.00 invoice shows USD 1,000.00, whatever the rate of the day is
   now.
b. **Any other journal item** (in pesos, or in a third currency such as
   EUR) has its company-currency balance converted at the rate of its
   **accounting date**: the most recent rate on or before that date,
   resolved like Odoo's own conversion (the company's rates first, then
   the shared ones). ARS 1,000,000 booked on a day at 1,000 ARS/USD shows
   USD 1,000.00; ARS 2,000,000 on a later day at 2,000 ARS/USD of the same
   month also shows USD 1,000.00, so the month shows USD 2,000.00. A EUR
   journal item is converted from its pesos, not from its euros.
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

A missing rate never turns into a silently wrong amount: if a needed day
has no rate, or its most recent rate is older than the *Maximum rate age*
of the structure (5 days by default, which covers weekends and bank
holidays), the secondary currency view shows a clear warning listing the
dates without a rate. The company currency view is not affected.

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

Opening the journal items behind a figure still requires the usual
accounting read access.

Building the structure
----------------------

Go to *Dashboards > Configuration > Management P&L*: it opens the
structure of the current company directly, like a company setting (one
structure per company, created on first use). It has three sections:
Sales, Direct costs and Indirect costs. They can be renamed but not
deleted or moved.

Add the lines in the *Lines* tab, which shows the tree indented:

- Use **+ Sub-line** on a section or group to add a line below it. Drag
  the handle to reorder lines among their siblings. The *Parent line*
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
- **Analytic usage**: *Not used*, *Analytic accounts* (of the selected
  root **Analytic plan**) or *Projects* (Odoo's project plan). When used,
  the dashboard toolbar offers a filter by those analytic accounts or
  projects. The filter uses a single plan: with several plans, a journal
  item is split at 100% on each plan, and mixing plans would count it
  twice.
- **Secondary currency**: optional display currency (USD by default when
  active). It must be active and different from the company currency.
- **Open dashboard in**: currency the dashboard opens in.
- **Maximum rate age (days)**: see *Secondary currency* above.
- **Compare with budget** and **Budget**: accounting budget compared
  with the actual figures (see *Usage*).

Budgets
-------

The comparison uses Odoo's **accounting budgets** (``account_reports``,
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
- **Analytic accounts / Projects** (only when the structure uses them):
  restricts every section to the share of each journal item distributed
  to the selected analytic accounts or projects.
- **Budget** (only when the structure compares with a budget).
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
------

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
