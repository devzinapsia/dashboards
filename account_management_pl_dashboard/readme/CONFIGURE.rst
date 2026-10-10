Access rights
=============

Two groups, under *Settings > Users & Companies > Users > Dashboards >
Management P&L*:

- **User**: sees the dashboard, with no access to the configuration (nor
  to the accounting itself: the dashboard reads the journal items on its
  own, for the user's current company only).
- **Administrator**: also configures the structures (implies User).

Opening the journal items behind a figure still requires the usual
accounting read access.

Building the structure
======================

Go to *Dashboards > Configuration > Management P&L*: it opens the
structure of the current company directly, like a company setting (one
structure per company, created on first use). It has three sections:
Income, Direct costs and Indirect costs. They can be renamed but not
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
  accounts for Income, expense accounts for costs) and shows their
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
==========

- **Excluded journals**: their entries are ignored, typically the
  year-end closing entries, which would otherwise empty the previous
  fiscal year's columns.
- **Month column format**: how months are titled in the grid, the chart
  and the Excel export: *ene 2026* (default), *01-2026*, *enero 26*,
  *2026/01* or *2026-01*.
- **Secondary currency**: optional display currency (USD by default when
  active). It must be active and different from the company currency.
- **Open dashboard in**: currency the dashboard opens in.

Budgets
=======

The budget to compare with is picked in the dashboard's toolbar (see
*Usage*), among the company's **accounting budgets** (``account_reports``,
Enterprise): one amount per account and per month. They are created and
edited from *Accounting > Reporting > Profit and Loss*, with its *Budget*
filter (amounts are typed straight into the report's budget column).
Analytic budgets (*Accounting > Budgets*, ``account_budget``) are by
analytic account only, without accounts, so they can't be compared with
a structure built on accounts.
