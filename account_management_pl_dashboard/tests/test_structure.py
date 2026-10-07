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
            "Sales", "Main customers",
            "Direct costs", "Staff", "Salaries", "Sales commissions",
            "Indirect costs", "Rent",
        ])

    def test_non_root_line_needs_parent(self):
        with self.assertRaises(ValidationError):
            self.Line.create({"structure_id": self.structure.id, "name": "Orphan"})

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

    def test_sales_account_cannot_be_cost(self):
        # With no explicit sales accounts, every Income account is a sales one.
        with self.assertRaisesRegex(ValidationError, "is a Sales account"):
            self.leaf_rent.account_ids = [Command.link(self.account_sales.id)]
        # An "Other income" account is not a sales account by default.
        self.leaf_rent.account_ids = [Command.set((self.account_rent | self.account_other_income).ids)]
        with self.assertRaisesRegex(ValidationError, "is a Sales account"):
            self.structure.sales_account_ids = [Command.set(self.account_other_income.ids)]

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

    def test_section_specific_assignments(self):
        with self.assertRaisesRegex(ValidationError, "belongs to Sales"):
            self.leaf_customers.account_ids = [Command.link(self.account_social.id)]
        with self.assertRaisesRegex(ValidationError, "is a cost line"):
            self.leaf_rent.partner_ids = [Command.link(self.customer_b.id)]

    def test_duplicate_customer(self):
        with self.assertRaisesRegex(ValidationError, "Customer A is already used in line Sales / Main customers"):
            self.Line.create({
                "structure_id": self.structure.id,
                "parent_id": self.root_income.id,
                "name": "Other customers",
                "partner_ids": [Command.set(self.customer_a.ids)],
            })

    def test_customer_must_be_commercial_entity(self):
        with self.assertRaisesRegex(ValidationError, "assign the company instead"):
            self.leaf_customers.partner_ids = [Command.link(self.customer_a_contact.id)]

    def test_duplicate_analytic_account(self):
        plan = self.env["account.analytic.plan"].create({"name": "Business units"})
        analytic = self.env["account.analytic.account"].create({"name": "Unit 1", "plan_id": plan.id})
        self.structure.write({"analytic_mode": "analytic", "analytic_plan_id": plan.id})
        leaf = self.Line.create({
            "structure_id": self.structure.id,
            "parent_id": self.root_income.id,
            "name": "Unit 1 sales",
            "analytic_account_ids": [Command.set(analytic.ids)],
        })
        with self.assertRaisesRegex(ValidationError, "already used in line Sales / Unit 1 sales"):
            self.Line.create({
                "structure_id": self.structure.id,
                "parent_id": self.root_income.id,
                "name": "Duplicate",
                "analytic_account_ids": [Command.set(analytic.ids)],
            })
        self.assertTrue(leaf.analytic_account_ids)

    def test_analytic_account_must_belong_to_plan(self):
        plan = self.env["account.analytic.plan"].create({"name": "Business units"})
        other_plan = self.env["account.analytic.plan"].create({"name": "Regions"})
        region = self.env["account.analytic.account"].create({"name": "North", "plan_id": other_plan.id})
        self.structure.write({"analytic_mode": "analytic", "analytic_plan_id": plan.id})
        with self.assertRaisesRegex(ValidationError, "doesn't belong to the analytic plan"):
            self.leaf_customers.write({
                "partner_ids": [Command.clear()],
                "analytic_account_ids": [Command.set(region.ids)],
            })

    def test_switching_sales_dimension_keeps_assignments(self):
        plan = self.env["account.analytic.plan"].create({"name": "Business units"})
        analytic = self.env["account.analytic.account"].create({"name": "Unit 1", "plan_id": plan.id})
        self.structure.write({"analytic_mode": "analytic", "analytic_plan_id": plan.id})
        self.leaf_customers.analytic_account_ids = [Command.set(analytic.ids)]
        self.structure.sales_dimension = "analytic"
        self.assertEqual(self.leaf_customers.partner_ids, self.customer_a)
        self.assertEqual(self.leaf_customers.analytic_account_ids, analytic)
        self.structure.sales_dimension = "partner"
        self.assertEqual(self.leaf_customers.analytic_account_ids, analytic)

    def test_sales_by_analytic_requires_analytic_usage(self):
        with self.assertRaises(ValidationError):
            self.structure.sales_dimension = "analytic"

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
        self.assertEqual(empty_sales.assignment_status, "Without customers")

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

    def test_budget_required_when_enabled(self):
        with self.assertRaises(ValidationError):
            self.structure.budget_enabled = True
        budget = self.env["account.report.budget"].create({"name": "Budget 2026", "company_id": self.company.id})
        self.structure.write({"budget_enabled": True, "budget_id": budget.id})
