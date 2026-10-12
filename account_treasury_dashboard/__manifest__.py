{
    "name": "Tablero de tesorería",
    "summary": "Treasury dashboard: cash position, bank reconciliation, investments, cash projection and "
    "period movements, configured per company",
    "version": "19.0.1.0.3",
    "category": "Accounting/Accounting",
    "license": "AGPL-3",
    "author": "Zinapsia",
    "website": "https://www.zinapsia.com",
    "depends": [
        "dashboards_base",
        "account",
    ],
    "data": [
        "security/account_treasury_dashboard_security.xml",
        "security/ir.model.access.csv",
        "views/account_treasury_config_views.xml",
        "views/account_treasury_dashboard_menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "account_treasury_dashboard/static/src/**/*",
        ],
    },
    "auto_install": False,
    "application": False,
    "installable": True,
}
