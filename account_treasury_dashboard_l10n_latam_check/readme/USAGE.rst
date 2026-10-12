The **Checks** section shows after *Reconciliation* in *Dashboards >
Boards > Treasury*, and the cash projection gets two more rows: *Third-party
checks* and *Own checks*. Click any figure to see its checks.

``scripts/load_demo_data.py`` (not part of the module, never installed
with it) adds check journals and checks to the company created by the
treasury dashboard's own demo script. Run it on a test database only,
after that one::

    ./odoo-bin shell -c <config> -d <test_db> --addons-path=<...> \
        < account_treasury_dashboard_l10n_latam_check/scripts/load_demo_data.py
