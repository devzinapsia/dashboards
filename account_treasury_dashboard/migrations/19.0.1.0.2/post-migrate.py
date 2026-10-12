def migrate(cr, version):
    """The configuration menu is now "Treasury" ("Tesorería") instead of
    "Treasury dashboard" ("Tablero de tesorería"). Updating the module only
    changes the English name: drop the menu's other translations, so that
    the module's .po files, loaded right after this script (and which never
    overwrite an existing translation), set them again."""
    cr.execute("""
        UPDATE ir_ui_menu
           SET name = jsonb_build_object('en_US', name->>'en_US')
         WHERE id IN (
            SELECT res_id
              FROM ir_model_data
             WHERE module = 'account_treasury_dashboard'
               AND model = 'ir.ui.menu'
               AND name = 'menu_account_treasury_config'
         )
    """)
