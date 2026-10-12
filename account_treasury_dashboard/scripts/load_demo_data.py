"""Demo data for the treasury dashboard.

NOT part of the module (not listed in the manifest): it is never installed
with the module. Run it by hand against a test database only:

    ./odoo-bin shell -c <config> -d <test_db> --addons-path=<...> \
        < account_treasury_dashboard/scripts/load_demo_data.py

It creates a separate company "Treasury dashboard demo" (Argentine pesos)
with the generic chart of accounts, daily USD rates, and:

- banks "Banco Galicia" (pesos, with its own outstanding receipts/payments
  accounts) and "Banco Nación USD" (dollars, booked at older rates), a
  cash journal, a petty cash fund, a prepaid card without journal, a VISA
  credit card and a dollar investment fund;
- a bank statement, statement lines without statement and unreconciled
  lines of different ages, payments in transit, one matched payment;
- customer invoices and vendor bills with varied due dates (overdue
  included), one invoice already paid but not in the bank yet;
- credit card purchases in the closed and in the current cycle;
- salaries payable (an account that can't be reconciled) and taxes
  payable (one that can), as projection commitments;
- internal transfers (bank to petty cash, bank to cash);
- the dashboard's configuration, and the Administrator group for admin.

Dates are relative to the day it runs. Running it twice does nothing the
second time.
"""
import random
from datetime import timedelta

from odoo import Command, fields

COMPANY_NAME = "Treasury dashboard demo"


