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

*Dashboards > Configuration > Treasury* opens the current
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

**Load suggested** adds a payment mean for every active (not archived)
bank, cash and credit card journal not configured yet: bank journals as
banks (tab *Banks*), cash journals as cash (tab *Petty cash funds and
prepaid cards*; change the type of those that are petty cash funds) and
credit card journals as credit cards (closing on the 30th, due on the 8th;
adjust them and set the credit limit). Journals of the same type booking on
the same default account get a single payment mean: one credit card
named after the account, with the account and all the journals booking on
it (e.g. one per cardholder of the same card). It doesn't
change or duplicate existing ones, nor bring back an archived one. Prepaid
cards and investments are added by hand.

A journal can only be in one payment mean (its balance would otherwise be
counted twice): to turn a cash payment mean into a petty cash fund, change
its type rather than adding the journal again.

- **Bank** (tab *Banks*): a journal of type Bank. *Days without a new
  statement* overrides the general setting (0 = general).
- **Cash** (tab *Petty cash funds and prepaid cards*): a journal of type
  Cash.
- **Petty cash fund** (same tab): its journal, of type Cash. Petty cash
  accounts are not reconciled.
- **Prepaid card**: a journal (Bank or Cash) and/or accounts, at least
  one. Not reconciled.
- **Credit card** (tab *Credit cards*): its **journals** (of type Credit
  Card; their account is added to *Accounts* when they are chosen) and/or
  accounts, at least one, plus the closing day, the due day (1 to 31) and
  the credit limit. A card whose cardholders have a journal
  each, all booking on the card's account, is a single credit card listing
  all those journals: it is computed once (debt, current cycle, limit),
  with the items in transit of every one of them. Odoo 19 has a *Credit Card* journal type (its default account is
  of type *Credit Card*): a card journal must be of that type.
- **Investment** (tab *Investments*): a journal of type Bank or
  Miscellaneous, and optionally more accounts. Its currency is the one of
  its journal or account (pesos or dollars). Check **In cash projection**
  for the investments that count as money available in the cash
  projection: their balance (at the rate of the day) adds up to its
  opening balance.

**In available total** (checked by default for banks and cash) adds the
payment mean to the available total, to the projection's opening balance
(banks and cash only) and to the period movements.

A journal can only be in one payment mean, and an account in only one
payment mean or commitment; the error says where it is already used.

Projection commitments
----------------------

Liabilities the projection pays out (salaries, social charges, taxes,
...): their accounts, a type (label only) and a name (the accounts' names
when left empty). Their mode is computed:

- **Open items**, when every account allows reconciliation: each open
  item is projected on its due date (the due date of its journal item),
  with its partner.
- **Account balance**, when an account doesn't (e.g. salaries payable):
  its items can't be followed one by one, so the current credit balance
  of the accounts is projected on the due date of the latest entry
  crediting them (week 1 once past), or on the next **payment day** if one
  is set. The payment day is optional.

The accounts of a commitment are left out of the generic customer
receivables and vendor payables, so they are never counted twice.
