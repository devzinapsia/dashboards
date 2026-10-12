from odoo import api, models
from odoo.exceptions import ValidationError


class AccountTreasuryMedium(models.Model):
    _inherit = "account.treasury.medium"

    @api.constrains("journal_id", "active")
    def _check_not_a_check_journal(self):
        """A check journal's portfolio is projected on each check's payment
        date: as a bank or cash payment mean in the available total it would
        also be in the projection's opening balance, counted twice."""
        for medium in self.filtered(lambda medium: medium.active and medium.journal_id):
            if medium.journal_id in medium.config_id._get_check_journals():
                raise ValidationError(self.env._(
                    "Journal %(journal)s is configured as a check journal, so it can't be payment mean %(medium)s: "
                    "its checks are shown in the Checks section.",
                    journal=medium.journal_id.display_name, medium=medium.name,
                ))