def load(env):
    if env["res.company"].search_count([("name", "=", COMPANY_NAME)]):
        print("Demo data already loaded, nothing to do.")
        return
    random.seed(7)
    admin = env.ref("base.user_admin")
    ars = env.ref("base.ARS")
    usd = env.ref("base.USD")
    (ars | usd).active = True

    company = env["res.company"].create({"name": COMPANY_NAME, "currency_id": ars.id})
    admin.write({"company_ids": [Command.link(company.id)]})
    admin.group_ids += env.ref("account_treasury_dashboard.group_treasury_dashboard_manager")
    env = env(context=dict(env.context, allowed_company_ids=[company.id]))
    env["account.chart.template"].try_loading("generic_coa", company=company, install_demo=False)
    company.currency_id = ars
    journals = env["account.journal"].search([("company_id", "=", company.id)])
    if "l10n_latam_use_documents" in journals._fields:
        journals.l10n_latam_use_documents = False

    today = fields.Date.context_today(env["res.users"])

    def day(offset):
        return today + timedelta(days=offset)

    # Daily USD rates (business days), around 1,450 ARS; none on weekends.
    rates = []
    for offset in range(-120, 1):
        rate_day = day(offset)
        if rate_day.weekday() < 5:
            ars_per_usd = 1450 + offset * 1.5 + random.uniform(-5, 5)
            rates.append({"currency_id": usd.id, "name": rate_day, "rate": 1 / ars_per_usd,
                          "company_id": company.id})
    env["res.currency.rate"].create(rates)

    def account(code, name, account_type, reconcile=False, currency=None):
        return env["account.account"].create({
            "code": code, "name": name, "account_type": account_type, "reconcile": reconcile,
            "currency_id": currency.id if currency else False,
            "company_ids": [Command.link(company.id)],
        })

    def journal(name, code, journal_type, currency=None, default_account=None):
        values = {"name": name, "code": code, "type": journal_type, "company_id": company.id,
                  "currency_id": currency.id if currency else False}
        if default_account:
            values["default_account_id"] = default_account.id
        return env["account.journal"].create(values)

    capital = account("3.1.1.01", "Capital", "equity")
    sales = account("4.1.1.01", "Ventas", "income")
    expenses = account("5.3.1.01", "Gastos generales", "expense")
    salaries_expense = account("5.1.2.01", "Sueldos", "expense")
    taxes_expense = account("5.1.5.01", "Impuestos", "expense")
    salaries_payable = account("2.1.4.01", "Sueldos a pagar", "liability_current")
    taxes_payable = account("2.1.5.01", "Impuestos a pagar", "liability_current", reconcile=True)
    prepaid_account = account("1.1.9.01", "Tarjeta prepaga", "asset_current")
    misc = env["account.journal"].search([("company_id", "=", company.id), ("type", "=", "general")], limit=1)

    galicia = journal("Banco Galicia", "BGAL", "bank")
    receipts_account = account("1.1.8.01", "Cobros pendientes Galicia", "asset_current", reconcile=True)
    payments_account = account("1.1.8.02", "Pagos pendientes Galicia", "asset_current", reconcile=True)
    galicia.inbound_payment_method_line_ids.payment_account_id = receipts_account
    galicia.outbound_payment_method_line_ids.payment_account_id = payments_account
    nacion_usd = journal("Banco Nación USD", "BNUS", "bank", currency=usd)
    cash = journal("Caja", "CAJ", "cash")
    petty = journal("Fondo fijo administración", "FFA", "cash")
    visa = journal("Tarjeta VISA", "VISA", "credit")
    fund_account = account("1.2.1.01", "FCI dólares", "asset_current", currency=usd)
    fund = journal("FCI dólares", "FCI", "general", currency=usd, default_account=fund_account)

    def entry(date, lines, ref):
        move = env["account.move"].create({
            "move_type": "entry", "date": date, "ref": ref, "journal_id": misc.id,
            "line_ids": [Command.create({"account_id": acc.id, "balance": balance, "name": ref, **extra})
                         for acc, balance, extra in lines],
        })
        move.action_post()
        return move

    def st_line(bank_journal, date, amount, label, statement=None):
        return env["account.bank.statement.line"].create({
            "journal_id": bank_journal.id, "date": date, "amount": amount, "payment_ref": label,
            "statement_id": statement.id if statement else False,
        })

    def partner(name):
        return env["res.partner"].create({"name": name, "company_id": company.id})

    customers = [partner(name) for name in ("Distribuidora Norte", "Comercial Sur", "Servicios Andinos")]
    vendors = [partner(name) for name in ("Papelera del Plata", "Logística Federal", "Energía Cuyo")]
    tax_office = partner("ARCA")

    # Opening balances.
    st_lines = [st_line(galicia, day(-45), 25_000_000, "Saldo inicial")]
    st_lines += [st_line(galicia, day(-30 + index * 3), random.choice([1, -1]) * random.randint(200_000, 1_500_000),
                         "Movimiento %s" % (index + 1)) for index in range(6)]
    # Without a PDF of the statement (account_accountant would render one,
    # which needs wkhtmltopdf).
    statement = env["account.bank.statement"].with_context(skip_pdf_attachment_generation=True).create({
        "journal_id": galicia.id, "name": "Extracto Galicia", "line_ids": [Command.set([line.id for line in st_lines])],
    })
    statement.balance_end_real = statement.balance_end
    # Lines after the statement (without statement), some of them old: the
    # reconciliation section ages them.
    for offset, amount, label in ((-75, 120_000, "Transferencia recibida"), (-40, -85_000, "Débito servicio"),
                                  (-12, 340_000, "Depósito"), (-5, -60_000, "Comisión bancaria"),
                                  (-2, 410_000, "Transferencia recibida")):
        st_line(galicia, day(offset), amount, label)
    entry(day(-60), [
        (nacion_usd.default_account_id, 1250 * 20_000, {"currency_id": usd.id, "amount_currency": 20_000}),
        (capital, -1250 * 20_000, {}),
    ], "Aporte en dólares")
    entry(day(-50), [
        (fund_account, 1300 * 50_000, {"currency_id": usd.id, "amount_currency": 50_000}),
        (capital, -1300 * 50_000, {}),
    ], "Suscripción FCI")
    entry(day(-40), [(cash.default_account_id, 800_000, {}), (capital, -800_000, {})], "Saldo inicial caja")

    # Internal transfers: bank to petty cash (refill) and bank to cash.
    transfer_account = company.transfer_account_id
    entry(day(-8), [(petty.default_account_id, 150_000, {}), (galicia.default_account_id, -150_000, {})],
          "Reposición fondo fijo")
    entry(day(-6), [(transfer_account, 200_000, {}), (galicia.default_account_id, -200_000, {})],
          "Transferencia a caja (salida)")
    entry(day(-6), [(cash.default_account_id, 200_000, {}), (transfer_account, -200_000, {})],
          "Transferencia a caja (entrada)")
    entry(day(-3), [(expenses, 38_000, {}), (petty.default_account_id, -38_000, {})], "Gastos fondo fijo")
    entry(day(-20), [(prepaid_account, 300_000, {}), (galicia.default_account_id, -300_000, {})],
          "Carga tarjeta prepaga")
    entry(day(-4), [(expenses, 45_000, {}), (prepaid_account, -45_000, {})], "Consumo prepaga")

    # Invoices and bills with varied due dates.
    def invoice(move_type, partner_record, amount, due_offset, date_offset=None):
        move = env["account.move"].create({
            "move_type": move_type, "partner_id": partner_record.id,
            "invoice_date": day(date_offset if date_offset is not None else due_offset - 30),
            "invoice_date_due": day(due_offset),
            "invoice_line_ids": [Command.create({
                "name": "Servicios", "quantity": 1, "price_unit": amount,
                "account_id": (sales if move_type == "out_invoice" else expenses).id, "tax_ids": [Command.clear()],
            })],
        })
        move.action_post()
        return move

    for index, (due_offset, amount) in enumerate(((-20, 900_000), (-5, 450_000), (3, 1_200_000), (9, 700_000),
                                                   (16, 2_100_000), (24, 850_000), (33, 1_500_000))):
        invoice("out_invoice", customers[index % 3], amount, due_offset)
    for index, (due_offset, amount) in enumerate(((-10, 600_000), (2, 1_800_000), (6, 950_000), (13, 3_200_000),
                                                   (20, 1_100_000), (29, 2_400_000))):
        invoice("in_invoice", vendors[index % 3], amount, due_offset)

    def payment(payment_type, partner_record, amount, date):
        record = env["account.payment"].create({
            "journal_id": galicia.id, "payment_type": payment_type,
            "partner_type": "customer" if payment_type == "inbound" else "supplier",
            "partner_id": partner_record.id, "amount": amount, "date": date,
        })
        record.action_post()
        return record

    # A paid invoice whose payment isn't in the bank yet: in transit only.
    paid_invoice = invoice("out_invoice", customers[0], 520_000, 12)
    paid = payment("inbound", customers[0], 520_000, day(-1))
    (paid_invoice.line_ids | paid.move_id.line_ids).filtered(
        lambda line: line.account_id.account_type == "asset_receivable").reconcile()
    payment("outbound", vendors[1], 275_000, day(-1))
    # A payment already matched with a statement line.
    matched = payment("inbound", customers[2], 340_000, day(-13))
    matched_st_line = st_line(galicia, day(-11), 340_000, "Cobro Servicios Andinos")
    _liquidity, suspense, _other = matched_st_line._seek_for_lines()
    outstanding = matched.move_id.line_ids.filtered(lambda line: line.account_id == matched.outstanding_account_id)
    matched_st_line.move_id.with_context(skip_readonly_check=True).write({"line_ids": [
        Command.update(suspense.id, {"account_id": outstanding.account_id.id, "partner_id": customers[2].id}),
    ]})
    (matched_st_line.move_id.line_ids.filtered(lambda line: line.account_id == outstanding.account_id)
     | outstanding).reconcile()

    # Credit card: closes on the 5th, due on the 15th.
    for offset, amount, label in ((-35, 180_000, "Combustible"), (-28, 95_000, "Software"),
                                  (-6, 140_000, "Pasajes"), (-1, 60_000, "Hotel")):
        entry(day(offset), [(expenses, amount, {}), (visa.default_account_id, -amount, {})], label)

    # Liabilities for the projection.
    entry(day(-10), [(salaries_expense, 4_300_000, {}), (salaries_payable, -4_300_000, {})], "Sueldos del mes")
    entry(day(-9), [(taxes_expense, 780_000, {}),
                    (taxes_payable, -780_000, {"partner_id": tax_office.id, "date_maturity": day(11)})],
          "IIBB a pagar")

    config = env["account.treasury.config"].create({"company_id": company.id})
    Medium = env["account.treasury.medium"]
    Medium.create([
        {"config_id": config.id, "sequence": 1, "name": "Banco Galicia", "kind": "bank", "journal_id": galicia.id},
        {"config_id": config.id, "sequence": 2, "name": "Banco Nación USD", "kind": "bank",
         "journal_id": nacion_usd.id, "stale_days": 10},
        {"config_id": config.id, "sequence": 3, "name": "Caja", "kind": "cash", "journal_id": cash.id},
        {"config_id": config.id, "sequence": 4, "name": "Fondo fijo administración", "kind": "petty_cash",
         "journal_id": petty.id},
        {"config_id": config.id, "sequence": 5, "name": "Tarjeta prepaga", "kind": "prepaid",
         "account_ids": [Command.set(prepaid_account.ids)]},
        {"config_id": config.id, "sequence": 6, "name": "VISA corporativa", "kind": "credit_card",
         "journal_id": visa.id, "closing_day": 5, "due_day": 15, "credit_limit": 3_000_000},
        {"config_id": config.id, "sequence": 7, "name": "FCI dólares", "kind": "investment", "journal_id": fund.id},
    ])
    env["account.treasury.commitment"].create([
        {"config_id": config.id, "name": "Sueldos", "kind": "payroll",
         "account_ids": [Command.set(salaries_payable.ids)], "payment_day": 5},
        {"config_id": config.id, "name": "Impuestos", "kind": "tax",
         "account_ids": [Command.set(taxes_payable.ids)]},
    ])
    env.cr.commit()
    print("Treasury dashboard demo loaded in company %r (switch to it to see the dashboard)." % COMPANY_NAME)


load(env)  # noqa: F821 - `env` is provided by odoo-bin shell
