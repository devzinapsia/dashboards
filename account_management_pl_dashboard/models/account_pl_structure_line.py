from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

from .account_pl_structure import PL_ACCOUNT_TYPES, SECTIONS

SECTION_ORDER = {section: index for index, (section, _label) in enumerate(SECTIONS, start=1)}
COST_SECTIONS = ("direct_cost", "indirect_cost")


class AccountPlStructureLine(models.Model):
    """A row of a management P&L structure.

    The three root lines (one per section) are created with the structure and
    can't be removed or retyped. Below them, a line with sub-lines is a
    *group* (its amount is the sum of its sub-lines) and a line without
    sub-lines is a *leaf*, the only kind of line that gets accounts (cost
    sections) or customers / analytic accounts (Sales) assigned.
    """

    _name = "account.pl.structure.line"
    _description = "Management P&L structure line"
    _order = "structure_id, sort_key, id"
    _check_company_auto = True

    structure_id = fields.Many2one(
        "account.pl.structure", string="Structure", required=True, ondelete="cascade", index=True,
    )
    company_id = fields.Many2one(related="structure_id.company_id", string="Company", store=True, index=True)
    parent_id = fields.Many2one(
        "account.pl.structure.line",
        string="Parent line",
        ondelete="cascade",
        index=True,
        domain="[('structure_id', '=', structure_id), ('id', '!=', id)]",
    )
    child_ids = fields.One2many("account.pl.structure.line", "parent_id", string="Sub-lines")
    sequence = fields.Integer(string="Sequence", default=10)
    name = fields.Char(string="Name", required=True)
    is_root = fields.Boolean(string="Is a section", readonly=True, copy=False)
    root_section = fields.Selection(SECTIONS, string="Root section", readonly=True, copy=False)
    section = fields.Selection(
        SECTIONS, string="Section", compute="_compute_section", store=True, recursive=True, index=True,
    )
    level = fields.Integer(string="Level", compute="_compute_hierarchy", store=True, recursive=True)
    sort_key = fields.Char(string="Sort key", compute="_compute_hierarchy", store=True, recursive=True)
    complete_name = fields.Char(string="Full name", compute="_compute_complete_name", recursive=True)
    is_group = fields.Boolean(string="Is a group", compute="_compute_is_group")
    sales_dimension = fields.Selection(related="structure_id.sales_dimension", string="Sales dimension")
    analytic_plan_id = fields.Many2one(
        "account.analytic.plan", string="Analytic plan", compute="_compute_analytic_plan_id",
    )

    account_ids = fields.Many2many(
        "account.account",
        "account_pl_structure_line_account_rel",
        "line_id",
        "account_id",
        string="Accounts",
        domain="[('account_type', 'in', %s), ('company_ids', 'parent_of', company_id)]" % (PL_ACCOUNT_TYPES,),
    )
    partner_ids = fields.Many2many(
        "res.partner",
        "account_pl_structure_line_partner_rel",
        "line_id",
        "partner_id",
        string="Customers",
        domain="[('parent_id', '=', False)]",
    )
    analytic_account_ids = fields.Many2many(
        "account.analytic.account",
        "account_pl_structure_line_analytic_rel",
        "line_id",
        "analytic_account_id",
        string="Analytic accounts",
        domain="[('root_plan_id', '=', analytic_plan_id)]",
    )
    assignment_status = fields.Char(string="Assignment status", compute="_compute_assignment_status")

    # -------------------------------------------------------------------------
    # Computes
    # -------------------------------------------------------------------------

    @api.depends("root_section", "parent_id.section")
    def _compute_section(self):
        for line in self:
            line.section = line.parent_id.section if line.parent_id else line.root_section

    @api.depends("sequence", "section", "parent_id.level", "parent_id.sort_key")
    def _compute_hierarchy(self):
        for line in self:
            if line.parent_id:
                line.level = line.parent_id.level + 1
                line.sort_key = "%s/%06d.%09d" % (
                    line.parent_id.sort_key or "", max(line.sequence, 0), line._origin.id or 0,
                )
            else:
                line.level = 0
                line.sort_key = "%d" % SECTION_ORDER.get(line.section, 0)

    @api.depends("name", "parent_id.complete_name")
    def _compute_complete_name(self):
        for line in self:
            if line.parent_id:
                line.complete_name = "%s / %s" % (line.parent_id.complete_name, line.name)
            else:
                line.complete_name = line.name

    @api.depends("child_ids")
    def _compute_is_group(self):
        for line in self:
            line.is_group = bool(line.child_ids)

    @api.depends("structure_id.analytic_mode", "structure_id.analytic_plan_id")
    def _compute_analytic_plan_id(self):
        for line in self:
            line.analytic_plan_id = line.structure_id._get_analytic_plan() if line.structure_id else False

    @api.depends("is_root", "child_ids", "section", "sales_dimension",
                 "account_ids", "partner_ids", "analytic_account_ids")
    def _compute_assignment_status(self):
        for line in self:
            status = False
            if not line.is_root and not line.child_ids:
                if line.section == "income":
                    if line.sales_dimension == "analytic" and not line.analytic_account_ids:
                        status = self.env._("Without analytic accounts")
                    elif line.sales_dimension != "analytic" and not line.partner_ids:
                        status = self.env._("Without customers")
                elif not line.account_ids:
                    status = self.env._("Without accounts")
            line.assignment_status = status

    def _has_assignments(self):
        self.ensure_one()
        return bool(self.account_ids or self.partner_ids or self.analytic_account_ids)

    # -------------------------------------------------------------------------
    # Constraints
    # -------------------------------------------------------------------------

    @api.constrains("parent_id", "structure_id", "is_root")
    def _check_hierarchy(self):
        if self._has_cycle():
            raise ValidationError(self.env._("A line can't be its own ancestor."))
        for line in self:
            if line.is_root and line.parent_id:
                raise ValidationError(self.env._(
                    "Section %s can't be placed under another line.", line.name
                ))
            if not line.is_root and not line.parent_id:
                raise ValidationError(self.env._(
                    "Line %s must belong to a section or group.", line.name
                ))
            if line.parent_id and line.parent_id.structure_id != line.structure_id:
                raise ValidationError(self.env._(
                    "Line %s and its parent line must belong to the same structure.", line.name
                ))
            if line.parent_id and line.parent_id._has_assignments():
                raise ValidationError(self.env._(
                    "Line %(parent)s has accounts, customers or analytic accounts assigned, so it can't "
                    "have sub-lines. Remove its assignments first, or add %(line)s somewhere else.",
                    parent=line.parent_id.complete_name,
                    line=line.name,
                ))

    @api.constrains("account_ids", "partner_ids", "analytic_account_ids", "section", "child_ids")
    def _check_assignments(self):
        for line in self:
            if not line._has_assignments():
                continue
            if line.is_root:
                raise ValidationError(self.env._(
                    "Section %s can't have assignments of its own: add a line below it.", line.name
                ))
            if line.child_ids:
                raise ValidationError(self.env._(
                    "Line %s is a group (it has sub-lines), so it can't have accounts, customers or "
                    "analytic accounts assigned. Assign them to its sub-lines instead.",
                    line.complete_name,
                ))
            if line.section == "income" and line.account_ids:
                raise ValidationError(self.env._(
                    "Line %s belongs to Sales: assign customers or analytic accounts to it, not accounts. "
                    "Sales accounts are set on the structure.",
                    line.complete_name,
                ))
            if line.section in COST_SECTIONS and (line.partner_ids or line.analytic_account_ids):
                raise ValidationError(self.env._(
                    "Line %s is a cost line: assign accounts to it, not customers or analytic accounts.",
                    line.complete_name,
                ))
            for account in line.account_ids:
                if account.account_type not in PL_ACCOUNT_TYPES:
                    raise ValidationError(self.env._(
                        "Account %(account)s (line %(line)s) is not an income or expense account.",
                        account=account.display_name,
                        line=line.complete_name,
                    ))
            line.structure_id._check_accounts_company(line.account_ids)
            allowed_companies = line.company_id.parent_ids
            for partner in line.partner_ids:
                if partner.commercial_partner_id != partner:
                    raise ValidationError(self.env._(
                        "%(partner)s (line %(line)s) is a contact of %(company)s: assign the company instead, "
                        "its contacts are added up automatically.",
                        partner=partner.display_name,
                        line=line.complete_name,
                        company=partner.commercial_partner_id.display_name,
                    ))
                if partner.company_id and partner.company_id not in allowed_companies:
                    raise ValidationError(self.env._(
                        "Customer %(partner)s (line %(line)s) belongs to another company.",
                        partner=partner.display_name,
                        line=line.complete_name,
                    ))
            for analytic in line.analytic_account_ids:
                if analytic.company_id and analytic.company_id not in allowed_companies:
                    raise ValidationError(self.env._(
                        "Analytic account %(analytic)s (line %(line)s) belongs to another company.",
                        analytic=analytic.display_name,
                        line=line.complete_name,
                    ))
        self._check_analytic_accounts()
        self._check_unique_assignments()

    def _check_analytic_accounts(self):
        """Analytic accounts must belong to the structure's analytic plan: with
        several plans, the same journal item is split at 100% on each plan, so
        mixing plans would count it more than once."""
        for line in self.filtered("analytic_account_ids"):
            plan = line.structure_id._get_analytic_plan()
            if not plan:
                # Analytic usage turned off: assignments are kept but unused.
                continue
            wrong = line.analytic_account_ids.filtered(lambda a: a.root_plan_id != plan)
            if wrong:
                raise ValidationError(self.env._(
                    "Analytic account %(analytic)s (line %(line)s) doesn't belong to the analytic plan "
                    "%(plan)s used by the structure.",
                    analytic=wrong[0].display_name,
                    line=line.complete_name,
                    plan=plan.display_name,
                ))

    def _check_unique_assignments(self):
        """An account, customer or analytic account can only be counted once
        per structure (both cost sections together), and a Sales account
        can't be reused by a cost leaf."""
        for structure in self.structure_id:
            all_lines = structure.line_ids
            account_owner, partner_owner, analytic_owner = {}, {}, {}
            for line in all_lines:
                for account in line.account_ids:
                    if account in account_owner:
                        raise ValidationError(self.env._(
                            "Account %(account)s is already used in line %(other)s; it can't also be in line "
                            "%(line)s (it would be counted twice).",
                            account=account.display_name,
                            other=account_owner[account].complete_name,
                            line=line.complete_name,
                        ))
                    account_owner[account] = line
                for partner in line.partner_ids:
                    if partner in partner_owner:
                        raise ValidationError(self.env._(
                            "Customer %(partner)s is already used in line %(other)s; it can't also be in line "
                            "%(line)s.",
                            partner=partner.display_name,
                            other=partner_owner[partner].complete_name,
                            line=line.complete_name,
                        ))
                    partner_owner[partner] = line
                for analytic in line.analytic_account_ids:
                    if analytic in analytic_owner:
                        raise ValidationError(self.env._(
                            "Analytic account %(analytic)s is already used in line %(other)s; it can't also "
                            "be in line %(line)s.",
                            analytic=analytic.display_name,
                            other=analytic_owner[analytic].complete_name,
                            line=line.complete_name,
                        ))
                    analytic_owner[analytic] = line
            if not account_owner:
                continue
            sales_accounts = structure._get_sales_accounts()
            for account, line in account_owner.items():
                if account in sales_accounts:
                    raise ValidationError(self.env._(
                        "Account %(account)s is a Sales account of the structure; it can't also be in line "
                        "%(line)s (it would be counted twice).",
                        account=account.display_name,
                        line=line.complete_name,
                    ))

    # -------------------------------------------------------------------------
    # CRUD
    # -------------------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        allow_root = self.env.context.get("pl_allow_root_create")
        for vals in vals_list:
            vals["is_root"] = bool(allow_root)
            if not allow_root:
                vals.pop("root_section", None)
            elif "section" in vals:
                vals["root_section"] = vals.pop("section")
        return super().create(vals_list)

    def write(self, vals):
        if self.filtered("is_root") and {"parent_id", "structure_id", "root_section", "is_root"} & set(vals):
            raise UserError(self.env._("The section lines can't be moved or retyped."))
        if "structure_id" in vals and any(line.structure_id.id != vals["structure_id"] for line in self):
            raise UserError(self.env._("A line can't be moved to another structure."))
        if "is_root" in vals or "root_section" in vals:
            raise UserError(self.env._("The section lines can't be moved or retyped."))
        return super().write(vals)

    @api.ondelete(at_uninstall=False)
    def _unlink_except_section(self):
        if self.filtered("is_root"):
            raise UserError(self.env._("The section lines (Sales, Direct costs, Indirect costs) can't be deleted."))

    def action_add_child(self):
        self.ensure_one()
        if self._has_assignments():
            raise UserError(self.env._(
                "Line %s has accounts, customers or analytic accounts assigned, so it can't have sub-lines. "
                "Remove its assignments first.",
                self.complete_name,
            ))
        last_sequence = max(self.child_ids.mapped("sequence"), default=0)
        self.create({
            "structure_id": self.structure_id.id,
            "parent_id": self.id,
            "name": self.env._("New line"),
            "sequence": last_sequence + 10,
        })
