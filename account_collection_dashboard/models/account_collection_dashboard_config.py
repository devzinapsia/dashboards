from psycopg2 import errors as pgerrors

from odoo import api, fields, models


class AccountCollectionDashboardConfig(models.Model):
    """Singleton settings record for the Collection dashboard.

    Following the pattern documented in dashboards_base's README: one plain
    model per concept dashboard (not res.config.settings, since there is no
    wizard-style "Apply" step needed here), with one field per indicator
    that requires the administrator to pick journals/accounts.
    """

    _name = "account.collection.dashboard.config"
    _description = "Collection Dashboard Configuration"

    company_id = fields.Many2one(
        "res.company", string="Company", required=True, default=lambda self: self.env.company
    )
    sale_journal_ids = fields.Many2many(
        "account.journal",
        "account_collection_dashboard_config_sale_journal_rel",
        "config_id",
        "journal_id",
        string="Sales voucher journals",
        domain="[('type', '=', 'sale'), ('company_id', '=', company_id)]",
        help="Journals used to source customer invoices and their collections"
        " for every indicator on the dashboard.",
    )
    rejected_check_journal_ids = fields.Many2many(
        "account.journal",
        "account_collection_dashboard_config_rejected_check_journal_rel",
        "config_id",
        "journal_id",
        string="Rejected check journals",
        domain="[('company_id', '=', company_id)]",
        help="Odoo has no formal 'rejected' state for third-party checks: a"
        " check counts as rejected here purely by convention, because it"
        " currently sits in one of these journals (e.g. the 'Rejected Third"
        " Party Checks' journal some localizations create).",
    )
    _company_uniq = models.Constraint(
        "unique(company_id)",
        "Only one Collection Dashboard configuration is allowed per company.",
    )

    def _compute_display_name(self):
        # This is a singleton settings record with no natural "name" field;
        # without this override, Odoo falls back to the technical
        # "<model>,<id>" string as the breadcrumb/display label.
        for config in self:
            config.display_name = self.env._("Collection Dashboard Settings")

    @api.model
    def _get_config(self, company=None):
        company = company or self.env.company
        config = self.search([("company_id", "=", company.id)], limit=1)
        if not config:
            # The dashboard's client action fires several RPC calls
            # concurrently, more than one of which may reach here before any
            # config row exists for this company (search() above finding
            # nothing in every one of them). Guard the create() with a
            # savepoint and fall back to a re-search on a unique-constraint
            # race instead of letting the losing request error out.
            try:
                with self.env.cr.savepoint():
                    config = self.create({"company_id": company.id})
            except pgerrors.UniqueViolation:
                config = self.search([("company_id", "=", company.id)], limit=1)
        return config

    @api.model
    def action_open_config(self):
        # This is a singleton per-company record (see _company_uniq above):
        # no "New" button, since creating a second one would just hit the
        # unique constraint, and no "Delete" either. The web client only
        # honors these through the action's context (create/delete as
        # top-level ir.actions.act_window fields are not read by the
        # View component for this), not through act_window's own
        # create/delete fields.
        return self._get_config()._get_records_action(
            name=self.env._("Collection Dashboard Settings"),
            context={**self.env.context, "create": False, "delete": False},
        )
