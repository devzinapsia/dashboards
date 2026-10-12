from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.fields import Domain

MEDIUM_KINDS = [
    ("bank", "Bank"),
    ("cash", "Cash"),
    ("petty_cash", "Petty cash fund"),
    ("prepaid", "Prepaid card"),
    ("credit_card", "Credit card"),
    ("investment", "Investment"),
]

# Journal types allowed for each kind of medium.
JOURNAL_TYPES_BY_KIND = {
    "bank": ("bank",),
    "cash": ("cash",),
    "petty_cash": ("cash",),
    "prepaid": ("bank", "cash"),
    "credit_card": ("credit",),
    "investment": ("bank", "general"),
}

# Kinds whose journal is mandatory; the others need a journal and/or accounts.
JOURNAL_REQUIRED_KINDS = ("bank", "cash", "petty_cash", "investment")

# Kinds counted in the available total unless unchecked.
AVAILABLE_BY_DEFAULT_KINDS = ("bank", "cash")

# Kinds holding money of the company (everything but credit cards, which are
# a liability). Movements between two of them are internal transfers.
LIQUID_KINDS = ("bank", "cash", "petty_cash", "prepaid", "investment")


class AccountTreasuryMedium(models.Model):
    """A payment mean of the treasury dashboard: a bank, cash, petty cash
    fund, prepaid card, credit card or investment, identified by a journal
    and/or accounting accounts."""

    _name = "account.treasury.medium"
    _description = "Treasury dashboard payment mean"
    _order = "config_id, sequence, id"
    _check_company_auto = True

    config_id = fields.Many2one(
        "account.treasury.config", string="Configuration", required=True, ondelete="cascade", index=True,
    )
    company_id = fields.Many2one(related="config_id.company_id", store=True, index=True)
    sequence = fields.Integer(string="Sequence", default=10)
    name = fields.Char(string="Name", required=True)
    kind = fields.Selection(MEDIUM_KINDS, string="Type", required=True)
    journal_id = fields.Many2one(
        "account.journal", string="Journal", check_company=True, domain="journal_domain", index="btree_not_null",
    )
    journal_ids = fields.Many2many(
        "account.journal",
        "account_treasury_medium_journal_rel",
        "medium_id",
        "journal_id",
        string="Journals",
        check_company=True,
        domain="journal_domain",
        help="Credit cards: the card's journals, e.g. one per cardholder, all booking on the card's account. The "
        "card is computed once, with all of them.",
    )
    journal_domain = fields.Binary(compute="_compute_journal_domain")
    account_ids = fields.Many2many(
        "account.account",
        "account_treasury_medium_account_rel",
        "medium_id",
        "account_id",
        string="Accounts",
        check_company=True,
        help="Accounting accounts of this payment mean, in addition to its journal's account (or instead of "
        "it, for prepaid and credit cards without a journal).",
    )
    currency_id = fields.Many2one(
        "res.currency", string="Currency", compute="_compute_currency_id",
        help="Currency of the payment mean: the one of its journal, or of its accounting account; the company "
        "currency when they have none.",
    )
    in_available_total = fields.Boolean(
        string="In available total",
        compute="_compute_in_available_total", store=True, readonly=False, precompute=True,
        help="Whether this payment mean adds up to the dashboard's available total (and, for banks and cash, to "
        "the cash projection's opening balance).",
    )
    in_projection = fields.Boolean(
        string="In cash projection",
        help="Investments only: whether its balance, valued at the rate of the day, adds up to the cash "
        "projection's opening balance, as money available for the coming weeks.",
    )
    stale_days = fields.Integer(
        string="Days without a new statement",
        help="Overrides the general setting for this bank. Leave it at 0 to use the general setting.",
    )
    closing_day = fields.Integer(string="Closing day", help="Day of the month the credit card statement closes.")
    due_day = fields.Integer(
        string="Due day",
        help="Day of the month the credit card statement is due. If it is lower than or equal to the closing "
        "day, it falls in the following month.",
    )
    credit_limit = fields.Monetary(string="Credit limit", currency_field="currency_id")
    active = fields.Boolean(string="Active", default=True)

    # -------------------------------------------------------------------------
    # Computes
    # -------------------------------------------------------------------------

    @api.depends("kind", "company_id")
    def _compute_journal_domain(self):
        for medium in self:
            medium.journal_domain = Domain.AND([
                Domain(self.env["account.journal"]._check_company_domain(medium.company_id)),
                Domain("type", "in", JOURNAL_TYPES_BY_KIND.get(medium.kind, ())),
            ])

    @api.depends("journal_id.currency_id", "journal_id.default_account_id.currency_id",
                 "journal_ids.currency_id", "journal_ids.default_account_id.currency_id",
                 "account_ids.currency_id", "company_id.currency_id")
    def _compute_currency_id(self):
        for medium in self:
            account_currencies = medium._get_own_accounts().currency_id
            journal_currencies = (medium.journal_id | medium.journal_ids).currency_id
            medium.currency_id = (
                (journal_currencies if len(journal_currencies) == 1 else False)
                or (account_currencies if len(account_currencies) == 1 else False)
                or medium.company_id.currency_id
            )

    @api.depends("kind")
    def _compute_in_available_total(self):
        for medium in self:
            medium.in_available_total = medium.kind in AVAILABLE_BY_DEFAULT_KINDS

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    def _get_own_accounts(self):
        """Accounts that belong to this payment mean only: its journal's
        default account and its own accounts. (The journal's outstanding
        receipts/payments accounts are usually shared between journals, so
        they are filtered by journal wherever they are read, not listed
        here.)"""
        return (self.journal_id | self.journal_ids).default_account_id | self.account_ids

    def _get_journals(self):
        """The journals of this payment mean: its own journal, and every bank,
        cash or credit card journal of the company whose default account is
        one of its accounts (e.g. two cardholders' credit card journals
        booking on the same card account, configured as a single payment
        mean with that account)."""
        self.ensure_one()
        journals = self.journal_id | self.journal_ids
        own_accounts = self._get_own_accounts()
        if own_accounts:
            journals |= self.env["account.journal"].sudo().with_context(active_test=True).search([
                ("company_id", "=", self.company_id.id),
                ("type", "in", ("bank", "cash", "credit")),
                ("default_account_id", "in", own_accounts.ids),
            ])
        return journals

    def _kind_label(self):
        self.ensure_one()
        return dict(self._fields["kind"]._description_selection(self.env))[self.kind]

    def _active_peers_domain(self):
        """Other active payment means of active configurations of the same
        company: the ones a journal or account can't be shared with."""
        self.ensure_one()
        return [
            ("company_id", "=", self.company_id.id),
            ("config_id.active", "=", True),
            ("id", "!=", self.id),
        ]

    # -------------------------------------------------------------------------
    # Constraints
    # -------------------------------------------------------------------------

    @api.constrains("kind", "journal_id", "journal_ids", "account_ids")
    def _check_journal_and_accounts(self):
        for medium in self:
            if medium.kind in JOURNAL_REQUIRED_KINDS and not medium.journal_id:
                raise ValidationError(self.env._(
                    "%(name)s: a payment mean of type %(kind)s needs a journal.",
                    name=medium.name, kind=medium._kind_label(),
                ))
            if not medium.journal_id and not medium.journal_ids and not medium.account_ids:
                raise ValidationError(self.env._(
                    "%(name)s: a payment mean of type %(kind)s needs a journal, accounts, or both.",
                    name=medium.name, kind=medium._kind_label(),
                ))
            allowed_types = JOURNAL_TYPES_BY_KIND[medium.kind]
            for journal in medium.journal_id | medium.journal_ids:
                if journal.type in allowed_types:
                    continue
                type_labels = dict(self.env["account.journal"]._fields["type"]._description_selection(self.env))
                raise ValidationError(self.env._(
                    "%(name)s: journal %(journal)s is of type %(journal_type)s, but a payment mean of type "
                    "%(kind)s needs a journal of type %(allowed)s.",
                    name=medium.name,
                    journal=journal.display_name,
                    journal_type=type_labels[journal.type],
                    kind=medium._kind_label(),
                    allowed=" / ".join(type_labels[journal_type] for journal_type in allowed_types),
                ))

    @api.constrains("journal_id", "journal_ids", "account_ids", "active", "config_id")
    def _check_unique_journal_and_accounts(self):
        for medium in self.filtered(lambda medium: medium.active and medium.config_id.active):
            for journal in medium.journal_id | medium.journal_ids:
                other = self.search([*medium._active_peers_domain(), "|", ("journal_id", "=", journal.id),
                                     ("journal_ids", "in", journal.ids)], limit=1)
                if other:
                    raise ValidationError(self.env._(
                        "Journal %(journal)s is already used by payment mean %(other)s (%(kind)s). A journal can "
                        "only be in one payment mean: change the type of %(other)s, or archive it, before using "
                        "the journal in another one.",
                        journal=journal.display_name, other=other.name, kind=other._kind_label(),
                    ))
            own_accounts = medium._get_own_accounts()
            if not own_accounts:
                continue
            others = self.search(medium._active_peers_domain())
            for other in others:
                shared = own_accounts & other._get_own_accounts()
                if shared and medium.kind == other.kind == "credit_card":
                    raise ValidationError(self.env._(
                        "Account %(account)s is already used by credit card %(other)s. Journals booking on the same "
                        "card account (e.g. one per cardholder) go in the same credit card: add the journal to the "
                        "Journals of %(other)s instead of creating another credit card.",
                        account=shared[0].display_name, other=other.name,
                    ))
                if shared:
                    raise ValidationError(self.env._(
                        "Account %(account)s is already used by payment mean %(other)s (%(kind)s). An account can "
                        "only be in one payment mean: change the type of %(other)s, or archive it, before using "
                        "the account in another one.",
                        account=shared[0].display_name, other=other.name, kind=other._kind_label(),
                    ))
            commitment = self.env["account.treasury.commitment"].search([
                ("company_id", "=", medium.company_id.id),
                ("config_id.active", "=", True),
                ("account_ids", "in", own_accounts.ids),
            ], limit=1)
            if commitment:
                shared = own_accounts & commitment.account_ids
                raise ValidationError(self.env._(
                    "Account %(account)s is already used by projection commitment %(commitment)s.",
                    account=shared[0].display_name, commitment=commitment.name,
                ))

    @api.constrains("kind", "closing_day", "due_day", "credit_limit", "stale_days")
    def _check_card_and_days(self):
        for medium in self:
            if medium.stale_days < 0:
                raise ValidationError(self.env._(
                    "%s: the days without a new statement can't be negative.", medium.name,
                ))
            if medium.kind != "credit_card":
                continue
            for day, label in ((medium.closing_day, self.env._("closing day")),
                               (medium.due_day, self.env._("due day"))):
                if not 1 <= day <= 31:
                    raise ValidationError(self.env._(
                        "%(name)s: the %(day)s must be between 1 and 31.", name=medium.name, day=label,
                    ))
            if medium.credit_limit < 0:
                raise ValidationError(self.env._("%s: the credit limit can't be negative.", medium.name))
