===========================
Treasury Dashboard - Checks
===========================

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

Configuration
=============

In *Dashboards > Configuration > Treasury*, tab **Checks**:

- **Third-party check journals**: the journals holding the third-party
  checks in portfolio.
- **Rejected check journals**: the journals where rejected checks are
  moved.

These journals can't be configured as a bank or cash payment mean (their
checks are shown in the Checks section instead), and *Load suggested*
leaves them out. Own checks are taken from the banks configured as payment
means. The *Show checks* option of the *General* tab hides the section.

Usage
=====

The **Checks** section shows after *Reconciliation* in *Dashboards >
Boards > Treasury*, and the cash projection gets two more rows: *Third-party
checks* and *Own checks*. Click any figure to see its checks.

``scripts/load_demo_data.py`` (not part of the module, never installed
with it) adds check journals and checks to the company created by the
treasury dashboard's own demo script. Run it on a test database only,
after that one::

    ./odoo-bin shell -c <config> -d <test_db> --addons-path=<...> \
        < account_treasury_dashboard_l10n_latam_check/scripts/load_demo_data.py

Bug Tracker
===========

Bugs are tracked on `GitHub Issues <https://github.com/devzinapsia/dashboards/issues>`_.
In case of trouble, please check there if your issue has already been
reported, mentioning the ``account_treasury_dashboard_l10n_latam_check`` module in the issue title.

Credits
=======

Authors
-------

* Zinapsia
