"""Demo data for the management P&L dashboard.

NOT part of the module (not listed in the manifest): it is never installed
with the module. Run it by hand against a test database only:

    ./odoo-bin shell -c <config> -d <test_db> --addons-path=<...> \
        < account_management_pl_dashboard/scripts/load_demo_data.py

It creates a separate company "Management P&L demo" (Argentine pesos, fiscal
year closing on June 30) with its own chart of accounts, customers,
analytic accounts, daily USD rates, two fiscal years of posted journal
entries (peso and USD invoices, a USD credit note, a USD invoice paid later
so that Odoo books a real exchange difference), a management P&L structure
and an accounting budget (by account and month). The admin user gets access to the company and to
the dashboard's Administrator group. Running it twice does nothing the
second time (and resumes a run interrupted after the chart of accounts was
loaded).
"""
import random
from datetime import date, timedelta

from dateutil.relativedelta import relativedelta

from odoo import Command, fields

COMPANY_NAME = "Management P&L demo"


def load(env):
    company = env["res.company"].search([("name", "=", COMPANY_NAME)], limit=1)
    structure = company and env["account.pl.structure"].with_context(active_test=False).search(
        [("company_id", "=", company.id)], limit=1,
    )
    if structure:
        if structure.budget_id:
            print("Demo data already loaded, nothing to do.")
        else:
            # Demo loaded by an earlier version of this script: add the budget.
            load_budget(env(context=dict(env.context, allowed_company_ids=[company.id])), structure)
            env.cr.commit()
            print("Budget added to the existing demo data.")
        return

    random.seed(42)
    admin = env.ref("base.user_admin")
    ars = env.ref("base.ARS")
    usd = env.ref("base.USD")
    (ars | usd).active = True

    # The chart of accounts loading commits, so a failed earlier run may have
    # left the company behind: reuse it.
    company = company or env["res.company"].create({"name": COMPANY_NAME})
    company.write({
        "currency_id": ars.id,
        "country_id": False,
        "fiscalyear_last_month": "6",
        "fiscalyear_last_day": 30,
    })
    admin.write({"company_ids": [Command.link(company.id)]})
    admin.group_ids += env.ref("account_management_pl_dashboard.group_management_pl_manager")
    # Data loading runs as the shell's superuser, in the demo company.
    env = env(context=dict(env.context, allowed_company_ids=[company.id]))
    if not company.chart_template:
        env["account.chart.template"].try_loading("generic_coa", company=company, install_demo=False)
    # The generic chart of accounts sets its own currency: back to pesos
    # (allowed as long as the company has no journal entries yet).
    company.currency_id = ars
    # Databases with l10n_latam_invoice_document installed would otherwise
    # require a document type on every demo invoice.
    journals = env["account.journal"].search([("company_id", "=", company.id)])
    if "l10n_latam_use_documents" in journals._fields:
        journals.l10n_latam_use_documents = False

    today = fields.Date.context_today(env["res.users"])
    first_day = date(today.year - 2 if today.month < 7 else today.year - 1, 7, 1)

    # Daily USD rates (business days only), from about 900 to 1450 ARS.
    days = (today - first_day).days
    rates = []
    for offset in range(days + 1):
        day = first_day + timedelta(days=offset)
        if day.weekday() < 5:
            ars_per_usd = 900 + 550 * offset / max(days, 1) + random.uniform(-8, 8)
            rates.append({"currency_id": usd.id, "name": day, "rate": 1 / ars_per_usd, "company_id": company.id})
    env["res.currency.rate"].create(rates)

    def account(code, name, account_type):
        return env["account.account"].create({
            "code": code, "name": name, "account_type": account_type,
            "company_ids": [Command.link(company.id)],
        })

    accounts = {
        "sales_services": account("4.1.1.01.001", "Ventas de servicios", "income"),
        "sales_licenses": account("4.1.1.01.002", "Ventas de licencias", "income"),
        "salaries": account("5.1.2.01.010", "Sueldos", "expense_direct_cost"),
        "salaries_extra": account("5.1.2.01.011", "Horas extra", "expense_direct_cost"),
        "social": account("5.1.2.01.020", "Cargas sociales", "expense_direct_cost"),
        "fees": account("5.1.3.01.001", "Honorarios", "expense_direct_cost"),
        "it": account("5.1.4.01.001", "Infraestructura IT", "expense_direct_cost"),
        "iibb": account("5.1.5.01.001", "IIBB", "expense"),
        "check_tax": account("5.1.5.01.002", "Impuesto al cheque", "expense"),
        "commissions": account("5.2.1.01.070", "Comisiones comerciales", "expense"),
        "rent": account("5.3.1.01.001", "Alquileres", "expense"),
        "admin": account("5.3.1.01.002", "Gastos administrativos", "expense"),
        "bank_fees": account("5.3.2.01.001", "Gastos bancarios", "expense"),
        # Not assigned to any line on purpose: shows the "Unassigned" row.
        "donations": account("5.9.1.01.001", "Donaciones", "expense_other"),
    }
    exchange_gain = company.income_currency_exchange_account_id
    exchange_loss = company.expense_currency_exchange_account_id

    partners = env["res.partner"].create([
        {"name": "Acme Argentina SA", "is_company": True},
        {"name": "Globex SRL", "is_company": True},
        {"name": "Initech LLC", "is_company": True},
        {"name": "Umbrella SA", "is_company": True},
        {"name": "Cliente ocasional", "is_company": True},
    ])
    acme, globex, initech, umbrella, occasional = partners
    acme_contact = env["res.partner"].create({"name": "Compras Acme", "parent_id": acme.id})

    plan = env["account.analytic.plan"].create({"name": "Unidades de negocio"})
    unit_consulting, unit_software = env["account.analytic.account"].create([
        {"name": "Consultoría", "plan_id": plan.id, "company_id": company.id},
        {"name": "Software", "plan_id": plan.id, "company_id": company.id},
    ])

    closing_journal = env["account.journal"].create({
        "name": "Cierre de ejercicio", "code": "CIE", "type": "general", "company_id": company.id,
    })
    misc_journal = env["account.journal"].search([("type", "=", "general"), ("company_id", "=", company.id),
                                                  ("id", "!=", closing_journal.id)], limit=1)
    bank_journal = env["account.journal"].search([("type", "=", "bank"), ("company_id", "=", company.id)], limit=1)
    balancing = env["account.account"].search([
        ("account_type", "=", "liability_current"), ("company_ids", "in", company.id),
    ], limit=1)

    def entry(day, lines, journal=misc_journal):
        lines = [(account_record, round(amount, 2), *rest) for account_record, amount, *rest in lines]
        total = round(sum(amount for _account, amount, *_rest in lines), 2)
        line_vals = []
        for account_record, amount, *rest in lines:
            vals = {"account_id": account_record.id, "debit": max(amount, 0), "credit": max(-amount, 0)}
            if rest:
                vals["analytic_distribution"] = rest[0]
            line_vals.append(Command.create(vals))
        line_vals.append(Command.create({
            "account_id": balancing.id, "debit": max(-total, 0), "credit": max(total, 0),
        }))
        move = env["account.move"].create({
            "move_type": "entry", "date": day, "journal_id": journal.id, "line_ids": line_vals,
        })
        move.action_post()
        return move

    def invoice(day, partner, currency, amounts, move_type="out_invoice"):
        move = env["account.move"].create({
            "move_type": move_type,
            "partner_id": partner.id,
            "invoice_date": day,
            "date": day,
            "currency_id": currency.id,
            "invoice_line_ids": [
                Command.create({
                    "name": "Servicios",
                    "account_id": account_record.id,
                    "quantity": 1,
                    "price_unit": round(amount, 2),
                    "tax_ids": [Command.clear()],
                    "analytic_distribution": distribution,
                })
                for account_record, amount, distribution in amounts
            ],
        })
        move.action_post()
        return move

    month = first_day
    growth = 1.0
    while month <= today:
        day = min(month + relativedelta(day=15), today)
        last_day = min(month + relativedelta(day=31), today)
        growth *= 1.04  # inflation in pesos
        consulting = {str(unit_consulting.id): 70.0, str(unit_software.id): 30.0}
        software = {str(unit_software.id): 100.0}

        entry(day, [
            (accounts["salaries"], 9_000_000 * growth, consulting),
            (accounts["salaries_extra"], 450_000 * growth, consulting),
            (accounts["social"], 2_400_000 * growth),
            (accounts["fees"], 800_000 * growth),
            (accounts["it"], 650_000 * growth, software),
            (accounts["iibb"], 520_000 * growth),
            (accounts["check_tax"], 180_000 * growth),
            (accounts["commissions"], 600_000 * growth),
            (accounts["rent"], 1_100_000 * growth),
            (accounts["admin"], 300_000 * growth),
            (accounts["bank_fees"], 90_000 * growth),
        ])
        if month.month % 4 == 0:
            entry(day, [(accounts["donations"], 150_000 * growth)])

        invoice(day, acme_contact, ars, [(accounts["sales_services"], 9_500_000 * growth, consulting)])
        invoice(day, globex, ars, [(accounts["sales_services"], 4_200_000 * growth, consulting)])
        invoice(day, initech, usd, [(accounts["sales_licenses"], 6_500.0, software)])
        invoice(last_day, umbrella, usd, [(accounts["sales_services"], 3_200.0, consulting)])
        invoice(day, occasional, ars, [(accounts["sales_services"], 350_000 * growth, None)])

        month += relativedelta(months=1)

    # A USD credit note.
    invoice(today.replace(day=1), initech, usd, [(accounts["sales_licenses"], 800.0, software)], "out_refund")

    # A USD invoice paid two months later: Odoo books the exchange difference.
    paid_invoice = invoice(today - relativedelta(months=3), umbrella, usd,
                           [(accounts["sales_services"], 5_000.0, consulting)])
    env["account.payment.register"].with_context(
        active_model="account.move", active_ids=paid_invoice.ids,
    ).create({
        "payment_date": today - relativedelta(months=1),
        "journal_id": bank_journal.id,
    })._create_payments()

    # A year-end closing entry of the previous fiscal year, in the excluded
    # journal: without excluding it, it would empty June's column.
    fiscal_year_end = company.compute_fiscalyear_dates(today)["date_from"] - timedelta(days=1)
    entry(fiscal_year_end, [(accounts["salaries"], -5_000_000.0)], journal=closing_journal)

    # Management P&L structure.
    structure = env["account.pl.structure"].create({
        "name": "Estado de resultados de gestión",
        "company_id": company.id,
        "sales_account_ids": [Command.set((accounts["sales_services"] | accounts["sales_licenses"]).ids)],
        "excluded_journal_ids": [Command.set(closing_journal.ids)],
        "analytic_mode": "analytic",
        "analytic_plan_id": plan.id,
        "secondary_currency_id": usd.id,
    })
    roots = {line.section: line for line in structure.line_ids}
    Line = env["account.pl.structure.line"]

    def line(parent, name, sequence, **assignments):
        return Line.create({
            "structure_id": structure.id, "parent_id": parent.id, "name": name, "sequence": sequence,
            **{field: [Command.set(records.ids)] for field, records in assignments.items()},
        })

    line(roots["income"], "Clientes corporativos", 10,
         partner_ids=acme | globex | umbrella, analytic_account_ids=unit_consulting)
    line(roots["income"], "Licencias", 20, partner_ids=initech, analytic_account_ids=unit_software)
    line(roots["income"], "Otros clientes", 30)

    staff = line(roots["direct_cost"], "Personal", 10)
    line(staff, "Sueldos", 10, account_ids=accounts["salaries"] | accounts["salaries_extra"])
    line(staff, "Cargas sociales", 20, account_ids=accounts["social"])
    line(roots["direct_cost"], "Honorarios", 20, account_ids=accounts["fees"])
    line(roots["direct_cost"], "Infraestructura IT", 30, account_ids=accounts["it"])
    taxes = line(roots["direct_cost"], "Impuestos", 40)
    line(taxes, "IIBB", 10, account_ids=accounts["iibb"])
    line(taxes, "Impuesto al cheque", 20, account_ids=accounts["check_tax"])
    line(roots["direct_cost"], "Comisiones comerciales", 50, account_ids=accounts["commissions"])

    line(roots["indirect_cost"], "Alquileres", 10, account_ids=accounts["rent"])
    line(roots["indirect_cost"], "Gastos administrativos", 20, account_ids=accounts["admin"] | accounts["bank_fees"])
    line(roots["indirect_cost"], "Diferencias de cambio", 30, account_ids=exchange_gain | exchange_loss)
    line(roots["indirect_cost"], "Incentivos no remunerativos", 40)

    load_budget(env, structure)
    env.cr.commit()
    print("Demo data loaded: company %r (id %s), structure id %s." % (company.name, company.id, structure.id))


