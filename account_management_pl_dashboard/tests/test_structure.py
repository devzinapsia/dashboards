from odoo import Command
from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged

from .common import PlDashboardCommon


@tagged("post_install", "-at_install")
class TestPlStructure(PlDashboardCommon):

    def test_sections_created_automatically(self):
        roots = self.structure.line_ids.filtered("is_root")
        self.assertEqual(roots.mapped("section"), ["income", "direct_cost", "indirect_cost"])
        self.assertTrue(all(not root.parent_id for root in roots))

    def test_sections_cannot_be_deleted_or_moved(self):
        with self.assertRaises(UserError):
            self.root_income.unlink()
        with self.assertRaises(UserError):
            self.root_direct.parent_id = self.root_income
        with self.assertRaises(UserError):
            self.root_direct.write({"root_section": "income"})

    def test_children_inherit_section(self):
        self.assertEqual(self.leaf_salaries.section, "direct_cost")
        self.assertEqual(self.leaf_salaries.level, 2)
        self.assertEqual(self.leaf_salaries.complete_name, "Direct costs / Staff / Salaries")
        # Moving a group moves its whole subtree to the new section.
        self.group_staff.parent_id = self.root_indirect
        self.assertEqual(self.leaf_salaries.section, "indirect_cost")

    def test_hierarchical_order(self):
        lines = self.structure.line_ids
        self.assertEqual(lines.mapped("name"), [
            "Sales", "Services sales",
            "Direct costs", "Staff", "Salaries", "Sales commissions",
            "Indirect costs", "Rent",
        ])

    def test_line_without_parent_goes_to_indirect_costs(self):
        # Never a new section: there are exactly three.
        line = self.Line.create({"structure_id": self.structure.id, "name": "Orphan"})
        self.assertEqual(line.parent_id, self.root_indirect)
        self.assertFalse(line.is_root)
        self.assertEqual(len(self.structure.line_ids.filtered("is_root")), 3)
        with self.assertRaises(ValidationError):
            line.parent_id = False

    def test_add_line_at_the_end_of_its_parent(self):
        # What "Add a line" sends when a section (or nothing) is selected.
        line = self.Line.create({
            "structure_id": self.structure.id, "parent_id": self.root_direct.id,
            "name": "Taxes", "sequence": 1000000,
        })
        self.assertEqual(self.root_direct.child_ids.sorted("sort_key")[-1], line)
        self.assertLess(line.sequence, 1000000)

    def test_add_line_right_after_the_selected_one(self):
        # What "Add a line" sends when a line is selected: its parent, and
        # INSERT_AFTER + its sequence.
        self.group_staff.sequence = 10
        self.leaf_commissions.sequence = 11
        line = self.Line.create({
            "structure_id": self.structure.id, "parent_id": self.root_direct.id,
            "name": "Bonuses", "sequence": 2000000 + 10,
        })
        names = self.root_direct.child_ids.sorted("sort_key").mapped("name")
        self.assertEqual(names, ["Staff", "Bonuses", "Sales commissions"])
        self.assertEqual(line.parent_id, self.root_direct)

    def test_group_cannot_have_assignments(self):
        with self.assertRaisesRegex(ValidationError, "is a group"):
            self.group_staff.account_ids = [Command.link(self.account_social.id)]

    def test_leaf_with_assignments_cannot_receive_children(self):
        with self.assertRaisesRegex(ValidationError, "can't have sub-lines"):
            self.Line.create({
                "structure_id": self.structure.id,
                "parent_id": self.leaf_salaries.id,
                "name": "Bonuses",
            })
        with self.assertRaises(UserError):
            self.leaf_salaries.action_add_child()

    def test_add_child_on_group(self):
        self.group_staff.action_add_child()
        self.assertEqual(len(self.group_staff.child_ids), 2)

    def test_section_root_cannot_have_assignments(self):
        with self.assertRaises(ValidationError):
            self.root_direct.account_ids = [Command.link(self.account_social.id)]

    def test_duplicate_account_across_cost_sections(self):
        # Real case from the spreadsheet: the same commissions account in a
        # direct cost leaf and in an indirect cost leaf.
        with self.assertRaisesRegex(ValidationError, "already used in line Direct costs / Sales commissions"):
            self.Line.create({
                "structure_id": self.structure.id,
                "parent_id": self.root_indirect.id,
                "name": "Non-wage incentives",
                "account_ids": [Command.set(self.account_commissions.ids)],
            })

    def test_same_account_allowed_in_other_structure(self):
        other = self.Structure.create({"name": "Draft structure", "active": False, "company_id": self.company.id})
        root = other.line_ids.filtered(lambda line: line.section == "direct_cost")
        self.Line.create({
            "structure_id": other.id,
            "parent_id": root.id,
            "name": "Commissions",
            "account_ids": [Command.set(self.account_commissions.ids)],
        })

    def test_account_once_across_sections(self):
        # A Sales account can't be counted again by a cost line.
        with self.assertRaisesRegex(ValidationError, "already used in line Sales / Services sales"):
            self.leaf_rent.account_ids = [Command.link(self.account_sales.id)]

    def test_sales_line_takes_accounts(self):
        self.leaf_sales.account_ids = [Command.link(self.account_other_income.id)]
        self.assertEqual(self.structure._get_sales_accounts(), self.account_sales | self.account_other_income)
        self.assertFalse(self.leaf_sales.assignment_status)

    def test_cost_account_must_be_pl(self):
        balance_account = self.company_data["default_account_receivable"]
        with self.assertRaisesRegex(ValidationError, "not an income or expense account"):
            self.leaf_rent.account_ids = [Command.link(balance_account.id)]

    def test_cost_account_must_belong_to_company(self):
        other_company_account = self.env["account.account"].create({
            "code": "5.9.9.99.999",
            "name": "Other company expense",
            "account_type": "expense",
            "company_ids": [Command.set(self.company_data_2["company"].ids)],
        })
        both_companies = (self.company | self.company_data_2["company"]).ids
        with self.assertRaisesRegex(ValidationError, "is not available for company"):
            self.leaf_rent.with_context(allowed_company_ids=both_companies).account_ids = [
                Command.link(other_company_account.id),
            ]

    def test_assignment_status(self):
        empty_leaf = self.Line.create({
            "structure_id": self.structure.id,
            "parent_id": self.root_indirect.id,
            "name": "IT infrastructure",
        })
        self.assertEqual(empty_leaf.assignment_status, "Without accounts")
        self.assertFalse(self.leaf_rent.assignment_status)
        self.assertFalse(self.group_staff.assignment_status)
        empty_sales = self.Line.create({
            "structure_id": self.structure.id,
            "parent_id": self.root_income.id,
            "name": "Others",
        })
        self.assertEqual(empty_sales.assignment_status, "Without accounts")

    def test_single_active_structure_per_company(self):
        with self.assertRaisesRegex(ValidationError, "already has an active"):
            self.Structure.create({"name": "Second", "company_id": self.company.id})
        self.Structure.create({"name": "Archived one", "company_id": self.company.id, "active": False})

    def test_secondary_currency_validation(self):
        with self.assertRaisesRegex(ValidationError, "different from the company currency"):
            self.structure.secondary_currency_id = self.company.currency_id
        inactive = self.env["res.currency"].with_context(active_test=False).search(
            [("active", "=", False)], limit=1,
        )
        if inactive:
            with self.assertRaisesRegex(ValidationError, "is not active"):
                self.structure.secondary_currency_id = inactive
        self.structure.secondary_currency_id = self.eur if self.company.currency_id != self.eur else self.usd

    def test_secondary_default_needs_currency(self):
        with self.assertRaises(ValidationError):
            self.structure.write({"secondary_currency_id": False, "default_display_currency": "secondary"})

    def test_views_load(self):
        """Structure form (with its lines list, "View" link included) and the
        line form opened from it."""
        form = self.Structure.get_views([(False, "form")])["views"]["form"]["arch"]
        self.assertIn('open_form_view="True"', form)
        self.assertIn('name="account_ids"', form)
        # Without "active" in the form there is no Archive action (no gear menu).
        self.assertNotIn('name="active"', form)
        line_form = self.Line.get_views([(False, "form")])["views"]["form"]["arch"]
        self.assertIn('name="account_ids"', line_form)

    def test_configuration_opens_company_structure(self):
        action = self.Structure.action_open_config()
        self.assertEqual(action["res_model"], "account.pl.structure")
        self.assertEqual(action["res_id"], self.structure.id)
        self.assertEqual(action["name"], "Configure management P&L structure")
        self.assertFalse(action["context"]["create"])
        self.assertFalse(action["context"]["delete"])
        self.assertEqual(self.structure.display_name, "Configure management P&L structure")

    def test_configuration_creates_structure_on_first_use(self):
        self.structure.active = False
        action = self.Structure.action_open_config()
        created = self.Structure.browse(action["res_id"])
        self.assertNotEqual(created, self.structure)
        self.assertEqual(created.company_id, self.company)
        self.assertEqual(created.name, "Management P&L")
        self.assertEqual(len(created.line_ids), 3)
        # Opening it again reuses it.
        self.assertEqual(self.Structure.action_open_config()["res_id"], created.id)
