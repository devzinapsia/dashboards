==========
Dashboards
==========

This module creates the "Dashboards" app and the shared infrastructure that
every dashboard concept module (Collection, Invoicing, Purchases, ...) is
expected to build on. It has **no business indicators of its own** — it is
pure plumbing:

- The "Dashboards" root app menu, with two empty submenus ready for concept
  modules to hang their own entries on:

  - **Boards**: where each concept module adds its dashboard client action.
  - **Configuration**: where each concept module adds its own settings.

- A "Dashboards" ``ir.module.category``, so that every concept module's
  access groups show up neatly grouped together in
  *Settings > Users & Companies > Permissions*.

- Reusable OWL components under ``static/src/components/``:

  - ``DashboardsKpiCard``: a generic KPI tile (title, main value, optional
    secondary value, optional click handler for drill-down, and a default
    slot for extra content).
  - ``DashboardsChart``: a thin Chart.js wrapper (loads the
    ``web.chartjs_lib`` asset bundle and (re)renders a canvas from a
    Chart.js ``type``/``data``/``options`` config).

  Both only use Bootstrap's semantic classes and ``--bs-*`` CSS variables,
  so they automatically follow the light/dark theme without any
  hardcoded colors.

- A drill-down helper, in both languages used by a dashboard:

  - JS: ``openDashboardDrilldown(env, params)`` in
    ``static/src/js/drilldown.js``, calling the "action" service.
  - Python: the ``dashboards.drilldown.mixin`` abstract model, with a
    ``_get_drilldown_action()`` method any backend dashboard model can
    inherit to build the same kind of window action dict server-side.

**Table of contents**

.. contents::
   :local:

Configuration
=============

This module has no configuration screen of its own — it only defines
patterns that concept modules (e.g. ``account_collection_dashboard``) are
expected to follow.

Per-indicator configuration model
----------------------------------

Some KPIs need the administrator to select journals/accounts before they
can be computed (e.g. "which journal is the petty cash fund", "which bank
journals should show a balance card"). The expected pattern is:

- One ``<concept>.dashboard.config`` model per concept module (e.g.
  ``account.collection.dashboard.config``), used as a *singleton*
  settings record (similar to ``res.config.settings``, but a plain model
  is enough since these dashboards don't need the wizard-style "Apply"
  screen).
- One ``Many2one``/``Many2many`` field per indicator that needs it,
  pointing to ``account.journal`` or ``account.account`` as appropriate
  (e.g. ``fixed_fund_journal_id = fields.Many2one("account.journal", ...)``
  for a "Fixed fund" balance card, or
  ``bank_journal_ids = fields.Many2many("account.journal", ...)`` for a
  list of bank journals to show balance cards for).
- The form view for this model is added under the "Configuration" menu
  created by this module (``dashboards_base.menu_dashboards_config``),
  not under a new top-level menu.
- No abstract mixin is provided for this in ``dashboards_base`` — a single
  concrete model per concept module, following this pattern, is enough
  and avoids a mixin that would add indirection without real reuse (there
  is no shared logic between concept modules here, only a shared shape).

Security groups
----------------

Concept modules must **not** put a ``category_id`` field directly on their
``res.groups`` records — in Odoo 19, ``res.groups`` no longer has that
field. Instead:

1. Create one ``res.groups.privilege`` record per feature (e.g. "Collection
   Dashboard"), with ``category_id`` set to
   ``dashboards_base.module_category_dashboards``.
2. Create the ``res.groups`` records for that feature with ``privilege_id``
   pointing to that privilege, chaining access levels with
   ``implied_ids`` (lowest level first, e.g. "User", then "Administrator"
   implying "User").

This is exactly the pattern used by core modules such as
``fleet/security/fleet_security.xml``, and it is what makes the groups
show up correctly grouped under "Dashboards" in
*Settings > Users & Companies > Permissions*.

Usage
=====

This module has no visible dashboard by itself — install a concept module
such as ``account_collection_dashboard`` to see an actual dashboard under
*Dashboards > Boards*.

For developers building a new concept module on top of this one:

- Add your dashboard's client action menu item as a child of
  ``dashboards_base.menu_dashboards_boards``.
- Add your settings menu item as a child of
  ``dashboards_base.menu_dashboards_config``.
- Reuse the ``dashboards_base.KpiCard`` and ``dashboards_base.DashboardChart``
  OWL components from ``@dashboards_base/components/kpi_card/kpi_card`` and
  ``@dashboards_base/components/dashboard_chart/dashboard_chart`` instead of
  writing new ones.
- Use ``openDashboardDrilldown`` from ``@dashboards_base/js/drilldown`` on
  the client side, and/or inherit ``dashboards.drilldown.mixin`` on the
  server side, to open a filtered window action when a KPI card is
  clicked.

Bug Tracker
===========

Bugs are tracked on `GitHub Issues <https://github.com/devzinapsia/dashboards/issues>`_.
In case of trouble, please check there if your issue has already been
reported, mentioning the ``dashboards_base`` module in the issue title.

Credits
=======

Authors
-------

* Zinapsia
