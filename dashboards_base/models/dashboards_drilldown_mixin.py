from odoo import models
from odoo.tools.safe_eval import safe_eval


class DashboardsDrilldownMixin(models.AbstractModel):
    """Reusable helper to build drill-down window actions for dashboard KPIs.

    Any dashboard backend model can inherit this mixin to turn a
    (res_model, domain) pair into a ready-to-use ir.actions.act_window
    dict, instead of duplicating the same action-building boilerplate in
    every concept module.
    """

    _name = "dashboards.drilldown.mixin"
    _description = "Dashboards Drilldown Mixin"

    def _get_drilldown_action(
        self, res_model, domain=None, view_type=None, name=None, context=None, view_id=None,
        create=False, delete=False,
    ):
        """Build an ir.actions.act_window dict opening ``res_model`` filtered by ``domain``.

        :param str res_model: technical name of the model to open.
        :param list domain: search domain to apply.
        :param str view_type: primary view to open ("list", "form", "kanban", ...).
            Defaults to "list". A "form" view is appended as fallback unless
            it is already the primary one.
        :param str name: action title.
        :param dict context: extra context passed to the target action.
        :param int view_id: id of a specific view to use for the primary
            view_type, instead of letting Odoo resolve the model's default
            one. The fallback "form" view is unaffected.
        :param bool create: whether the "New" button is available. Defaults
            to False - a drill-down is for inspecting the records behind a
            KPI, not for creating unrelated new ones.
        :param bool delete: whether records can be deleted from this view.
            Defaults to False, for the same reason.
        :return: an action dict, meant to be returned as-is to the client
            and passed to the "action" service's doAction().
        :rtype: dict
        """
        view_type = view_type or "list"
        view_modes = [view_type] if view_type == "form" else [view_type, "form"]
        # The web client only honors create/delete through the action's
        # context (not through act_window's own create/delete fields, which
        # the View component does not read for this).
        action_context = {**(context or {})}
        if not create:
            action_context["create"] = False
        if not delete:
            action_context["delete"] = False
        return {
            "type": "ir.actions.act_window",
            "name": name or self.env["ir.model"]._get(res_model).name,
            "res_model": res_model,
            "domain": domain or [],
            "views": [((view_id or False) if mode == view_type else False, mode) for mode in view_modes],
            "target": "current",
            "context": action_context,
        }

    def _get_native_drilldown_action(self, xml_id, domain=None, context=None):
        """Reuse an existing Odoo action (report, wizard, ...) as a drill-down,
        instead of building an ad-hoc one, when a standard action for the
        target data already exists.

        :param str xml_id: fully qualified xmlid of the action to reuse
            (e.g. "account_reports.action_account_report_partner_ledger").
        :param list domain: if given, overrides the action's own domain.
        :param dict context: merged into (and taking priority over) the
            action's own context.
        :return: an action dict, meant to be returned as-is to the client
            and passed to the "action" service's doAction().
        :rtype: dict
        """
        action = self.env["ir.actions.actions"]._for_xml_id(xml_id)
        if domain is not None:
            action["domain"] = domain
        if context:
            existing_context = action.get("context") or {}
            if isinstance(existing_context, str):
                existing_context = safe_eval(existing_context)
            action["context"] = {**existing_context, **context}
        return action
