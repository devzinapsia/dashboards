Executive dashboard for accounts receivable and treasury indicators, built
on top of ``dashboards_base``.

**Status: work in progress.** This module is being built in phases (simple
indicators first, delicate ones last); this description will be extended
as new indicators are added. Currently implemented:

Invoicing and collection
=========================

- **Invoiced vs. Collected**: for invoices dated within the selected
  period, the total invoiced amount (net of credit notes) vs. the amount
  already collected from those same invoices (regardless of when they
  were paid), and the resulting collection rate.
- **Collected late**: customer payments of the period that were collected
  after the due date of the invoice(s) they settle.
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

All of the above (except "Collected late", for now) can be split by
currency using the selector at the top of the dashboard, built from every
currency active on this database — not hardcoded to any specific pair.

Treasury
========

- **Bank balances**: one KPI card per journal selected in
  *Dashboards > Configuration > Collection* as a "bank balance" journal,
  showing that journal's default account current balance.
- **Fixed fund**: same as above, for the single journal configured as
  the "Fixed fund" journal.
- **Cash/transfer collections**: customer payments of the period through
  the journals selected as "cash/transfer collection" journals.

Reconciliation
===============

- **Pending reconciliation**: count and amount of journal items pending
  reconciliation, reusing the exact same domain as the standard
  "Journal Items to reconcile" screen (``account_accountant``).

By salesperson
===============

- **Collection by salesperson**: customer payments of the period,
  attributed to the salesperson (``invoice_user_id``) of the first
  invoice each payment reconciles. When a single payment settles
  invoices from more than one salesperson, the whole payment is
  attributed to the first one — this is a known simplification, not a
  proportional split.

Not yet implemented: third-party checks in portfolio, and pending
exchange-rate differences (the two most delicate indicators, saved for
last).
