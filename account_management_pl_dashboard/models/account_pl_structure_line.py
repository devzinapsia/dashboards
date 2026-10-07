from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

from .account_pl_structure import PL_ACCOUNT_TYPES, SECTIONS

SECTION_ORDER = {section: index for index, (section, _label) in enumerate(SECTIONS, start=1)}


class AccountPlStructureLine(models.Model):
    """A row of a management P&L structure.

    The three root lines (one per section) are created with the structure and
    can't be removed or retyped. Below them, a line with sub-lines is a
    *group* (its amount is the sum of its sub-lines) and a line without
    sub-lines is a *leaf*, the only kind of line that gets accounts assigned
    (income accounts for Sales, expense accounts for costs).
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

    account_ids = fields.Many2many(
        "account.account",
        "account_pl_structure_line_account_rel",
        "line_id",
        "account_id",
        string="Accounts",
        domain="[('account_type', 'in', %s), ('company_ids', 'parent_of', company_id)]" % (PL_ACCOUNT_TYPES,),
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

    @api.depends("is_root", "child_ids", "account_ids")
    def _compute_assignment_status(self):
        for line in self:
            is_empty_leaf = not line.is_root and not line.child_ids and not line.account_ids
            line.assignment_status = self.env._("Without accounts") if is_empty_leaf else False

    def _has_assignments(self):
        self.ensure_one()
        return bool(self.account_ids)

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
                    "Line %(parent)s has accounts assigned, so it can't have sub-lines. Remove its accounts "
                    "first, or add %(line)s somewhere else.",
                    parent=line.parent_id.complete_name,
                    line=line.name,
                ))

    @api.constrains("account_ids", "section", "child_ids")
    def _check_assignments(self):
        for line in self:
            if not line._has_assignments():
                continue
            if line.is_root:
                raise ValidationError(self.env._(
                    "Section %s can't have accounts of its own: add a line below it.", line.name
                ))
            if line.child_ids:
                raise ValidationError(self.env._(
                    "Line %s is a group (it has sub-lines), so it can't have accounts assigned. Assign them "
                    "to its sub-lines instead.",
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
        self._check_unique_assignments()

    def _check_unique_assignments(self):
        """An account can only be counted once per structure, whatever the
        section: in two lines, its amount would be counted twice."""
        for structure in self.structure_id:
            account_owner = {}
            for line in structure.line_ids:
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
                "Line %s has accounts assigned, so it can't have sub-lines. Remove its accounts first.",
                self.complete_name,
            ))
        last_sequence = max(self.child_ids.mapped("sequence"), default=0)
        self.create({
            "structure_id": self.structure_id.id,
            "parent_id": self.id,
            "name": self.env._("New line"),
            "sequence": last_sequence + 10,
        })
