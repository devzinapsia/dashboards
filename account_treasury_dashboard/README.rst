==================
Treasury Dashboard
==================

Treasury dashboard ("tablero de tesorería"), built on top of
``dashboards_base``: one screen, for the current company (no
consolidation), with the cash position, the bank reconciliation status,
the investments, a cash projection week by week and the movements of the
period. Every figure opens a detail popup, and from there the standard
list behind it (journal items, payments, statement lines) when the user
can read it.

Every company is different, so everything specific is configured per
company in *Dashboards > Configuration > Treasury dashboard*: which
journals or accounts are a bank, cash, a petty cash fund, a prepaid card,
a credit card or an investment, which liabilities the projection pays out,
and the alert thresholds. A section with nothing configured for it is not
shown. "Today" is the date in the user's time zone.

Sections
========

Cash position
-------------

- **Banks**, one row per bank, as Odoo's bank reconciliation report
  (``account_reports``) defines its figures:

  - *Bank account balance*: balance of the journal's default account
    (posted entries up to today). Bank statement lines are posted to that
    account as soon as they are imported.
  - *In transit*: payments and receipts recorded and not matched with a
    bank statement yet. They sit on the outstanding receipts/payments
    accounts of the journal's payment methods (filtered by journal, since
    those accounts are usually shared), not on the bank account. Their
    residual is taken, as the report does.
  - *Book balance* = bank account balance + in transit.
  - *Last statement balance*: ending balance of the statement of the
    latest statement line belonging to a statement, with its date ("No
    statement" when there is none).
  - *Difference* = book balance - last statement balance. Its popup
    explains it: transactions without statement, miscellaneous operations
    on the bank account (journal items not coming from a statement line,
    after the lock date, without the opening entry nor the exchange
    difference journal), outstanding receipts, outstanding payments and
    the unexplained remainder (the report's "journal balance" warning).

  A *Total banks* row adds them up in the company currency.
- **Cash**: balance of the cash journal's account (plus in-transit items
  if its payment methods use outstanding accounts), with a *Total cash*.
- **Total available**: book balance of every payment mean with *In
  available total*, in the company currency, foreign currencies valued at
  the rate of the day.
- **Foreign currency**, per currency found (not only dollars), among the
  payment means of the available total whose account (or journal) is in
  that currency: original amount (sum of the amounts in currency), the
  equivalent in the company currency at the rate of the day, the book
  value (sum of the accounting balances) and the difference between both,
  i.e. the exchange difference not booked yet.
- **Petty cash funds and prepaid cards**: balance and last refill (date,
  amount, days since). The refill is the latest internal transfer into the
  fund or card. A prepaid card without a journal has no transfer of its
  own to follow: its last load is approximated by the latest entry debiting
  its accounts. "No refills" when there is none.
- **Credit cards**: purchases of the current cycle (credits net of
  refunds since the last closing; paying the card from a bank or cash is
  left out), total debt, last and next closing, next due date and days to
  it, limit and available credit (limit - total debt). The card closes on
  its closing day every month (the last day of the month when shorter,
  e.g. the 31st in February); a statement is due on the first due day
  after its closing (the following month when the due day is lower than
  or equal to the closing day).

Reconciliation
--------------

Per bank, the statement lines not reconciled yet
(``account.bank.statement.line.is_reconciled``), count and amount, by age
of the line's date: 0-7, 8-30, 31-60 and over 60 days (defined in one
constant, ``AGING_BUCKETS``), with totals per bank and overall.

The latest statement is the date of the bank's latest posted statement
line, whether it belongs to a statement or not: online synchronization and
file imports create lines without a statement, a statement's own date is
the date of its last line anyway, and the creation date would hide an old
file imported today. An alert shows when it is older than the bank's own
*Days without a new statement* or, if it has none, the general one.

Investments
-----------

Each investment account in its own currency (the one of its journal or
accounting account: pesos or dollars), its equivalent in the company
currency at the rate of the day, its book value, the exchange difference
not booked yet and its last movement, with a *Total investments*.

