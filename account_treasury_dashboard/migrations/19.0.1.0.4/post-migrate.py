def migrate(cr, version):
    """Credit cards now list their journals in "Journals" (several cardholders'
    journals booking on the same card account): move the journal of the
    credit cards configured so far there."""
    cr.execute("""
        INSERT INTO account_treasury_medium_journal_rel (medium_id, journal_id)
             SELECT id, journal_id
               FROM account_treasury_medium
              WHERE kind = 'credit_card'
                AND journal_id IS NOT NULL
        ON CONFLICT DO NOTHING
    """)
    cr.execute("""
        UPDATE account_treasury_medium
           SET journal_id = NULL
         WHERE kind = 'credit_card'
           AND journal_id IS NOT NULL
    """)
