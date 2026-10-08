from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """The first section is now called "Income" ("Ingresos") instead of
    "Sales" ("Ventas"): rename existing structures' section where it still
    has the old default name."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    env["account.pl.structure.line"]._rename_default_income_sections()