Cash projection
---------------

4 to 8 weeks: week 1 runs from today to the next Sunday, the following
ones from Monday to Sunday.

- **Opening balance**: balance of the BANK ACCOUNTS of the bank and cash
  payment means in the available total (foreign currencies at the rate of
  the day), on purpose not their book balance: what is recorded but not in
  the bank yet comes in as a flow (in transit, week 1). Starting from the
  book balance and adding those flows would count them twice.
- **Inflows**: customer receivables (open receivable items, by due date,
  or the entry date when there is none) and receipts in transit.
- **Outflows**: vendor payables (open payable items, by due date),
  payments in transit, credit card statements and the projection
  commitments.
- **Overdue** receivables are shown in a row of their own and don't add to
  the projected balance, unless *Include overdue receivables in week 1* is
  checked. Overdue payables do fall in week 1 (prudent criterion).
- **No double counting**: a payment reconciled with its invoice leaves no
  residual on the invoice, so it only shows as in transit until matched
  with the bank statement, and then only in the opening balance.
- A table per week (opening balance, each category, net and **projected
  balance**), a chart (bars: net; line: projected balance; zero line), an
  alert on every week with a negative projected balance and a card with the
  minimum projected balance and its week.

Period movements
----------------

Inflows and outflows of the payment means in the available total, in the
company currency (accounting amounts): current month to date, previous
month up to the same day (with the variation) and the whole previous
month. Movements are netted by journal entry over each payment mean's
items (own accounts and in-transit accounts): matching a statement line
with a payment, which only moves an amount from the outstanding account to
the bank account, nets to zero.

**Internal transfers** are left out of inflows and outflows and shown on
their own (count and amount arriving to a payment mean). An entry is an
internal transfer when:

- it has an item on the company's *Internal transfer account*. Odoo 19 has
  no ``is_internal_transfer`` field on payments any more: this covers the
  bank reconciliation's "internal transfer" model and the paired payments
  of internal transfer modules (e.g. ingadhoc's
  ``account_internal_transfer``, which uses that account as counterpart),
  without depending on them;
- or it moves money between two or more liquid payment means (bank, cash,
  petty cash fund, prepaid card, investment) and nets to zero across them.

Credit cards are not liquid payment means: paying a card statement from a
bank is an outflow.

Estimates and currencies
========================

- Foreign currency amounts (balances, residuals) are valued at the latest
  rate loaded up to today (company rates first, then shared ones). A rate
  older than today (weekends, holidays) is used and reported. A currency
  without any rate up to today makes the section show an error instead of
  a wrong amount; the other sections keep working.
- Credit card statements in the projection: what is owed for the closed
  cycle on its due date (week 1 when already due), and the purchases of
  the current cycle up to today on the following due date. Purchases of
  the rest of the cycle aren't known yet.
- Flows after the projection's last week are left out.

Phase 2 (not included)
======================

- Petty cash expenses not accounted for yet ("gastos sin rendir").
- Card purchases without a voucher ("consumos sin comprobante").

Configuration
=============

Access
------

In *Settings > Users & Companies > Users*, under *Dashboards > Treasury*:

- **User**: sees the dashboard, without access to its configuration.
- **Administrator**: also configures it.

Journal items are read on behalf of the dashboard, so its users don't need
accounting rights; the links from the popups to the standard lists only
show for users who can read them.

Settings
--------

*Dashboards > Configuration > Treasury dashboard* opens the current
company's settings (one per company).

General
~~~~~~~

- **Days without a new statement** (default 3): a bank whose latest
  statement line is older is flagged. Each bank can override it.
- **Projection weeks**: between 4 and 8 (default 6).
- **Include overdue receivables in week 1**: see *Cash projection*.
- **Sections**: show or hide each section.

Payment means
~~~~~~~~~~~~~

