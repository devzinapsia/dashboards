This module has no configuration screen of its own — it only defines
patterns that concept modules (e.g. ``account_collection_dashboard``) are
expected to follow.

Per-indicator configuration model
==================================

Some KPIs need the administrator to select journals/accounts before they
can be computed (e.g. "which journal is the petty cash fund", "which bank
journals should show a balance card"). The expected pattern is:

- One ``<concept>.dashboard.config`` model per concept module (e.g.
  ``account.collection.dashboard.config``), used as a *singleton*
  settings record (similar to ``res.config.settings``, but a plain model
  is enough since these dashboards don't need the wizard-style "Apply"
  screen).
- One ``Many2one``/``Many2many`` field per indicator that needs it,
  pointing to ``account.journal`` or ``account.account`` as appropriate
  (e.g. ``fixed_fund_journal_id = fields.Many2one("account.journal", ...)``
  for a "Fixed fund" balance card, or
  ``bank_journal_ids = fields.Many2many("account.journal", ...)`` for a
  list of bank journals to show balance cards for).
- The form view for this model is added under the "Configuration" menu
  created by this module (``dashboards_base.menu_dashboards_config``),
  not under a new top-level menu.
- No abstract mixin is provided for this in ``dashboards_base`` — a single
  concrete model per concept module, following this pattern, is enough
  and avoids a mixin that would add indirection without real reuse (there
  is no shared logic between concept modules here, only a shared shape).

Security groups
================

Concept modules must **not** put a ``category_id`` field directly on their
``res.groups`` records — in Odoo 19, ``res.groups`` no longer has that
field. Instead:

1. Create one ``res.groups.privilege`` record per feature (e.g. "Collection
   Dashboard"), with ``category_id`` set to
   ``dashboards_base.module_category_dashboards``.
2. Create the ``res.groups`` records for that feature with ``privilege_id``
   pointing to that privilege, chaining access levels with
   ``implied_ids`` (lowest level first, e.g. "User", then "Administrator"
   implying "User").

This is exactly the pattern used by core modules such as
``fleet/security/fleet_security.xml``, and it is what makes the groups
show up correctly grouped under "Dashboards" in
*Settings > Users & Companies > Permissions*.
