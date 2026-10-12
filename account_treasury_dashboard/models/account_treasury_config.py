from odoo import Command, api, fields, models
from odoo.exceptions import ValidationError

PROJECTION_WEEKS_MIN = 4
PROJECTION_WEEKS_MAX = 8

# Payment mean type suggested for each journal type by "Load suggested".
SUGGESTED_KINDS = {"bank": "bank", "cash": "cash", "credit": "credit_card"}
# Default closing and due days of a suggested credit card.
SUGGESTED_CARD_DAYS = {"closing_day": 30, "due_day": 8}


class AccountTreasuryConfig(models.Model):
    """Per-company settings of the treasury dashboard.

    Everything company-specific lives here: which journals/accounts are a
    bank, cash, petty cash fund, prepaid card, credit card or investment
    (account.treasury.medium), which liabilities feed the cash projection
    (account.treasury.commitment), and the thresholds. A dashboard section
    with nothing configured for it is not shown.
    """

    _name = "account.treasury.config"
    _description = "Treasury dashboard configuration"
    _order = "company_id, id"
    _check_company_auto = True

    company_id = fields.Many2one(
        "res.company", string="Company", required=True, default=lambda self: self.env.company, index=True,
    )
    company_currency_id = fields.Many2one(related="company_id.currency_id", string="Company currency")
    active = fields.Boolean(string="Active", default=True)

    statement_stale_days = fields.Integer(
        string="Days without a new statement",
        default=3,
        help="A bank whose latest statement line is older than this many days is flagged on the dashboard. "
        "Each bank can override it.",
    )
    projection_weeks = fields.Integer(
        string="Projection weeks",
        default=6,
        help="Number of weeks of the cash projection (between 4 and 8). Week 1 runs from today to the next Sunday.",
    )
    include_overdue_receivables = fields.Boolean(
        string="Include overdue receivables in week 1",
        help="If checked, overdue customer receivables add to week 1 of the cash projection. Otherwise they "
        "are shown in a separate row and don't change the projected balance.",
    )

    show_cash_position = fields.Boolean(string="Show cash position", default=True)
    show_reconciliation = fields.Boolean(string="Show reconciliation", default=True)
    show_investments = fields.Boolean(string="Show investments", default=True)
    show_projection = fields.Boolean(string="Show cash projection", default=True)
    show_movements = fields.Boolean(string="Show period movements", default=True)

    medium_ids = fields.One2many(
        "account.treasury.medium", "config_id", string="Payment means", context={"active_test": False},
    )
    # The same mediums, split by tab of the configuration form.
    bank_medium_ids = fields.One2many(
        "account.treasury.medium", "config_id", string="Banks",
        domain=[("kind", "=", "bank")], context={"active_test": False},
    )
    fund_medium_ids = fields.One2many(
        "account.treasury.medium", "config_id", string="Petty cash funds and prepaid cards",
        domain=[("kind", "in", ("cash", "petty_cash", "prepaid"))], context={"active_test": False},
    )
    credit_card_medium_ids = fields.One2many(
        "account.treasury.medium", "config_id", string="Credit cards",
        domain=[("kind", "=", "credit_card")], context={"active_test": False},
    )
    investment_medium_ids = fields.One2many(
        "account.treasury.medium", "config_id", string="Investments",
        domain=[("kind", "=", "investment")], context={"active_test": False},
    )
    commitment_ids = fields.One2many(
        "account.treasury.commitment", "config_id", string="Projection commitments", context={"active_test": False},
    )

    has_balance_commitments = fields.Boolean(compute="_compute_has_balance_commitments")

    @api.depends("commitment_ids.mode", "commitment_ids.active")
    def _compute_has_balance_commitments(self):
        for config in self:
            config.has_balance_commitments = any(
                commitment.active and commitment.mode == "balance" for commitment in config.commitment_ids
            )

    # -------------------------------------------------------------------------
    # Constraints
    # -------------------------------------------------------------------------

    @api.constrains("active", "company_id")
    def _check_single_active_per_company(self):
        for config in self.filtered("active"):
            duplicate = self.search([
                ("company_id", "=", config.company_id.id),
                ("id", "!=", config.id),
            ], limit=1)
            if duplicate:
                raise ValidationError(self.env._(
                    "Company %s already has an active treasury dashboard configuration. Archive it before "
                    "activating another one.",
                    config.company_id.display_name,
                ))

    @api.constrains("projection_weeks")
    def _check_projection_weeks(self):
        for config in self:
            if not PROJECTION_WEEKS_MIN <= config.projection_weeks <= PROJECTION_WEEKS_MAX:
                raise ValidationError(self.env._(
                    "The cash projection must have between %(min)s and %(max)s weeks.",
                    min=PROJECTION_WEEKS_MIN,
                    max=PROJECTION_WEEKS_MAX,
                ))

    @api.constrains("statement_stale_days")
    def _check_statement_stale_days(self):
        for config in self:
            if config.statement_stale_days < 1:
                raise ValidationError(self.env._("The days without a new statement must be at least 1."))

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    @api.model
    def _get_active_config(self, company=None):
        company = company or self.env.company
        return self.search([("company_id", "=", company.id)], limit=1)

    def _compute_display_name(self):
        # A per-company setting opened straight from the Configuration menu:
        # the breadcrumb says what the screen is for.
        for config in self:
            config.display_name = self.env._("Treasury dashboard settings")

    @api.model
    def action_open_config(self):
        """Configuration menu entry: open the current company's settings
        directly (creating them on first use). No "New" nor "Delete": one
        configuration per company. The web client only honors these through
        the action's context.
        """
        config = self._get_active_config() or self.create({"company_id": self.env.company.id})
        return config._get_records_action(
            name=self.env._("Treasury dashboard settings"),
            context={**self.env.context, "create": False, "delete": False},
        )

    # -------------------------------------------------------------------------
    # "Load suggested"
    # -------------------------------------------------------------------------

    def _get_suggested_journal_domain(self):
        """Journals offered by "Load suggested". Extension point: e.g. a
        checks module can leave out its third-party check journals (which
        are cash journals too)."""
        self.ensure_one()
        return [
            *self.env["account.journal"]._check_company_domain(self.company_id),
            ("company_id", "=", self.company_id.id),
            ("type", "in", ("bank", "cash", "credit")),
        ]

    def _suggested_medium_values(self, journals):
        """Values of the payment mean suggested for ``journals``, journals of
        the same type sharing the same default account."""
        journal = journals[0]
        kind = SUGGESTED_KINDS[journal.type]
        values = {"config_id": self.id, "kind": kind}
        if kind == "credit_card":
            # A credit card is named after its account, and lists the account
            # and the journals booking on it (one per cardholder of the same
            # card).
            account = journal.default_account_id
            values.update({
                "name": account.name or journal.name,
                "journal_ids": [Command.set(journals.ids)],
                "account_ids": [Command.set(account.ids)],
                **SUGGESTED_CARD_DAYS,
            })
            return values
        if len(journals) == 1:
            values.update({"name": journal.name, "journal_id": journal.id})
        else:
            # Several journals booking on the same account (e.g. one per
            # cardholder of the same card): a single payment mean with the
            # account, so that its balance is counted once.
            account = journal.default_account_id
            values.update({"name": account.name, "account_ids": [Command.set(account.ids)]})
        return values

    def action_load_suggested(self):
        """Create a payment mean for every bank, cash and credit card journal
        of the company that no payment mean uses yet: banks, cash (petty cash
        funds are changed to that type by hand) and credit cards (closing on
        the 30th, due on the 8th by default). Journals of the same type
        sharing their default account get a single payment mean with that
        account. Journals, or accounts, already used by a payment mean
        (archived ones included, so that an archived one isn't brought back)
        are left out, and existing payment means are left untouched. Prepaid
        cards and investments are loaded by hand."""
        Medium = self.env["account.treasury.medium"]
        for config in self:
            existing = Medium.with_context(active_test=False).search([("company_id", "=", config.company_id.id)])
            used_journals = existing.journal_id | existing.journal_ids
            used_accounts = used_journals.default_account_id | existing.account_ids
            # Only active journals: the settings form's lists show archived
            # payment means, and their context must not bring back archived
            # journals.
            journals = self.env["account.journal"].with_context(active_test=True).search(
                [*config._get_suggested_journal_domain(), ("id", "not in", used_journals.ids)],
                order="type, sequence, id",
            )
            groups = {}
            for journal in journals:
                account = journal.default_account_id
                if account and account in used_accounts:
                    continue
                key = (journal.type, account.id or ("journal", journal.id))
                groups.setdefault(key, self.env["account.journal"])
                groups[key] |= journal
            last_sequence = max(config.medium_ids.mapped("sequence") or [0])
            Medium.create([
                {**config._suggested_medium_values(group), "sequence": last_sequence + index}
                for index, group in enumerate(groups.values(), start=1)
            ])
        return True
