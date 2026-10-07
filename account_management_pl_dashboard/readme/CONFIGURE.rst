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

Go to *Dashboards > Configuration > Management P&L* and create the
structure of the company (only one can be active per company). Saving it
creates its three sections: Sales, Direct costs and Indirect costs. They
can be renamed but not deleted or moved.

Add the lines in the *Lines* tab, which shows the tree indented:

- Use **+ Sub-line** on a section or group to add a line below it, or *Add
  a line* and choose its parent line. Drag the handle to reorder lines
  among their siblings.
- A line with sub-lines is a **group**: its amount is the sum of its
  sub-lines, and it can't have anything assigned.
- A line without sub-lines is a **leaf**. Cost leaves get **accounts**;
  Sales leaves get **customers** (companies: their contacts are added up
  automatically) or **analytic accounts**, depending on the sales
  dimension. A leaf with assignments can't receive sub-lines.
- A leaf without assignments is flagged *Without accounts* / *Without
  customers* / *Without analytic accounts* and shows 0 in the dashboard.

**An account, a customer or an analytic account can only be used once**
in a structure (both cost sections together), and a Sales account can't
be used by a cost leaf: otherwise the same amount would be counted twice
(e.g. a commissions account under direct costs and again under indirect
costs). Saving such a structure fails with a message naming the line
that already uses it. Accounts must be income or expense accounts
available to the structure's company.

Parameters
==========

- **Sales dimension**: what Sales leaves group by, *Customer* (the
  commercial customer of each journal item) or *Analytic* (analytic
  accounts of the structure's analytic plan). Both assignments are kept
  on every leaf, so switching back and forth loses nothing; the lines
  list shows the one in use. Switching to *Analytic* requires the
  analytic usage to be set.
- **Sales accounts**: income accounts considered as Sales. Empty: every
  account of type *Income* of the company (*Other income*, e.g. exchange
  gains, is not Sales: map it to a cost leaf or leave it Unassigned).
- **Excluded journals**: their entries are ignored, typically the
  year-end closing entries, which would otherwise empty the previous
  fiscal year's columns.
- **Analytic usage**: *Not used*, *Analytic accounts* (of the selected
  root **Analytic plan**) or *Projects* (Odoo's project plan). When used,
  the dashboard toolbar offers a filter by those analytic accounts or
  projects, and Sales can be grouped by them. Analytic accounts of the
  lines must belong to that plan: with several plans, a journal item is
  split at 100% on each plan, and mixing plans would count it twice.
- **Secondary currency**: optional display currency (USD by default when
  active). It must be active and different from the company currency.
- **Open dashboard in**: currency the dashboard opens in.
- **Maximum rate age (days)**: see *Secondary currency* above.
- **Compare with budget** and **Budget**: accounting budget compared
  with the actual figures (see *Usage*).

Budgets
=======

The comparison uses Odoo's **accounting budgets** (``account_reports``,
Enterprise): one amount per account and per month. They are created and
edited from *Accounting > Reporting > Profit and Loss*, with its *Budget*
filter (amounts are typed straight into the report's budget column).
Analytic budgets (*Accounting > Budgets*, ``account_budget``) are by
analytic account only, without accounts, so they can't be compared with
a structure built on accounts.

Moving from customers to analytic accounts
==========================================

1. Set the *Analytic usage* (and the plan, if it is *Analytic
   accounts*).
2. Assign analytic accounts to the Sales leaves (the customers stay
   assigned).
3. Switch the *Sales dimension* to *Analytic*.

Sales are then read from the analytic lines of that plan, which already
have the analytic distribution applied, for the same posted entries,
dates and excluded journals.
