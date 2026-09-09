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
