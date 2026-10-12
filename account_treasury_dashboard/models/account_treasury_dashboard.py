import logging

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.tools.translate import LazyTranslate

from .treasury_currency import TreasuryRates

_lt = LazyTranslate(__name__)
_logger = logging.getLogger(__name__)

USER_GROUP = "account_treasury_dashboard.group_treasury_dashboard_user"


class AccountTreasuryDashboard(models.AbstractModel):
    """Computation engine of the treasury dashboard.

    The dashboard is a list of sections, each one provided by a method of
    this model and loaded by its own RPC call, so that a section that fails
    (e.g. a missing exchange rate) doesn't break the others. A section only
    returns generic blocks (see treasury_blocks), which the frontend renders
    without knowing the section: another module adds a section by extending
    _get_section_providers() and defining its _section_<id>() and
    _drilldown_<id>() methods, without any JavaScript.

    Journal items are read with sudo(), since a dashboard user doesn't need
    accounting rights, so every public method checks the group membership
    itself and only ever reads the current company (one of the user's
    allowed companies). Amounts are kept unrounded: rounding only happens
    when the frontend formats them.
    """

    _name = "account.treasury.dashboard"
    _description = "Treasury dashboard"
    _inherit = "dashboards.drilldown.mixin"

    # -------------------------------------------------------------------------
    # Access and context
    # -------------------------------------------------------------------------

    def _check_dashboard_access(self):
        if not self.env.user.has_group(USER_GROUP):
            raise AccessError(self.env._("You are not allowed to see the treasury dashboard."))
        company = self.env.company
        if company.id not in self.env.user._get_company_ids():
            raise AccessError(self.env._("You are not allowed to access company %s.", company.display_name))
        return company

    def _get_config(self, company):
        return self.env["account.treasury.config"].sudo()._get_active_config(company)

    def _prepare_context(self):
        """What every section computation needs: checks the access first."""
        company = self._check_dashboard_access()
        config = self._get_config(company)
        today = fields.Date.context_today(self)
        return {
            "company": company,
            "currency": company.currency_id,
            "config": config,
            # The user's "today", in their own time zone (RPC context's tz).
            "today": today,
            # Foreign currencies valued at the rate of the day (raises, in the
            # section that needs it, when a currency has no rate).
            "rates": TreasuryRates(self.env, company, today),
        }

    def _get_mediums(self, config, kinds=None, available_only=False):
        mediums = config.medium_ids.filtered("active")
        if kinds:
            mediums = mediums.filtered(lambda medium: medium.kind in kinds)
        if available_only:
            mediums = mediums.filtered("in_available_total")
        return mediums

    # -------------------------------------------------------------------------
    # Section registry
    # -------------------------------------------------------------------------

    def _get_section_providers(self):
        """The dashboard's sections, in display order. Extension point.

        Each provider is a dict with:
        - id: used for _section_<id>() (content) and _drilldown_<id>()
          (popup of a clicked figure);
        - title: lazy translated title;
        - sequence: display order;
        - toggle: boolean field of account.treasury.config enabling it;
        - is_configured: name of a method(config) telling whether there is
          something configured for it (a section without configuration is
          not shown).
        """
        return [
            {"id": "cash_position", "title": _lt("Cash position"), "sequence": 10,
             "toggle": "show_cash_position", "is_configured": "_is_cash_position_configured"},
            {"id": "reconciliation", "title": _lt("Reconciliation"), "sequence": 20,
             "toggle": "show_reconciliation", "is_configured": "_is_reconciliation_configured"},
            {"id": "investments", "title": _lt("Investments"), "sequence": 30,
             "toggle": "show_investments", "is_configured": "_is_investments_configured"},
            {"id": "projection", "title": _lt("Cash projection"), "sequence": 40,
             "toggle": "show_projection", "is_configured": "_is_projection_configured"},
            {"id": "movements", "title": _lt("Period movements"), "sequence": 50,
             "toggle": "show_movements", "is_configured": "_is_movements_configured"},
        ]

    def _is_cash_position_configured(self, config):
        return bool(self._get_mediums(config, ("bank", "cash", "petty_cash", "prepaid", "credit_card")))

    def _is_reconciliation_configured(self, config):
        return bool(self._get_mediums(config, ("bank",)))

    def _is_investments_configured(self, config):
        return bool(self._get_mediums(config, ("investment",)))

    def _is_projection_configured(self, config):
        return bool(self._get_mediums(config, ("bank", "cash"), available_only=True))

    def _is_movements_configured(self, config):
        return bool(self._get_mediums(config, available_only=True))

    def _describe_sections(self, config):
        sections = []
        for provider in sorted(self._get_section_providers(), key=lambda provider: provider["sequence"]):
            enabled = bool(config) and bool(config[provider["toggle"]])
            configured = bool(config) and getattr(self, provider["is_configured"])(config)
            sections.append({
                "id": provider["id"],
                "title": str(provider["title"]),
                "enabled": enabled,
                "configured": configured,
                "visible": enabled and configured,
            })
        return sections

    def _get_provider(self, section_id):
        for provider in self._get_section_providers():
            if provider["id"] == section_id:
                return provider
        raise UserError(self.env._("Unknown dashboard section: %s", section_id))

    # -------------------------------------------------------------------------
    # RPC
    # -------------------------------------------------------------------------

    @api.model
    def get_dashboard(self):
        """The dashboard's frame: company, today, and its sections (only the
        visible ones are loaded, each by its own get_section_data call)."""
        ctx = self._prepare_context()
        config = ctx["config"]
        sections = self._describe_sections(config)
        if not config:
            message = self.env._(
                "The treasury dashboard is not configured yet for %s. An administrator configures it in "
                "Dashboards > Configuration > Treasury.", ctx["company"].name,
            )
        elif not any(section["visible"] for section in sections):
            message = self.env._(
                "There is nothing to show yet: configure the banks, cash and other payment means of %s in "
                "Dashboards > Configuration > Treasury.", ctx["company"].name,
            )
        else:
            message = False
        return {
            "company_name": ctx["company"].name,
            "currency_id": ctx["currency"].id,
            "today": fields.Date.to_string(ctx["today"]),
            "has_config": bool(config),
            "sections": sections,
            "message": message,
        }

    @api.model
    def get_section_data(self, section_id):
        """Content of one section: {"alerts": [...], "blocks": [...]}, or
        {"error": message} when it can't be computed. The error stays in
        this section: the others are separate calls."""
        ctx = self._prepare_context()  # access errors are raised, never turned into a section error
        provider = self._get_provider(section_id)
        if not next(section for section in self._describe_sections(ctx["config"])
                    if section["id"] == section_id)["visible"]:
            raise UserError(self.env._("This section is not enabled or not configured."))
        try:
            with self.env.cr.savepoint():
                content = getattr(self, "_section_%s" % provider["id"])(ctx)
        except UserError as error:
            return {"error": error.args[0]}
        except Exception:
            _logger.exception("Treasury dashboard: section %s failed", section_id)
            return {"error": self.env._("This section couldn't be computed. The details were written to the server log.")}
        return {"alerts": content.get("alerts", []), "blocks": content.get("blocks", [])}

    @api.model
    def get_drilldown(self, section_id, key, params=None):
        """Popup content of a clicked figure (see _popup())."""
        ctx = self._prepare_context()
        provider = self._get_provider(section_id)
        return getattr(self, "_drilldown_%s" % provider["id"])(key, params or {}, ctx)

    # -------------------------------------------------------------------------
    # Popups
    # -------------------------------------------------------------------------

    def _popup(self, title, columns, rows, total=None, list_model=None, list_domain=None, list_name=None):
        """A drill-down popup.

        :param list rows: [{"key", "cells": {column: value()}, "record": (model, id) or None,
            "list": (model, domain, name) or None}]: a row opens its record, or
            the list of records behind it (e.g. a month's journal items).
        :param dict total: value() of the total, or None.
        :param str list_model: model of the standard list offered below the
            popup ("View all"), with ``list_domain``; it is only offered when
            the user can read that model, and each row only links to its
            record (or list) under the same condition. Without the right, the
            popup is shown on its own.
        """
        readable = {}

        def can_read(model):
            if model not in readable:
                readable[model] = self.env[model].has_access("read")
            return readable[model]

        popup_rows = []
        for popup_row in rows:
            record = popup_row.get("record")
            row_list = popup_row.get("list")
            popup_rows.append({
                "key": popup_row["key"],
                "cells": popup_row["cells"],
                "record": {"model": record[0], "id": record[1]} if record and can_read(record[0]) else False,
                "action": self._get_drilldown_action(row_list[0], domain=row_list[1], name=str(row_list[2]))
                if row_list and can_read(row_list[0]) else False,
            })
        list_action = False
        if list_model and can_read(list_model):
            list_action = self._get_drilldown_action(list_model, domain=list_domain or [], name=list_name or str(title))
        return {
            "title": str(title),
            "columns": columns,
            "rows": popup_rows,
            "total": total or False,
            "list_action": list_action,
        }
