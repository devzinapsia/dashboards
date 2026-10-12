{
    "name": "Tablero de tesorería - cheques",
    "summary": "Checks section and cash projection contributions of the treasury dashboard "
    "(third-party checks in portfolio and deposited, own checks pending debit)",
    "version": "19.0.1.0.0",
    "category": "Accounting/Accounting",
    "license": "AGPL-3",
    "author": "Zinapsia",
    "website": "https://www.zinapsia.com",
    "depends": [
        "account_treasury_dashboard",
        "l10n_latam_check",
    ],
    "data": [
        "views/account_treasury_config_views.xml",
    ],
    "auto_install": True,
    "application": False,
    "installable": True,
}
