Access
======

In *Settings > Users & Companies > Users*, under *Dashboards > Treasury*:

- **User**: sees the dashboard, without access to its configuration.
- **Administrator**: also configures it.

Journal items are read on behalf of the dashboard, so its users don't need
accounting rights; the links from the popups to the standard lists only
show for users who can read them.

Settings
========

*Dashboards > Configuration > Treasury dashboard* opens the current
company's settings (one per company).

General
-------

- **Days without a new statement** (default 3): a bank whose latest
  statement line is older is flagged. Each bank can override it.
- **Projection weeks**: between 4 and 8 (default 6).
- **Include overdue receivables in week 1**: see *Cash projection*.
- **Sections**: show or hide each section.

Payment means
-------------

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
----------------------

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
