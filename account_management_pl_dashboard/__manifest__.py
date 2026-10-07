{
    "name": "Estado de resultados de gestión",
    "summary": "Management P&L dashboard with a configurable structure, drill-down, budget comparison "
    "and secondary currency view",
    "version": "19.0.1.0.5",
    "category": "Accounting/Accounting",
    "license": "AGPL-3",
    "author": "Zinapsia",
    "website": "https://www.zinapsia.com",
    "depends": [
        "dashboards_base",
        "account",
        "analytic",
        "account_reports",
    ],
    "data": [
        "security/account_management_pl_dashboard_security.xml",
        "security/ir.model.access.csv",
        "views/account_pl_structure_views.xml",
        "views/account_pl_dashboard_menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "account_management_pl_dashboard/static/src/**/*",
        ],
    },
    "auto_install": False,
    "application": False,
    "installable": True,
}
