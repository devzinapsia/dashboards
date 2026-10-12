from odoo import api, fields, models
from odoo.exceptions import ValidationError


class AccountTreasuryConfig(models.Model):
    _inherit = "account.treasury.config"

    show_checks = fields.Boolean(string="Show checks", default=True)
    third_party_check_journal_ids = fields.Many2many(
        "account.journal",
        "account_treasury_config_third_party_check_journal_rel",
        "config_id",
        "journal_id",
        string="Third-party check journals",
        check_company=True,
        domain="[('type', '=', 'cash'), ('company_id', '=', company_id)]",
        help="Journals holding the third-party checks in portfolio. Their checks are shown in the Checks section "
        "and projected on their payment date; these journals can't be a bank or cash payment mean.",
    )
    rejected_check_journal_ids = fields.Many2many(
        "account.journal",
        "account_treasury_config_rejected_check_journal_rel",
        "config_id",
        "journal_id",
        string="Rejected check journals",
        check_company=True,
        domain="[('type', '=', 'cash'), ('company_id', '=', company_id)]",
        help="Odoo has no 'rejected' state for third-party checks: a check counts as rejected because it sits in "
        "one of these journals. Rejected checks are shown apart and never projected as a receipt.",
    )

    def _get_check_journals(self):
        return self.third_party_check_journal_ids | self.rejected_check_journal_ids

    @api.constrains("third_party_check_journal_ids", "rejected_check_journal_ids")
    def _check_check_journals(self):
        for config in self:
            both = config.third_party_check_journal_ids & config.rejected_check_journal_ids
            if both:
                raise ValidationError(self.env._(
                    "Journal %s can't be both a third-party check journal and a rejected check journal.",
                    both[0].display_name,
                ))
            medium = config.medium_ids.filtered(
                lambda medium: medium.active and medium.journal_id in config._get_check_journals())[:1]
            if medium:
                raise ValidationError(self.env._(
                    "Journal %(journal)s is a check journal, so it can't be payment mean %(medium)s: its checks are "
                    "shown in the Checks section. Remove the payment mean first.",
                    journal=medium.journal_id.display_name, medium=medium.name,
                ))

    def _get_suggested_journal_domain(self):
        # Check journals are cash journals too, but their portfolio is shown
        # in the Checks section, never as cash.
        return [*super()._get_suggested_journal_domain(), ("id", "not in", self._get_check_journals().ids)]
