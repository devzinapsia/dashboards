from odoo import api, fields, models
from odoo.exceptions import ValidationError

COMMITMENT_KINDS = [
    ("payroll", "Payroll"),
    ("tax", "Tax"),
    ("other", "Other"),
]


class AccountTreasuryCommitment(models.Model):
    """A liability that the cash projection pays out (salaries, social
    charges, taxes, ...).

    - "open_items" mode, when every account allows reconciliation: each open
      journal item is projected on its due date, with its partner.
    - "balance" mode, when an account doesn't: the accounts' current credit
      balance is projected on the next occurrence of the payment day (an
      account that can't be reconciled has no open items to follow).
    """

    _name = "account.treasury.commitment"
    _description = "Treasury dashboard projection commitment"
    _order = "config_id, sequence, id"
    _check_company_auto = True

    config_id = fields.Many2one(
        "account.treasury.config", string="Configuration", required=True, ondelete="cascade", index=True,
    )
    company_id = fields.Many2one(related="config_id.company_id", store=True, index=True)
    sequence = fields.Integer(string="Sequence", default=10)
    name = fields.Char(
        string="Name", required=True, compute="_compute_name", store=True, readonly=False, precompute=True,
        help="Filled with the accounts' names when left empty.",
    )
    kind = fields.Selection(COMMITMENT_KINDS, string="Type", required=True, default="other")
    account_ids = fields.Many2many(
        "account.account",
        "account_treasury_commitment_account_rel",
        "commitment_id",
        "account_id",
        string="Accounts",
        required=True,
        check_company=True,
    )
    mode = fields.Selection(
        [("open_items", "Open items"), ("balance", "Account balance")],
        string="Mode",
        compute="_compute_mode",
        store=True,
        help="Open items when every account allows reconciliation (each open item on its due date), account "
        "balance otherwise (the current balance on the due date of the latest entry crediting the accounts, or on "
        "the payment day if set).",
    )
    payment_day = fields.Integer(
        string="Payment day",
        help="Optional, account balance mode only: day of the month the balance is paid. Without it, the balance "
        "is projected on the due date of the latest entry crediting the accounts.",
    )
    active = fields.Boolean(string="Active", default=True)

    @api.depends("account_ids")
    def _compute_name(self):
        for commitment in self:
            if not commitment.name and commitment.account_ids:
                commitment.name = ", ".join(commitment.account_ids.mapped("name"))

    @api.depends("account_ids.reconcile")
    def _compute_mode(self):
        for commitment in self:
            if commitment.account_ids and all(commitment.account_ids.mapped("reconcile")):
                commitment.mode = "open_items"
            else:
                commitment.mode = "balance"

    @api.constrains("payment_day")
    def _check_payment_day(self):
        for commitment in self:
            if commitment.payment_day and not 1 <= commitment.payment_day <= 31:
                raise ValidationError(self.env._(
                    "%s: the payment day must be between 1 and 31.", commitment.name,
                ))

    @api.constrains("account_ids", "active", "config_id")
    def _check_unique_accounts(self):
        for commitment in self.filtered(lambda commitment: commitment.active and commitment.config_id.active):
            peers_domain = [
                ("company_id", "=", commitment.company_id.id),
                ("config_id.active", "=", True),
            ]
            other = self.search([*peers_domain, ("id", "!=", commitment.id),
                                 ("account_ids", "in", commitment.account_ids.ids)], limit=1)
            if other:
                shared = commitment.account_ids & other.account_ids
                raise ValidationError(self.env._(
                    "Account %(account)s is already used by projection commitment %(other)s.",
                    account=shared[0].display_name, other=other.name,
                ))
            for medium in self.env["account.treasury.medium"].search(peers_domain):
                shared = commitment.account_ids & medium._get_own_accounts()
                if shared:
                    raise ValidationError(self.env._(
                        "Account %(account)s is already used by payment mean %(medium)s (%(kind)s).",
                        account=shared[0].display_name, medium=medium.name, kind=medium._kind_label(),
                    ))
