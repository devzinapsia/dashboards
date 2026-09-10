{
    "name": "Dashboards",
    "summary": "Base app and shared infrastructure for executive dashboards",
    "version": "19.0.1.0.0",
    "category": "Productivity",
    "license": "AGPL-3",
    "author": "Zinapsia",
    "website": "https://www.zinapsia.com",
    "depends": [
        "base",
        "web",
    ],
    "data": [
        "security/dashboards_base_security.xml",
        "views/dashboards_menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "dashboards_base/static/src/js/drilldown.js",
            "dashboards_base/static/src/js/dashboards_theme.js",
            "dashboards_base/static/src/components/kpi_card/kpi_card.js",
            "dashboards_base/static/src/components/kpi_card/kpi_card.xml",
            "dashboards_base/static/src/components/kpi_card/kpi_card.scss",
            "dashboards_base/static/src/components/dashboard_chart/dashboard_chart.js",
            "dashboards_base/static/src/components/dashboard_chart/dashboard_chart.xml",
            "dashboards_base/static/src/components/dashboard_chart/dashboard_chart.scss",
        ],
    },
    "auto_install": True,
    "application": True,
    "installable": True,
}
