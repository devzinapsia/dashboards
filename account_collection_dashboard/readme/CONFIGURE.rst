Go to *Dashboards > Configuration > Collection* (Administrator access
only) and set:

- **Sales voucher journals**: the journals ("Sales" type) used to source
  customer invoices and their collections — this is the base filter for
  every invoicing/collection indicator on the dashboard, not just one of
  them.
- **Rejected check journals**: Odoo has no formal "rejected" state for
  third-party checks. A check only counts as rejected here by
  convention, because it currently sits in one of the journals selected
  here (e.g. the "Rejected Third Party Checks" journal some
  localizations create automatically). Move a check into one of these
  journals (a mass transfer, or however your process records a
  rejection) to have it show up in the "Rejected checks" KPI.
- **Fixed fund journal**: the single journal representing the company's
  fixed/petty cash fund.
- **Bank balance journals**: the bank journals that should each get a
  balance KPI card on the dashboard.
- **Cash/transfer collection journals**: the journals whose inbound
  customer payments count towards the "Cash/transfer collections" KPI.
- **Third-party check journals**: the journals used to hold third-party
  checks in portfolio (received, not yet deposited or transferred out).

Access to the dashboard itself is controlled by the "Dashboards /
Collection" groups (User, Administrator) under
*Settings > Users & Companies > Permissions*. Only Administrators can
access this configuration screen and its underlying model.
