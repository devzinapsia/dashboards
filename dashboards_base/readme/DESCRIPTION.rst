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
