Adds the checks of ``l10n_latam_check`` to the treasury dashboard
(``account_treasury_dashboard``). It installs automatically when both
modules are installed, and works the same with or without ingadhoc's
``l10n_latam_check_ux`` (which books one journal item per check).

Checks section
==============

By the check's date (payment date of third-party checks, debit date of
own checks), with count and amount in brackets: overdue, today, next 7
days, next 8 to 30 days and later (one constant, ``CHECK_BUCKETS``).

- **Third-party checks in portfolio**: their current journal is one of the
  configured third-party check journals. An alert lists those whose date
  has already passed.
- **Deposited, not credited yet**: moved to a bank by a payment not matched
  with a bank statement yet.
- **Own checks pending debit**: own checks handed and not debited yet
  (``issue_state`` "handed").
- **Rejected checks**: Odoo has no "rejected" state, so a check is rejected
  because it sits in a configured rejected check journal. Shown with an
  alert, never projected.

Every figure opens the list of its checks (number, bank, partner, journal,
date, amount), and the checks themselves for users who can read them.

Cash projection
===============

- Third-party checks in portfolio come in on their payment date (week 1
  when it has passed).
- The banks' outstanding items of check payments are taken out of the
  generic in-transit flows (which put everything in week 1) and projected
  on their checks' dates: own checks pending debit go out, deposited
  checks come in. Each item is split among its checks, in proportion to
  their amounts: Odoo's own deposit makes one item for all the deposited
  checks, due on the deposit date.
- Nothing is counted twice: a check is either in portfolio (in a check
  journal, which can't be a bank or cash payment mean, so never in the
  opening balance), or an outstanding item of the bank (out of the generic
  in-transit flows), or credited (in the opening balance only).

The cash position keeps showing every outstanding item, checks included,
in the banks' *In transit* column: it follows Odoo's bank reconciliation
report.