def load_budget(env, structure):
    """Accounting budget (by account and month, like the ones created from
    the Profit and Loss report) for the current and previous fiscal years:
    the actual figures of each month, +/- 15%, so that the dashboard shows
    favorable and unfavorable deviations. Sales are budgeted at the
    section level only, as Odoo budgets are by account."""
    random.seed(7)
    company = structure.company_id
    today = fields.Date.context_today(env["res.users"])
    previous_start = company.compute_fiscalyear_dates(
        company.compute_fiscalyear_dates(today)["date_from"] - timedelta(days=1)
    )["date_from"]
    fiscal_year_end = company.compute_fiscalyear_dates(today)["date_to"]
    accounts = structure.line_ids.account_ids | structure.sales_account_ids
    actuals = dict(
        ((account.id, month), balance)
        for account, month, balance in env["account.move.line"]._read_group(
            [
                ("company_id", "=", company.id),
                ("parent_state", "=", "posted"),
                ("account_id", "in", accounts.ids),
                ("journal_id", "not in", structure.excluded_journal_ids.ids),
                ("date", ">=", previous_start),
            ],
            groupby=["account_id", "date:month"],
            aggregates=["balance:sum"],
        )
    )
    items = []
    month = previous_start
    while month <= fiscal_year_end:
        for account in accounts:
            # Future months: continue the last known month's figures.
            reference = actuals.get((account.id, month)) or actuals.get(
                (account.id, min(month, today.replace(day=1)))
            )
            if reference:
                items.append(Command.create({
                    "account_id": account.id,
                    "date": month,
                    "amount": round(reference * random.uniform(0.85, 1.15), 2),
                }))
        month += relativedelta(months=1)
    budget = env["account.report.budget"].create({
        "name": "Presupuesto de gestión", "company_id": company.id, "item_ids": items,
    })
    structure.write({"budget_enabled": True, "budget_id": budget.id})


load(env)  # noqa: F821 - `env` is provided by odoo-bin shell
