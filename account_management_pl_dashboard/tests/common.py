from odoo import Command

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


class PlDashboardCommon(AccountTestInvoicingCommon):
    """Shared fixtures: a structure with a few leaves, cost accounts and
    customers, built on the standard accounting test company."""

    @classmethod
    def _setup_pl_company_data(cls):
        """Accounting data of the company the tests run in (overridable)."""
        return cls.company_data

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company_data_2 = cls.setup_other_company()
        cls.pl_company_data = cls._setup_pl_company_data()
        cls.company = cls.pl_company_data["company"]
        cls.env.user.write({
            "company_ids": [Command.link(cls.company.id)],
            "company_id": cls.company.id,
        })
        cls.env = cls.env(context=dict(cls.env.context, allowed_company_ids=[cls.company.id]))
        cls.env.user.group_ids += cls.env.ref("account_management_pl_dashboard.group_management_pl_manager")
        cls.Structure = cls.env["account.pl.structure"]
        cls.Line = cls.env["account.pl.structure.line"]

        cls.usd = cls.env.ref("base.USD")
        cls.eur = cls.env.ref("base.EUR")
        (cls.usd | cls.eur).active = True

        def make_account(code, name, account_type):
            return cls.env["account.account"].create({
                "code": code,
                "name": name,
                "account_type": account_type,
                "company_ids": [Command.link(cls.company.id)],
            })

        cls.account_sales = make_account("4.1.1.01.001", "Services sales", "income")
        cls.account_other_income = make_account("4.9.1.01.001", "Other income", "income_other")
        cls.account_salaries = make_account("5.1.2.01.010", "Salaries", "expense")
        cls.account_social = make_account("5.1.2.01.020", "Social charges", "expense")
        cls.account_commissions = make_account("5.2.1.01.070", "Sales commissions", "expense")
        cls.account_rent = make_account("5.3.1.01.001", "Rent", "expense")

        cls.customer_a = cls.env["res.partner"].create({"name": "Customer A", "is_company": True})
        cls.customer_a_contact = cls.env["res.partner"].create({
            "name": "Contact of A", "parent_id": cls.customer_a.id,
        })
        cls.customer_b = cls.env["res.partner"].create({"name": "Customer B", "is_company": True})

        cls.structure = cls.Structure.create({
            "name": "Management P&L",
            "company_id": cls.company.id,
            "secondary_currency_id": cls.usd.id if cls.company.currency_id != cls.usd else cls.eur.id,
        })
        cls.root_income, cls.root_direct, cls.root_indirect = (
            cls.structure.line_ids.filtered(lambda line, section=section: line.section == section)
            for section in ("income", "direct_cost", "indirect_cost")
        )
        cls.leaf_sales = cls.Line.create({
            "structure_id": cls.structure.id,
            "parent_id": cls.root_income.id,
            "name": "Services sales",
            "account_ids": [Command.set(cls.account_sales.ids)],
        })
        cls.group_staff = cls.Line.create({
            "structure_id": cls.structure.id,
            "parent_id": cls.root_direct.id,
            "name": "Staff",
        })
        cls.leaf_salaries = cls.Line.create({
            "structure_id": cls.structure.id,
            "parent_id": cls.group_staff.id,
            "name": "Salaries",
            "account_ids": [Command.set(cls.account_salaries.ids)],
        })
        cls.leaf_commissions = cls.Line.create({
            "structure_id": cls.structure.id,
            "parent_id": cls.root_direct.id,
            "name": "Sales commissions",
            "account_ids": [Command.set(cls.account_commissions.ids)],
        })
        cls.leaf_rent = cls.Line.create({
            "structure_id": cls.structure.id,
            "parent_id": cls.root_indirect.id,
            "name": "Rent",
            "account_ids": [Command.set(cls.account_rent.ids)],
        })
        cls.account_balancing = make_account("1.1.9.99.999", "Balancing account", "asset_current")
        cls.misc_journal = cls.pl_company_data["default_journal_misc"]
        cls.Dashboard = cls.env["account.pl.dashboard"]

    @classmethod
    def _entry(cls, date, lines, journal=None, post=True):
        """Create a journal entry with the given (account, amount, partner)
        lines (amount > 0 = debit, in company currency), optionally followed
        by (currency, amount_currency) and/or an {analytic account: %}
        distribution, balanced against a balance sheet account in company
        currency.
        """
        line_vals = []
        total = 0.0
        for account, amount, partner, *extra in lines:
            distribution = extra.pop() if extra and isinstance(extra[-1], dict) else None
            foreign = extra
            total += amount
            vals = {
                "account_id": account.id,
                "partner_id": partner.id if partner else False,
                "debit": amount if amount > 0 else 0.0,
                "credit": -amount if amount < 0 else 0.0,
            }
            if foreign:
                # (currency, amount_currency): a journal item in a foreign currency.
                vals.update(currency_id=foreign[0].id, amount_currency=foreign[1])
            if distribution:
                # {analytic account: percentage}
                vals["analytic_distribution"] = {str(analytic.id): pct for analytic, pct in distribution.items()}
            line_vals.append(Command.create(vals))
        line_vals.append(Command.create({
            "account_id": cls.account_balancing.id,
            "debit": -total if total < 0 else 0.0,
            "credit": total if total > 0 else 0.0,
        }))
        move = cls.env["account.move"].create({
            "move_type": "entry",
            "date": date,
            "journal_id": (journal or cls.misc_journal).id,
            "line_ids": line_vals,
        })
        if post:
            move.action_post()
        return move

    def _data(self, period="fiscal_year", **kwargs):
        return self.Dashboard.get_dashboard_data(period=period, **kwargs)

    @staticmethod
    def _row(data, key):
        return next((row for row in data["rows"] if row["key"] == key), None)

    def _line_row(self, data, line):
        return self._row(data, "line-%d" % line.id)


