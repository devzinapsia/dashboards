Open *Dashboards > Boards > Treasury*. It works on the current company:
switch company in the top bar to see another one.

- Each section loads on its own: if one can't be computed (e.g. a missing
  exchange rate), it shows the reason and a *Retry* button, and the others
  keep working.
- Sections can be collapsed (*Expand all* / *Collapse all*); they stay as
  left when coming back from a list.
- Click any figure with a detail: a popup lists what makes it up (journal
  entries, payments, statement lines, flows of a projection week). The sum
  of a popup is the figure clicked. A row opens its record (or, in the
  popups by month, that month's journal items) and *View all* the standard
  list behind it, when the user can read them.
- Amounts in red are negative; a warning sign marks a figure to look at
  (difference with the statement, old statement, negative projected
  balance, card over its limit or close to its due date).

Demo data
=========

``scripts/load_demo_data.py`` (not part of the module, never installed
with it) creates a company "Treasury dashboard demo" with banks, cash, a
petty cash fund, a prepaid card, a credit card, a dollar investment,
statements, payments in transit, invoices and bills, commitments and
internal transfers. Run it on a test database only::

    ./odoo-bin shell -c <config> -d <test_db> --addons-path=<...> \
        < account_treasury_dashboard/scripts/load_demo_data.py

For developers
==============

A section is a provider: extend ``_get_section_providers()`` of
``account.treasury.dashboard`` and define ``_section_<id>()`` (generic
blocks, see ``models/treasury_blocks.py``) and ``_drilldown_<id>()``; no
JavaScript needed. The cash projection takes more flows from
``_projection_flow_providers()`` / ``_projection_categories()``, and
``_in_transit_exclusion_domain()`` takes journal items out of the generic
in-transit flows when another module projects them on their own date
(e.g. deferred checks).
