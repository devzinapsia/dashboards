def migrate(cr, version):
    """Credit cards show their journals' account in Accounts: add it to the
    credit cards configured so far."""
    cr.execute("""
        INSERT INTO account_treasury_medium_account_rel (medium_id, account_id)
             SELECT DISTINCT medium.id, journal.default_account_id
               FROM account_treasury_medium medium
               JOIN account_treasury_medium_journal_rel rel ON rel.medium_id = medium.id
               JOIN account_journal journal ON journal.id = rel.journal_id
              WHERE medium.kind = 'credit_card'
                AND journal.default_account_id IS NOT NULL
        ON CONFLICT DO NOTHING
    """)
