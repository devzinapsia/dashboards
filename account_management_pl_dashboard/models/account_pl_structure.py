from odoo import api, fields, models
from odoo.exceptions import ValidationError

# Account types that make up the profit and loss statement.
PL_ACCOUNT_TYPES = (
    "income",
    "income_other",
    "expense",
    "expense_other",
    "expense_depreciation",
    "expense_direct_cost",
)
# Account types considered "Sales" when the structure doesn't list its own
# sales accounts. "income_other" (exchange gains, interests, ...) is left
# out on purpose: it is not a sale, and falls under "Unassigned" unless an
# administrator maps it to a cost leaf explicitly.
DEFAULT_SALES_ACCOUNT_TYPES = ("income",)

# Fixed root sections, in display order.
SECTIONS = [
    ("income", "Sales"),
    ("direct_cost", "Direct costs"),
    ("indirect_cost", "Indirect costs"),
]


class AccountPlStructure(models.Model):
    _name = "account.pl.structure"
    _description = "Management P&L structure"
    _order = "company_id, name, id"
    _check_company_auto = True

    name = fields.Char(string="Name", required=True)
    company_id = fields.Many2one(
        "res.company", string="Company", required=True, default=lambda self: self.env.company, index=True,
    )
    company_currency_id = fields.Many2one(related="company_id.currency_id", string="Company currency")
    active = fields.Boolean(string="Active", default=True)
    line_ids = fields.One2many("account.pl.structure.line", "structure_id", string="Lines", copy=False)

    sales_dimension = fields.Selection(
        [("partner", "Customer"), ("analytic", "Analytic")],
        string="Sales dimension",
        required=True,
        default="partner",
        help="What the Sales leaves group by: commercial customers, or analytic accounts of the "
        "analytic plan selected below.",
    )
    analytic_mode = fields.Selection(
        [("none", "Not used"), ("analytic", "Analytic accounts"), ("project", "Projects")],
        string="Analytic usage",
        required=True,
        default="none",
        help="Whether the dashboard works with analytic accounts (of a given plan) or with projects. "
        "When used, the dashboard toolbar offers a filter by those analytic accounts or projects, "
        "and Sales leaves can be grouped by them.",
    )
    analytic_plan_id = fields.Many2one(
        "account.analytic.plan",
        string="Analytic plan",
        domain="[('parent_id', '=', False)]",
        help="Root analytic plan used when the analytic usage is 'Analytic accounts'.",
    )
    sales_account_ids = fields.Many2many(
        "account.account",
        "account_pl_structure_sales_account_rel",
        "structure_id",
        "account_id",
        string="Sales accounts",
        domain="[('account_type', 'in', %s), ('company_ids', 'parent_of', company_id)]" % (PL_ACCOUNT_TYPES,),
        help="Income accounts considered as Sales. Leave empty to use every account of type Income.",
    )
    excluded_journal_ids = fields.Many2many(
        "account.journal",
        "account_pl_structure_excluded_journal_rel",
        "structure_id",
        "journal_id",
        string="Excluded journals",
        check_company=True,
        help="Journal entries of these journals are ignored (e.g. year-end closing entries, which "
        "would otherwise empty the previous fiscal year's columns).",
    )
    budget_enabled = fields.Boolean(string="Compare with budget")
    budget_id = fields.Many2one(
        "account.report.budget",
        string="Budget",
        check_company=True,
        help="Accounting budget (by account and month) the actual figures are compared with.",
    )
    secondary_currency_id = fields.Many2one(
        "res.currency",
        string="Secondary currency",
        default=lambda self: self._default_secondary_currency(),
        domain="[('active', '=', True)]",
        help="Optional display currency, to reflect operations made in a foreign currency.",
    )
    default_display_currency = fields.Selection(
        [("company", "Company currency"), ("secondary", "Secondary currency")],
        string="Open dashboard in",
        required=True,
        default="company",
    )
    rate_max_age_days = fields.Integer(
        string="Maximum rate age (days)",
        default=5,
        help="In the secondary currency view, a day whose most recent exchange rate is older than "
        "this many days is reported as missing a rate (covers weekends and bank holidays).",
    )

    @api.model
    def _default_secondary_currency(self):
        usd = self.env.ref("base.USD", raise_if_not_found=False)
        if usd and usd.active and usd != self.env.company.currency_id:
            return usd
        return False

    # -------------------------------------------------------------------------
    # Constraints
    # -------------------------------------------------------------------------

    @api.constrains("active", "company_id")
    def _check_single_active_per_company(self):
        for structure in self.filtered("active"):
            duplicate = self.with_context(active_test=True).search([
                ("company_id", "=", structure.company_id.id),
                ("id", "!=", structure.id),
            ], limit=1)
            if duplicate:
                raise ValidationError(self.env._(
                    "Company %(company)s already has an active management P&L structure (%(structure)s). "
                    "Archive it before activating another one.",
                    company=structure.company_id.display_name,
                    structure=duplicate.display_name,
                ))

    @api.constrains("secondary_currency_id", "company_id", "default_display_currency")
    def _check_secondary_currency(self):
        for structure in self:
            currency = structure.secondary_currency_id
            if not currency:
                if structure.default_display_currency == "secondary":
                    raise ValidationError(self.env._(
                        "Set a secondary currency before using it as the default display currency."
                    ))
                continue
            if not currency.active:
                raise ValidationError(self.env._(
                    "The secondary currency %s is not active.", currency.name
                ))
            if currency == structure.company_id.currency_id:
                raise ValidationError(self.env._(
                    "The secondary currency must be different from the company currency (%s).", currency.name
                ))

    @api.constrains("rate_max_age_days")
    def _check_rate_max_age_days(self):
        if any(structure.rate_max_age_days < 0 for structure in self):
            raise ValidationError(self.env._("The maximum rate age can't be negative."))

    @api.constrains("analytic_mode", "analytic_plan_id", "sales_dimension")
    def _check_analytic_settings(self):
        for structure in self:
            if structure.analytic_mode == "analytic" and not structure.analytic_plan_id:
                raise ValidationError(self.env._("Select the analytic plan to use."))
            if structure.sales_dimension == "analytic" and structure.analytic_mode == "none":
                raise ValidationError(self.env._(
                    "Sales can only be grouped by analytic account when the analytic usage is set."
                ))

    @api.constrains("budget_enabled", "budget_id")
    def _check_budget(self):
        if any(structure.budget_enabled and not structure.budget_id for structure in self):
            raise ValidationError(self.env._("Select the budget to compare with."))

    @api.constrains("sales_account_ids", "company_id")
    def _check_sales_accounts(self):
        for structure in self:
            structure._check_accounts_company(structure.sales_account_ids)
        # Sales accounts can't be used by a cost leaf either.
        self.line_ids._check_unique_assignments()

    @api.constrains("analytic_mode", "analytic_plan_id")
    def _check_analytic_plan_of_lines(self):
        self.line_ids._check_analytic_accounts()

    def _check_accounts_company(self, accounts):
        """Accounts are shared between companies through ``company_ids``; an
        account is usable by a company when it belongs to it or to one of its
        parent companies (same rule as account.account's own
        ``_check_company_domain``)."""
        self.ensure_one()
        allowed_companies = self.company_id.parent_ids
        for account in accounts:
            if not account.sudo().company_ids & allowed_companies:
                raise ValidationError(self.env._(
                    "Account %(account)s is not available for company %(company)s.",
                    account=account.display_name,
                    company=self.company_id.display_name,
                ))

    # -------------------------------------------------------------------------
    # Helpers used by the lines and by the computation engine
    # -------------------------------------------------------------------------

    def _get_analytic_plan(self):
        """Root analytic plan the structure works with, or an empty recordset."""
        self.ensure_one()
        if self.analytic_mode == "project":
            project_plan, _other_plans = self.env["account.analytic.plan"]._get_all_plans()
            return project_plan
        if self.analytic_mode == "analytic":
            return self.analytic_plan_id
        return self.env["account.analytic.plan"]

    def _get_sales_accounts(self):
        """Accounts whose movements make up Sales (explicit list, or every
        Income account of the company when the list is empty)."""
        self.ensure_one()
        if self.sales_account_ids:
            return self.sales_account_ids
        return self.env["account.account"].sudo().with_context(active_test=False).search([
            ("account_type", "in", DEFAULT_SALES_ACCOUNT_TYPES),
            ("company_ids", "parent_of", self.company_id.id),
        ])

    @api.model
    def _get_active_structure(self, company=None):
        company = company or self.env.company
        return self.search([("company_id", "=", company.id)], limit=1)

    # -------------------------------------------------------------------------
    # CRUD
    # -------------------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        structures = super().create(vals_list)
        section_labels = dict(self.env["account.pl.structure.line"]._fields["section"]._description_selection(self.env))
        for structure in structures:
            self.env["account.pl.structure.line"].with_context(pl_allow_root_create=True).create([
                {
                    "structure_id": structure.id,
                    "section": section,
                    "name": section_labels[section],
                    "sequence": index * 10,
                }
                for index, (section, _label) in enumerate(SECTIONS, start=1)
            ])
        return structures

    def copy_data(self, default=None):
        vals_list = super().copy_data(default=default)
        return [dict(vals, name=self.env._("%s (copy)", structure.name), active=False)
                for structure, vals in zip(self, vals_list)]
