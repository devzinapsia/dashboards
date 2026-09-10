Executive dashboard for accounts receivable and treasury indicators, built
on top of ``dashboards_base``.

Invoicing and collection
=========================

- **Total receivable**: the full open (uncollected) balance of customer
  invoices, re-expressed in the currency selected at the top of the
  dashboard using **today's** exchange rate — an invoice in any currency
  contributes its already-booked company-currency residual, converted
  once to the selected currency, rather than being filtered out when it
  doesn't match the selected currency.
- **Rejected checks**: amount of third-party checks currently sitting in
  a journal configured as "rejected". Odoo has no formal rejected state
  for checks — see *Configuration* below.
- **Collection turnover** (*Rotación de cobranza*): Net credit sales ÷
  Average accounts receivable, over a period selected independently of
  the dashboard's date range (current fiscal year, previous fiscal year,
  or trailing 12 months). "Net credit sales" is net of tax and of credit
  notes. "Average accounts receivable" is the accounts-receivable
  balance at the start and at the end of that period, averaged.
- **Collection/Payment ratio**: amount collected from customers ÷ amount
  paid to suppliers, over the dashboard's selected date range.
- **Due soon, by Follow-up level**: not-yet-due receivables, grouped by
  the real Follow-up level (``account_followup.followup.line``) already
  assigned to them (only lines with a level assigned show up here).
- **Overdue, by age**: overdue, uncollected receivables bucketed into
  0-30 / 31-60 / 61-90 / +90 days overdue.
- **Top overdue customers**: the 10 customers with the highest overdue
  balance. Drill-down reuses the standard Partner Ledger report
  (``account_reports``); note it opens **unfiltered** — this report's
  partner filter is a purely interactive client-side widget in this Odoo
  version, it cannot be pre-seeded from the action that opens it.

"Total receivable", "Rejected checks", "Due soon", "Overdue by age" and
"Top overdue customers" can be split by currency using the selector at
the top of the dashboard, built from every currency active on this
database — not hardcoded to any specific pair.

Every invoicing/collection indicator above is restricted to the journals
selected as "Sales voucher journals" in *Configuration* (see below).

Treasury
========

- **Bank balances**: one KPI card per journal selected in
  *Dashboards > Configuration > Collection* as a "bank balance" journal,
  showing that journal's default account current balance.
- **Fixed fund**: same as above, for the single journal configured as
  the "Fixed fund" journal.
- **Cash/transfer collections**: customer payments of the period through
  the journals selected as "cash/transfer collection" journals.
- **Third-party checks in portfolio**: checks received from customers,
  not yet deposited or transferred out, grouped by currency (with an
  overdue/upcoming split by cash-in date).

Reconciliation
===============

- **Pending reconciliation**: count and amount of journal items pending
  reconciliation, reusing the exact same domain as the standard
  "Journal Items to reconcile" screen (``account_accountant``).

Multi-currency
===============

- **Pending exchange difference**: invoices with an open foreign-currency
  balance whose value at today's exchange rate no longer matches the
  amount already booked in company currency — the same criterion Odoo's
  own "Multicurrency Revaluation" report uses.

By salesperson
===============

- **Collection by salesperson**: customer payments of the period,
  attributed to the salesperson (``invoice_user_id``) of the first
  invoice each payment reconciles. When a single payment settles
  invoices from more than one salesperson, the whole payment is
  attributed to the first one — this is a known simplification, not a
  proportional split.
