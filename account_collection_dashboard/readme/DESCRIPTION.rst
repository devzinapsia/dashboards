Executive dashboard for accounts receivable indicators, built
on top of ``dashboards_base``.

Invoicing and collection
=========================

- **Total receivable**: the full open (uncollected) balance of customer
  invoices, re-expressed in the currency selected at the top of the
  dashboard using **today's** exchange rate — an invoice in any currency
  contributes its already-booked company-currency residual, converted
  once to the selected currency, rather than being filtered out when it
  doesn't match the selected currency. Drill-down opens the list of
  those open invoices (Total / Amount due columns), grouped by due date
  (month) and clickable through to each invoice.
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
- **Customers with debt**: count of distinct customers with at least one
  open receivable invoice (a customer with several outstanding invoices
  counts once). Drill-down opens the list of those open invoices (Total /
  Amount due columns), clickable through to each invoice.
- **Not yet due**: total amount of receivables not yet due, regardless of
  whether a Follow-up level has been assigned to them — a broader total
  than "Due soon, by Follow-up level" above, which only covers lines that
  already have one. Drill-down opens the matching sales invoices.
- **Due today**: amount of receivables due exactly today. Drill-down
  opens the matching sales invoices.
- **Due in 7 days**: amount of receivables due within the next 7 days,
  today included (so it overlaps with "Due today" by design). Drill-down
  opens the matching sales invoices.

"Total receivable", "Rejected checks", "Due soon", "Customers with
debt", "Not yet due", "Due today" and "Due in 7 days" can be split by
currency using the selector at the top of the dashboard, built from
every currency active on this database — not hardcoded to any specific
pair.

Every invoicing/collection indicator above is restricted to the journals
selected as "Sales voucher journals" in *Configuration* (see below).

By salesperson
===============

- **Collection by salesperson**: customer payments of the period,
  attributed to the salesperson (``invoice_user_id``) of the first
  invoice each payment reconciles. When a single payment settles
  invoices from more than one salesperson, the whole payment is
  attributed to the first one — this is a known simplification, not a
  proportional split.

Charts
======

- **Top 10 - Slowest paying customers**: the 10 customers who took the
  longest, on average, to fully settle an invoice (settlement date minus
  invoice date), averaged over every fully-paid invoice issued within
  the period selected by the same selector used for "Collection
  turnover" (current fiscal year / previous fiscal year / last 12
  months). "Settlement date" is the latest reconciliation date among
  every entry that cleared the invoice, whatever the counterpart
  (payment, credit note, or otherwise).
- **Collection projection**: the open receivable balance bucketed by
  days left until due (0-15 / 16-30 / 31-60 / 61-90 / +90 days),
  already-overdue debt folded into the first bucket. Each bar shows its
  share of the total balance as a percentage.
