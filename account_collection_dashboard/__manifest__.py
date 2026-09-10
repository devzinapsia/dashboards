{
    "name": "Tablero de cobranzas",
    "summary": "Executive dashboard for accounts receivable indicators",
    "version": "19.0.1.0.10",
    "category": "Accounting/Accounting",
    "license": "AGPL-3",
    "author": "Zinapsia",
    "website": "https://www.zinapsia.com",
    "depends": [
        "dashboards_base",
        "account",
        "account_followup",
        "l10n_latam_check",
        "account_reports",
        "account_accountant",
    ],
    "data": [
        "security/account_collection_dashboard_security.xml",
        "security/ir.model.access.csv",
        "views/account_collection_dashboard_config_views.xml",
        "views/account_collection_dashboard_menus.xml",
        "views/account_move_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "account_collection_dashboard/static/src/**/*",
        ],
    },
    "auto_install": True,
    "application": False,
    "installable": True,
}
