Management profit and loss dashboard ("estado de resultados de gestión"),
built on top of ``dashboards_base``. It replaces the spreadsheet usually
kept for this purpose with a grid computed straight from the accounting,
with drill-down down to the journal items, access rights, a comparison
with the accounting budget and a view in a secondary currency.

It is a **management** P&L, not a legal one: income and expenses are
organized in a structure defined by the administrator, in rows that make
sense for the business (Salaries, IT infrastructure, Sales commissions,
...) rather than in the chart of accounts' order.

- Three fixed sections: **Income** (called *Sales* before version
  19.0.1.0.9; existing structures are renamed on update unless the section
  had been renamed by hand), **Direct costs** and **Indirect costs**.
  Below each one, groups and leaves are freely defined. Every leaf groups
  one or more accounts and shows their balance: income accounts for
  Income, expense accounts for costs.
- Rows computed from the sections, defined in a single place of the code
  (``COMPUTED_ROWS``) so that more can be added later:

  - Gross profit = Income - Direct costs
  - Gross profit % = Gross profit / Income
  - Net profit = Income - (Direct costs + Indirect costs)
  - Net profit % = Net profit / Income

  When Income is 0, percentages are left empty (never a division by
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
   debit - credit; Income: credit - debit, so credit notes subtract on
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
