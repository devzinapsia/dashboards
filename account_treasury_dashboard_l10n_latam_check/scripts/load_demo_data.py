"""Checks demo data for the treasury dashboard.

NOT part of the module (not listed in the manifest): it is never installed
with the module. Run it by hand against a test database only, after the
treasury dashboard's own demo script
(account_treasury_dashboard/scripts/load_demo_data.py):

    ./odoo-bin shell -c <config> -d <test_db> --addons-path=<...> \
        < account_treasury_dashboard_l10n_latam_check/scripts/load_demo_data.py

In the company "Treasury dashboard demo" it creates a third-party checks
journal and a rejected checks journal (configured in the treasury
settings), an own checks payment method on Banco Galicia, and:

- third-party checks in portfolio with payment dates from overdue to
  two months ahead;
- two checks deposited in Banco Galicia, not credited yet;
- one rejected check;
- own deferred checks pending debit.

Dates are relative to the day it runs. Running it twice does nothing the
second time.
"""
from datetime import timedelta

from odoo import Command, fields

COMPANY_NAME = "Treasury dashboard demo"


def load(env):
    company = env["res.company"].search([("name", "=", COMPANY_NAME)], limit=1)
    if not company:
        print("Load the treasury dashboard demo data first.")
        return
    env = env(context=dict(env.context, allowed_company_ids=[company.id]))
    if env["account.journal"].search_count([("company_id", "=", company.id), ("code", "=", "CHT")]):
        print("Checks demo data already loaded, nothing to do.")
        return
    ref = env.ref
    today = fields.Date.context_today(env["res.users"])

    def account(code, name):
        return env["account.account"].create({
            "code": code, "name": name, "account_type": "asset_current", "reconcile": True,
            "company_ids": [Command.link(company.id)],
        })

    checks_account = account("1.1.1.02.003", "Valores a depositar")
    deferred_account = account("1.1.1.02.004", "Cheques diferidos a pagar")

    def check_journal(name, code):
        journal = env["account.journal"].create({"name": name, "code": code, "type": "cash", "company_id": company.id})
        journal.inbound_payment_method_line_ids = [
            Command.create({"payment_method_id": ref(method).id, "name": label, "payment_account_id": checks_account.id})
            for method, label in (("l10n_latam_check.account_payment_method_new_third_party_checks", "Cheques nuevos"),
                                  ("l10n_latam_check.account_payment_method_in_third_party_checks", "Cheques existentes"))
        ]
        journal.outbound_payment_method_line_ids = [Command.create({
            "payment_method_id": ref("l10n_latam_check.account_payment_method_out_third_party_checks").id,
            "name": "Cheques existentes", "payment_account_id": checks_account.id,
        })]
        return journal

    portfolio = check_journal("Cheques de terceros", "CHT")
    rejected = check_journal("Cheques rechazados", "CHR")
    galicia = env["account.journal"].search([("company_id", "=", company.id), ("code", "=", "BGAL")])
    galicia.outbound_payment_method_line_ids = [Command.create({
        "payment_method_id": ref("l10n_latam_check.account_payment_method_own_checks").id,
        "name": "Cheques propios", "payment_account_id": deferred_account.id,
    })]
    config = env["account.treasury.config"].search([("company_id", "=", company.id)])
    config.write({
        "third_party_check_journal_ids": [Command.set(portfolio.ids)],
        "rejected_check_journal_ids": [Command.set(rejected.ids)],
    })

    customers = env["res.partner"].search([("company_id", "=", company.id),
                                           ("name", "in", ("Distribuidora Norte", "Comercial Sur"))])
    vendor = env["res.partner"].search([("company_id", "=", company.id), ("name", "=", "Logística Federal")], limit=1)
    method = portfolio.inbound_payment_method_line_ids.filtered(lambda line: line.code == "new_third_party_checks")[:1]
    received = env["l10n_latam.check"]
    for customer, checks in zip(customers, (
        [("10000101", -4, 180_000), ("10000102", 2, 320_000), ("10000103", 9, 450_000), ("10000104", 26, 610_000)],
        [("20000201", 0, 95_000), ("20000202", 17, 700_000), ("20000203", 45, 380_000), ("20000204", 12, 260_000),
         ("20000205", 6, 150_000)],
    )):
        payment = env["account.payment"].create({
            "partner_id": customer.id, "payment_type": "inbound", "partner_type": "customer",
            "journal_id": portfolio.id, "date": today - timedelta(days=3), "payment_method_line_id": method.id,
            "l10n_latam_new_check_ids": [Command.create({
                "name": number, "payment_date": today + timedelta(days=days), "amount": amount,
            }) for number, days, amount in checks],
        })
        payment.action_post()
        received |= payment.l10n_latam_new_check_ids

    def transfer(checks, journal):
        env["l10n_latam.payment.mass.transfer"].with_context(
            active_model="l10n_latam.check", active_ids=checks.ids,
        ).create({"destination_journal_id": journal.id, "payment_date": today - timedelta(days=1)})._create_payments()

    transfer(received.filtered(lambda check: check.name in ("20000204", "10000102")), galicia)
    transfer(received.filtered(lambda check: check.name == "20000205"), rejected)

    own_method = galicia.outbound_payment_method_line_ids.filtered(
        lambda line: line.code == "own_checks" and line.payment_account_id == deferred_account)[:1]
    own = env["account.payment"].create({
        "partner_id": vendor.id, "payment_type": "outbound", "partner_type": "supplier", "journal_id": galicia.id,
        "date": today - timedelta(days=2), "payment_method_line_id": own_method.id,
        "l10n_latam_new_check_ids": [Command.create({
            "name": number, "payment_date": today + timedelta(days=days), "amount": amount,
        }) for number, days, amount in (("00005001", 8, 540_000), ("00005002", 23, 540_000), ("00005003", 38, 540_000))],
    })
    own.action_post()
    env.cr.commit()
    print("Checks demo data loaded in company %r." % COMPANY_NAME)


load(env)  # noqa: F821 - `env` is provided by odoo-bin shell