**Load suggested** adds a bank or cash payment mean for every bank and
cash journal not configured yet (it doesn't change or duplicate existing
ones, nor bring back an archived one). Petty cash funds, prepaid cards,
credit cards and investments are added by hand.

- **Bank** (tab *Banks and cash*): a journal of type Bank. *Days without
  a new statement* overrides the general setting (0 = general).
- **Cash**: a journal of type Cash.
- **Petty cash fund** (tab *Petty cash funds and prepaid cards*): its
  journal, of type Cash. Petty cash accounts are not reconciled.
- **Prepaid card**: a journal (Bank or Cash) and/or accounts, at least
  one. Not reconciled.
- **Credit card** (tab *Credit cards*): a journal and/or accounts, at
  least one, plus the closing day, the due day (1 to 31) and the credit
  limit. Odoo 19 has a *Credit Card* journal type (its default account is
  of type *Credit Card*): a card journal must be of that type.
- **Investment** (tab *Investments*): a journal of type Bank or
  Miscellaneous, and optionally more accounts. Its currency is the one of
  its journal or account (pesos or dollars).

**In available total** (checked by default for banks and cash) adds the
payment mean to the available total, to the projection's opening balance
(banks and cash only) and to the period movements.

A journal can only be in one payment mean, and an account in only one
payment mean or commitment; the error says where it is already used.

Projection commitments
~~~~~~~~~~~~~~~~~~~~~~

Liabilities the projection pays out (salaries, social charges, taxes,
...): a name, a type (label only) and their accounts. Their mode is
computed:

- **Open items**, when every account allows reconciliation: each open
  item is projected on its due date, with its partner.
- **Account balance**, when an account doesn't (e.g. salaries payable):
  its items can't be followed one by one, so the current credit balance
  of the accounts is projected on the next **payment day** (required in
  this mode).

The accounts of a commitment are left out of the generic customer
receivables and vendor payables, so they are never counted twice.

Usage
=====

Open *Dashboards > Boards > Treasury*. It works on the current company:
switch company in the top bar to see another one.

- Each section loads on its own: if one can't be computed (e.g. a missing
  exchange rate), it shows the reason and a *Retry* button, and the others
  keep working.
- Sections can be collapsed (*Expand all* / *Collapse all*); they stay as
  left when coming back from a list.
- Click any figure with a detail: a popup lists what makes it up (journal
  entries, payments, statement lines, flows of a projection week). The sum
  of a popup is the figure clicked. A row opens its record and *View all*
  the standard list behind it, when the user can read them.
- Amounts in red are negative; a warning sign marks a figure to look at
  (difference with the statement, old statement, negative projected
  balance, card over its limit or close to its due date).

Demo data
---------

``scripts/load_demo_data.py`` (not part of the module, never installed
with it) creates a company "Treasury dashboard demo" with banks, cash, a
petty cash fund, a prepaid card, a credit card, a dollar investment,
statements, payments in transit, invoices and bills, commitments and
internal transfers. Run it on a test database only::

    ./odoo-bin shell -c <config> -d <test_db> --addons-path=<...> \
        < account_treasury_dashboard/scripts/load_demo_data.py

For developers
--------------

A section is a provider: extend ``_get_section_providers()`` of
``account.treasury.dashboard`` and define ``_section_<id>()`` (generic
blocks, see ``models/treasury_blocks.py``) and ``_drilldown_<id>()``; no
JavaScript needed. The cash projection takes more flows from
``_projection_flow_providers()`` / ``_projection_categories()``, and
``_in_transit_exclusion_domain()`` takes journal items out of the generic
in-transit flows when another module projects them on their own date
(e.g. deferred checks).

Bug Tracker
===========

Bugs are tracked on `GitHub Issues <https://github.com/devzinapsia/dashboards/issues>`_.
In case of trouble, please check there if your issue has already been
reported, mentioning the ``account_treasury_dashboard`` module in the
issue title.

Credits
=======

Authors
-------

* Zinapsia