class PlDashboardAnalyticMixin:
    """Analytic fixtures: a plan with two business units, for the toolbar's
    analytic filter."""

    @classmethod
    def _setup_analytics(cls):
        cls.plan = cls.env["account.analytic.plan"].create({"name": "Business units"})
        cls.unit_1, cls.unit_2 = cls.env["account.analytic.account"].create([
            {"name": "Unit 1", "plan_id": cls.plan.id, "company_id": cls.company.id},
            {"name": "Unit 2", "plan_id": cls.plan.id, "company_id": cls.company.id},
        ])



class PlDashboardArsCommon(PlDashboardCommon):
    """Same fixtures in an Argentine-peso company, so that USD can be the
    secondary currency (the standard test company is in USD)."""

    @classmethod
    def _setup_pl_company_data(cls):
        ars = cls.env.ref("base.ARS")
        ars.active = True
        return cls.setup_other_company(name="AR company", currency_id=ars.id)

    @classmethod
    def _rate(cls, currency, date, company_units):
        """Rate of ``currency`` on ``date``, given as company-currency units
        per unit of ``currency`` (e.g. 1000 ARS per USD)."""
        return cls.env["res.currency.rate"].create({
            "currency_id": currency.id,
            "name": date,
            "rate": 1.0 / company_units,
            "company_id": cls.company.id,
        })

    @classmethod
    def _invoice(cls, date, amount, currency, partner, move_type="out_invoice", account=None, distribution=None):
        move = cls.env["account.move"].create({
            "move_type": move_type,
            "partner_id": partner.id,
            "invoice_date": date,
            "date": date,
            "currency_id": currency.id,
            "invoice_line_ids": [Command.create({
                "name": "Service",
                "account_id": (account or cls.account_sales).id,
                "quantity": 1,
                "price_unit": amount,
                "tax_ids": [Command.clear()],
                "analytic_distribution": distribution and {
                    str(analytic.id): pct for analytic, pct in distribution.items()
                },
            })],
        })
        move.action_post()
        return move
