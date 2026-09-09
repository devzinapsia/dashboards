from odoo.tests.common import TransactionCase


class TestDashboardsBase(TransactionCase):

    def test_root_menu(self):
        menu = self.env.ref("dashboards_base.menu_dashboards_root")
        self.assertEqual(menu.name, "Dashboards")
        self.assertFalse(menu.parent_id)

    def test_submenus(self):
        root_menu = self.env.ref("dashboards_base.menu_dashboards_root")
        boards_menu = self.env.ref("dashboards_base.menu_dashboards_boards")
        config_menu = self.env.ref("dashboards_base.menu_dashboards_config")
        self.assertEqual(boards_menu.parent_id, root_menu)
        self.assertEqual(config_menu.parent_id, root_menu)

    def test_module_category(self):
        category = self.env.ref("dashboards_base.module_category_dashboards")
        self.assertEqual(category.name, "Dashboards")

    def test_drilldown_action_default_view(self):
        action = self.env["dashboards.drilldown.mixin"]._get_drilldown_action(
            "res.partner", domain=[("customer_rank", ">", 0)], name="Test Drilldown"
        )
        self.assertEqual(action["type"], "ir.actions.act_window")
        self.assertEqual(action["res_model"], "res.partner")
        self.assertEqual(action["domain"], [("customer_rank", ">", 0)])
        self.assertEqual(action["views"], [(False, "list"), (False, "form")])
        self.assertEqual(action["name"], "Test Drilldown")

    def test_drilldown_action_form_view(self):
        action = self.env["dashboards.drilldown.mixin"]._get_drilldown_action(
            "res.partner", view_type="form"
        )
        self.assertEqual(action["views"], [(False, "form")])

    def test_drilldown_action_default_name(self):
        action = self.env["dashboards.drilldown.mixin"]._get_drilldown_action("res.partner")
        self.assertTrue(action["name"])

    def test_native_drilldown_action(self):
        action = self.env["dashboards.drilldown.mixin"]._get_native_drilldown_action(
            "base.action_partner_form",
            domain=[("customer_rank", ">", 0)],
            context={"default_customer_rank": 1},
        )
        self.assertEqual(action["res_model"], "res.partner")
        self.assertEqual(action["domain"], [("customer_rank", ">", 0)])
        self.assertEqual(action["context"]["default_customer_rank"], 1)
