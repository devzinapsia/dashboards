from collections import defaultdict
from datetime import timedelta

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.tools import SQL
from odoo.tools.translate import LazyTranslate

from .account_pl_structure import PL_ACCOUNT_TYPES
from .pl_currency_converter import PlCurrencyConverter

_lt = LazyTranslate(__name__)

PERIODS = ("month", "fiscal_year", "previous_fiscal_year", "last_12")

# Rows computed from the section totals, below the structure. This is the
# single place where they are defined: an "amount" row is a linear
# combination of section totals (coefficient per section), a "percent" row
# is another computed row divided by a section total (empty when that
# section total is zero). Rows are evaluated in order, so a percent row can
# refer to any amount row defined above it.
COMPUTED_ROWS = [
    {
        "key": "gross_profit",
        "label": _lt("Gross profit"),
        "type": "amount",
        "coefficients": {"income": 1, "direct_cost": -1},
    },
    {
        "key": "gross_profit_pct",
        "label": _lt("Gross profit %"),
        "type": "percent",
        "numerator": "gross_profit",
        "denominator": "income",
    },
    {
        "key": "net_profit",
        "label": _lt("Net profit"),
        "type": "amount",
        "coefficients": {"income": 1, "direct_cost": -1, "indirect_cost": -1},
    },
    {
        "key": "net_profit_pct",
        "label": _lt("Net profit %"),
        "type": "percent",
        "numerator": "net_profit",
        "denominator": "income",
    },
]

TOTAL_COLUMN = "total"
UNASSIGNED_ROW = "unassigned"


class AccountPlDashboard(models.AbstractModel):
    """Computation engine of the management P&L dashboard.

    Every public method is meant to be called via RPC from the OWL client
    action. The business logic lives here, the frontend only renders what
    these methods return. Journal items are read with sudo() because a
    dashboard user doesn't need accounting rights, so every public method
    checks the group membership itself and only ever reads the current
    company (which Odoo guarantees to be one of the user's allowed
    companies).

    Amounts are kept unrounded all along; rounding only happens when the
    frontend formats them.
    """

    _name = "account.pl.dashboard"
    _description = "Management P&L dashboard"
    _inherit = "dashboards.drilldown.mixin"

    # -------------------------------------------------------------------------
    # Access
    # -------------------------------------------------------------------------

    def _check_dashboard_access(self):
        if not self.env.user.has_group("account_management_pl_dashboard.group_management_pl_user"):
            raise AccessError(self.env._("You are not allowed to see the management P&L dashboard."))
        company = self.env.company
        if company.id not in self.env.user._get_company_ids():
            raise AccessError(self.env._("You are not allowed to access company %s.", company.display_name))
        return company

    def _get_structure(self, company):
        return self.env["account.pl.structure"].sudo()._get_active_structure(company)

    # -------------------------------------------------------------------------
    # Periods
    # -------------------------------------------------------------------------

    @api.model
    def _get_period_bounds(self, period, company, today):
        if period == "month":
            return today.replace(day=1), today.replace(day=1) + relativedelta(months=1, days=-1)
        if period == "fiscal_year":
            bounds = company.compute_fiscalyear_dates(today)
            return bounds["date_from"], bounds["date_to"]
        if period == "previous_fiscal_year":
            current = company.compute_fiscalyear_dates(today)
            bounds = company.compute_fiscalyear_dates(current["date_from"] - timedelta(days=1))
            return bounds["date_from"], bounds["date_to"]
        if period == "last_12":
            month_start = today.replace(day=1)
            return month_start - relativedelta(months=11), month_start + relativedelta(months=1, days=-1)
        raise UserError(self.env._("Unknown period: %s", period))

    @api.model
    def _get_columns(self, period, company, today):
        """One column per calendar month of the period (clipped to the period
        bounds, for fiscal years that don't start on the 1st), plus a Total
        column when the period spans more than one month. Months starting
        after today are flagged as future: they are shown empty, not as 0."""
        date_from, date_to = self._get_period_bounds(period, company, today)
        columns = []
        month_start = date_from.replace(day=1)
        while month_start <= date_to:
            month_end = month_start + relativedelta(months=1, days=-1)
            columns.append({
                "key": month_start.strftime("%Y-%m"),
                "date_from": max(month_start, date_from),
                "date_to": min(month_end, date_to),
                "is_future": month_start > today,
                "is_total": False,
            })
            month_start += relativedelta(months=1)
        if len(columns) > 1:
            columns.append({
                "key": TOTAL_COLUMN,
                "date_from": date_from,
                "date_to": date_to,
                "is_future": False,
                "is_total": True,
            })
        return columns

    @api.model
    def _column_key_of(self, date):
        return date.strftime("%Y-%m")

    # -------------------------------------------------------------------------
    # Data gathering
    # -------------------------------------------------------------------------

    def _base_move_line_domain(self, structure, date_from, date_to):
        domain = [
            ("company_id", "=", structure.company_id.id),
            ("parent_state", "=", "posted"),
            ("date", ">=", date_from),
            ("date", "<=", date_to),
        ]
        if structure.excluded_journal_ids:
            domain.append(("journal_id", "not in", structure.excluded_journal_ids.ids))
        return domain

    def _read_move_line_amounts(self, domain, key_fields, converter=None):
        """Sum journal items by ``key_fields`` and month, in the display
        currency.

        One query whatever the number of journal items. In company currency
        the items are grouped by month directly; in the secondary currency
        they are grouped by accounting date and journal item currency, which
        is the granularity the conversion needs (one rate per day, original
        amount for items already in the secondary currency).

        :param list key_fields: many2one fields to group by (e.g.
            ["account_id"] or ["account_id", "partner_id"]).
        :param PlCurrencyConverter converter: None for the company currency.
        :return: list of (key_ids, month_key, amount) tuples, key_ids being a
            tuple of record ids (0 when empty); amounts keep the accounting
            sign (debit positive).
        """
        MoveLine = self.env["account.move.line"].sudo()
        size = len(key_fields)
        if not converter:
            rows = MoveLine._read_group(domain, groupby=[*key_fields, "date:month"], aggregates=["balance:sum"])
            return [
                (tuple(record.id or 0 for record in row[:size]), self._column_key_of(row[size]), row[size + 1] or 0.0)
                for row in rows
            ]
        rows = MoveLine._read_group(
            domain,
            groupby=[*key_fields, "date:day", "currency_id"],
            aggregates=["balance:sum", "amount_currency:sum"],
        )
        return [
            (
                tuple(record.id or 0 for record in row[:size]),
                self._column_key_of(row[size]),
                converter.convert_move_lines(row[size], row[size + 1].id, row[size + 2] or 0.0, row[size + 3] or 0.0),
            )
            for row in rows
        ]

    def _read_analytic_amounts(self, structure, date_from, date_to, key_fields, accounts, analytic_ids,
                               converter=None):
        """Sum the analytic lines of the structure's analytic plan for the
        selected analytic accounts (toolbar filter), i.e. only the share of
        each journal item distributed to them.

        Analytic lines are read through their journal item, so the same rules
        apply as everywhere else: posted entries only, accounting date of the
        journal item, company, excluded journals. In the secondary currency,
        each analytic line takes the same share of its journal item's
        secondary amount as of its company-currency balance (exact, because
        both conversion cases are linear).

        :param list key_fields: journal item fields to group by ("account_id",
            "partner_id").
        :param tuple accounts: ("in", account_ids) or ("pl_except", account_ids),
            the latter meaning every P&L account except those.
        :return: same shape as _read_move_line_amounts.
        """
        plan = structure._get_analytic_plan()
        self.env["account.move.line"].flush_model()
        self.env["account.analytic.line"].flush_model()
        self.env["account.account"].flush_model(["account_type"])
        plan_column = SQL.identifier("aal", plan._column_name())
        keys_sql = SQL(", ").join(SQL.identifier("aml", key_field) for key_field in key_fields)
        conditions = [
            SQL("aml.company_id = %s", structure.company_id.id),
            SQL("aml.parent_state = 'posted'"),
            SQL("aml.date BETWEEN %s AND %s", date_from, date_to),
            SQL("%s = ANY(%s)", plan_column, list(analytic_ids)),
        ]
        if structure.excluded_journal_ids:
            conditions.append(SQL("aml.journal_id <> ALL(%s)", structure.excluded_journal_ids.ids))
        operator, account_ids = accounts
        if operator == "in":
            conditions.append(SQL("aml.account_id = ANY(%s)", list(account_ids)))
        else:
            conditions.append(SQL("aa.account_type IN %s", PL_ACCOUNT_TYPES))
            conditions.append(SQL("aml.account_id <> ALL(%s)", list(account_ids)))
        size = len(key_fields)

        # aal.amount = -balance x distribution, so -aal.amount is the share of
        # the journal item's balance (accounting sign).
        if converter:
            query = SQL(
                """
                SELECT %(keys)s, aml.date, aml.currency_id,
                       SUM(-aal.amount),
                       SUM(aml.amount_currency * -aal.amount / NULLIF(aml.balance, 0))
                  FROM account_analytic_line aal
                  JOIN account_move_line aml ON aml.id = aal.move_line_id
                  JOIN account_account aa ON aa.id = aml.account_id
                 WHERE %(where)s
              GROUP BY %(keys)s, aml.date, aml.currency_id
                """,
                keys=keys_sql,
                where=SQL(" AND ").join(conditions),
            )
            self.env.cr.execute(query)
            return [
                (
                    tuple(key_id or 0 for key_id in row[:size]),
                    self._column_key_of(row[size]),
                    converter.convert_move_lines(row[size], row[size + 1], row[size + 2] or 0.0, row[size + 3] or 0.0),
                )
                for row in self.env.cr.fetchall()
            ]
        query = SQL(
            """
            SELECT %(keys)s, date_trunc('month', aml.date)::date, SUM(-aal.amount)
              FROM account_analytic_line aal
              JOIN account_move_line aml ON aml.id = aal.move_line_id
              JOIN account_account aa ON aa.id = aml.account_id
             WHERE %(where)s
          GROUP BY %(keys)s, date_trunc('month', aml.date)::date
            """,
            keys=keys_sql,
            where=SQL(" AND ").join(conditions),
        )
        self.env.cr.execute(query)
        return [
            (tuple(key_id or 0 for key_id in row[:size]), self._column_key_of(row[size]), row[size + 1] or 0.0)
            for row in self.env.cr.fetchall()
        ]

    def _collect_amounts(self, structure, date_from, date_to, converter=None, analytic_ids=None):
        """Gather the period's amounts, classified by structure leaf.

        Every leaf adds up the balance of its accounts, with its section's
        sign (Sales: credit - debit, costs: debit - credit). Sales leaves are
        also broken down by commercial customer, for their drill-down.

        :param list analytic_ids: toolbar analytic/project filter. When set,
            amounts are read from the analytic lines of those analytic
            accounts (i.e. only the share of each journal item distributed to
            them), instead of from the journal items.
        :return: dict with
            - ``leaf``: {(line_id, month_key): amount};
            - ``leaf_detail``: {(line_id, detail_key, month_key): amount}, the
              per-account (costs) or per-customer (Sales) breakdown of each
              leaf;
            - ``unassigned``: {(detail_key, month_key): amount} for the P&L
              accounts no line includes, with the "effect on the result" sign
              (credit - debit), so that net profit + unassigned = the
              accounting result of the period.
        """
        leaf = defaultdict(float)
        leaf_detail = defaultdict(float)
        unassigned = defaultdict(float)
        account_leaf = {
            account.id: line for line in structure.line_ids for account in line.account_ids
        }
        sales_accounts = structure._get_sales_accounts()

        def read(domain_or_accounts, key_fields):
            if analytic_ids is not None:
                return self._read_analytic_amounts(
                    structure, date_from, date_to, key_fields, domain_or_accounts, analytic_ids, converter,
                )
            operator, account_ids = domain_or_accounts
            domain = self._base_move_line_domain(structure, date_from, date_to)
            if operator == "in":
                domain.append(("account_id", "in", list(account_ids)))
            else:
                domain += [
                    ("account_id.account_type", "in", PL_ACCOUNT_TYPES),
                    ("account_id", "not in", list(account_ids)),
                ]
            return self._read_move_line_amounts(domain, key_fields, converter)

        # Cost lines, and the P&L accounts no line includes, by account.
        for (account_id,), month_key, balance in read(("pl_except", sales_accounts.ids), ["account_id"]):
            line = account_leaf.get(account_id)
            detail_key = "account-%d" % account_id
            if line:
                sign = -1 if line.section == "income" else 1
                leaf[line.id, month_key] += sign * balance
                leaf_detail[line.id, detail_key, month_key] += sign * balance
            else:
                unassigned[detail_key, month_key] -= balance

        # Sales lines, by account and commercial customer.
        if sales_accounts:
            rows = read(("in", sales_accounts.ids), ["account_id", "partner_id"])
            partners = self.env["res.partner"].sudo().browse(
                {partner_id for (_account_id, partner_id), _month, _balance in rows if partner_id}
            )
            commercial_of = {partner.id: partner.commercial_partner_id.id for partner in partners}
            for (account_id, partner_id), month_key, balance in rows:
                line = account_leaf[account_id]
                detail_key = "partner-%d" % commercial_of.get(partner_id, 0)
                leaf[line.id, month_key] -= balance
                leaf_detail[line.id, detail_key, month_key] -= balance

        return {"leaf": leaf, "leaf_detail": leaf_detail, "unassigned": unassigned}

    # -------------------------------------------------------------------------
    # Analytic filter
    # -------------------------------------------------------------------------

    def _get_analytic_filter_options(self, structure):
        """Analytic accounts (or projects) offered by the toolbar filter."""
        plan = structure._get_analytic_plan()
        if not plan:
            return []
        analytics = self.env["account.analytic.account"].sudo().search([
            ("root_plan_id", "=", plan.id),
            ("company_id", "in", (False, *structure.company_id.parent_ids.ids)),
        ])
        return [{"id": analytic.id, "name": analytic.display_name} for analytic in analytics]

    def _sanitize_analytic_filter(self, structure, analytic_ids):
        """Keep only analytic accounts the filter actually offers; None when
        there is no filter."""
        if not analytic_ids or structure.analytic_mode == "none":
            return None
        allowed = {option["id"] for option in self._get_analytic_filter_options(structure)}
        return [analytic_id for analytic_id in analytic_ids if analytic_id in allowed] or None

    # -------------------------------------------------------------------------
    # Aggregation
    # -------------------------------------------------------------------------

    def _build_values(self, structure, columns, amounts):
        """Compute every row x column value from the collected amounts.

        :return: (values, section_totals, unassigned_values) where values is
            {line_id: {column_key: amount}} and section_totals
            {section: {column_key: amount}}. Future columns hold None.
        """
        month_columns = [column for column in columns if not column["is_total"]]
        has_total = any(column["is_total"] for column in columns)
        lines = structure.line_ids
        values = {}
        # Children first, so that groups can add up their already-computed
        # sub-lines.
        for line in lines.sorted(lambda line: line.level, reverse=True):
            row = {}
            for column in month_columns:
                if column["is_future"]:
                    row[column["key"]] = None
                elif line.child_ids:
                    row[column["key"]] = sum(values[child.id][column["key"]] or 0.0 for child in line.child_ids)
                else:
                    row[column["key"]] = amounts["leaf"].get((line.id, column["key"]), 0.0)
            if has_total:
                row[TOTAL_COLUMN] = self._sum_columns(row, month_columns)
            values[line.id] = row

        section_totals = {
            line.section: values[line.id] for line in lines.filtered("is_root")
        }
        unassigned = {}
        for column in month_columns:
            if column["is_future"]:
                unassigned[column["key"]] = None
            else:
                unassigned[column["key"]] = sum(
                    amount for (_detail, month_key), amount in amounts["unassigned"].items()
                    if month_key == column["key"]
                )
        if has_total:
            unassigned[TOTAL_COLUMN] = self._sum_columns(unassigned, month_columns)
        return values, section_totals, unassigned

    @api.model
    def _sum_columns(self, row, month_columns):
        return sum(row[column["key"]] or 0.0 for column in month_columns)

    @api.model
    def _compute_computed_rows(self, section_totals, column_keys):
        """Evaluate COMPUTED_ROWS for every column.

        :return: {row_key: {column_key: value}}; None means "empty" (future
            month, or percentage over a zero base).
        """
        results = {}
        for definition in COMPUTED_ROWS:
            row = {}
            for column_key in column_keys:
                if any(section_totals[section][column_key] is None for section in section_totals):
                    row[column_key] = None
                    continue
                if definition["type"] == "amount":
                    row[column_key] = sum(
                        coefficient * section_totals[section][column_key]
                        for section, coefficient in definition["coefficients"].items()
                    )
                else:
                    numerator = results[definition["numerator"]][column_key]
                    denominator = section_totals[definition["denominator"]][column_key]
                    row[column_key] = (
                        numerator / denominator * 100.0
                        if numerator is not None and denominator else None
                    )
            results[definition["key"]] = row
        return results

    # -------------------------------------------------------------------------
    # Budget
    # -------------------------------------------------------------------------

    def _collect_budget(self, request, converter=None):
        """Budgeted amounts by account and month, in the display currency,
        with the accounting sign (debit positive), from the structure's
        accounting budget (account.report.budget: one item per account and
        month, in company currency).

        In the secondary currency, each month's company-currency budget is
        converted at the rate of the month's last day (for the current month,
        the most recent rate, i.e. today's): the deviation then includes the
        exchange rate effect.

        Future months are left out, like the actual figures, so that totals
        compare the same months.

        :return: {(account_id, month_key): amount}
        """
        structure = request["structure"]
        rows = self.env["account.report.budget.item"].sudo()._read_group(
            [
                ("budget_id", "=", structure.budget_id.id),
                ("date", ">=", request["date_from"].replace(day=1)),
                ("date", "<=", request["read_to"]),
            ],
            groupby=["account_id", "date:month"],
            aggregates=["amount:sum"],
        )
        today = fields.Date.context_today(self)
        budget = defaultdict(float)
        for account, month, amount in rows:
            if not amount:
                continue
            if converter:
                month_end = month + relativedelta(months=1, days=-1)
                amount = converter.convert_balance(amount, min(month_end, today))
            budget[account.id, self._column_key_of(month)] += amount
        return budget

    def _is_budget_shown(self, request, show_budget):
        structure = request["structure"]
        return bool(
            show_budget and structure.budget_enabled and structure.budget_id
            and request["analytic_ids"] is None
        )

    @api.model
    def _deviation(self, actual, budget):
        """(actual - budget) / |budget| in %, or None ("n/a") when there is
        no budget to compare with."""
        if actual is None or budget is None or not budget:
            return None
        return (actual - budget) / abs(budget) * 100.0

    def _build_budget_values(self, request, budget):
        """Budget of every structure line and column, in the section's sign.

        Leaves add up the budget of their accounts (Sales: income budgets are
        stored negative, like their balance); groups and sections add up their
        sub-lines.

        :return: {line_id: {column_key: amount or None}}
        """
        structure, columns = request["structure"], request["columns"]
        month_columns = [column for column in columns if not column["is_total"]]
        has_total = len(columns) > len(month_columns)
        values = {}
        for line in structure.line_ids.sorted(lambda line: line.level, reverse=True):
            sign = -1 if line.section == "income" else 1
            row = {}
            for column in month_columns:
                key = column["key"]
                if column["is_future"]:
                    row[key] = None
                elif line.child_ids:
                    row[key] = sum(values[child.id][key] or 0.0 for child in line.child_ids)
                else:
                    row[key] = sign * sum(budget.get((account.id, key), 0.0) for account in line.account_ids)
            if has_total:
                row[TOTAL_COLUMN] = self._sum_columns(row, month_columns)
            values[line.id] = row
        return values

    # -------------------------------------------------------------------------
    # Public RPC
    # -------------------------------------------------------------------------

    @api.model
    def get_dashboard_config(self):
        """Toolbar settings, loaded once when the dashboard opens. Kept apart
        from get_dashboard_data so that the toolbar (and the switch back to
        the company currency) stays usable when the data itself fails, e.g.
        because of a missing exchange rate."""
        company = self._check_dashboard_access()
        structure = self._get_structure(company)
        if not structure:
            return {"has_structure": False, "company_name": company.display_name}
        return {
            "has_structure": True,
            "company_name": company.display_name,
            "company_currency_id": company.currency_id.id,
            "company_currency_name": company.currency_id.name,
            "secondary_currency_id": structure.secondary_currency_id.id or False,
            "secondary_currency_name": structure.secondary_currency_id.name or False,
            "default_display_currency": (
                structure.default_display_currency if structure.secondary_currency_id else "company"
            ),
            "budget_enabled": structure.budget_enabled,
            "analytic_mode": structure.analytic_mode,
            "analytic_filter_options": self._get_analytic_filter_options(structure),
            "can_configure": self.env.user.has_group("account_management_pl_dashboard.group_management_pl_manager"),
        }

    def _prepare_request(self, period, display_currency, analytic_ids):
        """Resolve and validate the parameters shared by every dashboard RPC.

        The grid and the drill-down popups go through this same preparation
        and the same _collect_amounts() call, which is what guarantees that a
        popup's detail adds up to the cell it was opened from.

        :return: dict, or None when the company has no active structure.
        """
        company = self._check_dashboard_access()
        if period not in PERIODS:
            raise UserError(self.env._("Unknown period: %s", period))
        structure = self._get_structure(company)
        if not structure:
            return None
        display_currency = display_currency or structure.default_display_currency
        if display_currency == "secondary" and not structure.secondary_currency_id:
            display_currency = "company"
        currency = structure.secondary_currency_id if display_currency == "secondary" else company.currency_id
        today = fields.Date.context_today(self)
        columns = self._get_columns(period, company, today)
        date_from, date_to = columns[0]["date_from"], columns[-1]["date_to"]
        # Future months are shown empty: their (future-dated) journal items
        # are neither read nor converted.
        read_to = min(date_to, max(column["date_to"] for column in columns if not column["is_future"]))
        return {
            "company": company,
            "structure": structure,
            "period": period,
            "display_currency": display_currency,
            "currency": currency,
            "columns": columns,
            "date_from": date_from,
            "date_to": date_to,
            "read_to": read_to,
            "analytic_ids": self._sanitize_analytic_filter(structure, analytic_ids),
        }

    def _compute_request_amounts(self, request, with_budget=False):
        """:return: (amounts, budget) - budget is {} unless with_budget."""
        converter = None
        if request["display_currency"] == "secondary":
            converter = PlCurrencyConverter(
                self.env, request["company"], request["currency"],
                request["structure"].rate_max_age_days, request["read_to"],
            )
        amounts = self._collect_amounts(
            request["structure"], request["date_from"], request["read_to"], converter, request["analytic_ids"],
        )
        budget = self._collect_budget(request, converter) if with_budget else {}
        if converter:
            # Never return a silently wrong amount: the company currency view
            # stays available, the frontend shows this as a warning.
            converter.raise_if_missing()
        return amounts, budget

    @api.model
    def get_dashboard_data(self, period="fiscal_year", display_currency=None, analytic_ids=None,
                           show_budget=True):
        """Everything the dashboard grid needs, in one call.

        :param str period: one of PERIODS.
        :param str display_currency: "company" or "secondary"; defaults to
            the structure's default_display_currency.
        :param list analytic_ids: toolbar analytic account / project filter.
        :param bool show_budget: toolbar budget toggle (only applies when the
            structure enables the budget comparison).
        """
        request = self._prepare_request(period, display_currency, analytic_ids)
        if not request:
            return {"has_structure": False, "company_name": self.env.company.display_name}
        structure, columns, currency = request["structure"], request["columns"], request["currency"]
        budget_shown = self._is_budget_shown(request, show_budget)
        amounts, budget = self._compute_request_amounts(request, with_budget=budget_shown)
        values, section_totals, unassigned = self._build_values(structure, columns, amounts)
        budget_values = self._build_budget_values(request, budget) if budget_shown else {}
        column_keys = [column["key"] for column in columns]
        computed = self._compute_computed_rows(section_totals, column_keys)

        rows = []
        for line in structure.line_ids:
            rows.append({
                "key": "line-%d" % line.id,
                "line_id": line.id,
                "parent_key": "line-%d" % line.parent_id.id if line.parent_id else False,
                "name": line.name,
                "level": line.level,
                "kind": "section" if line.is_root else ("group" if line.child_ids else "leaf"),
                "section": line.section,
                "assignment_status": line.assignment_status or False,
                "values": values[line.id],
                "drilldown": True,
            })
            if budget_shown:
                rows[-1]["budget"] = budget_values[line.id]
                rows[-1]["deviation"] = {
                    key: self._deviation(value, budget_values[line.id][key])
                    for key, value in values[line.id].items()
                }
        for definition in COMPUTED_ROWS:
            rows.append({
                "key": definition["key"],
                "name": str(definition["label"]),
                "level": 0,
                "kind": "computed_" + definition["type"],
                "values": computed[definition["key"]],
                "drilldown": False,
            })
        if any(value is not None and not currency.is_zero(value) for value in unassigned.values()):
            rows.append({
                "key": UNASSIGNED_ROW,
                "name": self.env._("Unassigned"),
                "level": 0,
                "kind": "unassigned",
                "values": unassigned,
                "drilldown": True,
            })

        return {
            "has_structure": True,
            "structure_id": structure.id,
            "company_name": request["company"].display_name,
            "period": request["period"],
            "date_from": fields.Date.to_string(request["date_from"]),
            "date_to": fields.Date.to_string(request["date_to"]),
            "display_currency": request["display_currency"],
            "currency_id": currency.id,
            "currency_name": currency.name,
            "analytic_ids": request["analytic_ids"] or [],
            "budget_shown": budget_shown,
            "budget_unavailable_reason": (
                self.env._("The budget is by account: it can't be compared with an analytic filter.")
                if show_budget and structure.budget_enabled and request["analytic_ids"] is not None else False
            ),
            "columns": [
                {
                    "key": column["key"],
                    "date_from": fields.Date.to_string(column["date_from"]),
                    "date_to": fields.Date.to_string(column["date_to"]),
                    "is_future": column["is_future"],
                    "is_total": column["is_total"],
                }
                for column in columns
            ],
            "rows": rows,
        }

    # -------------------------------------------------------------------------
    # Drill-down
    # -------------------------------------------------------------------------

    def _get_request_column(self, request, column_key):
        column = next((column for column in request["columns"] if column["key"] == column_key), None)
        if not column:
            raise UserError(self.env._("Unknown column: %s", column_key))
        month_keys = {
            other["key"] for other in request["columns"]
            if not other["is_total"] and not other["is_future"]
            and (column["is_total"] or other["key"] == column["key"])
        }
        return column, month_keys

    def _get_request_line(self, request, row_key):
        if row_key == UNASSIGNED_ROW:
            return None
        try:
            line_id = int(row_key.removeprefix("line-"))
        except ValueError:
            raise UserError(self.env._("This row has no detail.")) from None
        line = request["structure"].line_ids.filtered(lambda line: line.id == line_id)
        if not line:
            raise UserError(self.env._("This row has no detail."))
        return line

    def _describe_detail_keys(self, request, line, detail_keys):
        """Labels (and account codes) of drill-down detail keys, read in batch.

        Keys are "account-<id>", "partner-<id>" (0 = no customer) or "all"
        (every journal item of the line's accounts).
        """
        ids = defaultdict(set)
        for key in detail_keys:
            if key != "all":
                kind, record_id = key.rsplit("-", 1)
                ids[kind].add(int(record_id))
        records = {
            "account": self.env["account.account"].sudo().with_company(request["company"]).browse(ids["account"]),
            "partner": self.env["res.partner"].sudo().browse(ids["partner"] - {0}),
        }
        names = {kind: {record.id: record for record in recordset} for kind, recordset in records.items()}
        descriptions = {}
        for key in detail_keys:
            if key == "all":
                descriptions[key] = {"label": line.name, "code": False}
                continue
            kind, record_id = key.rsplit("-", 1)
            record = names[kind].get(int(record_id))
            if kind == "account":
                descriptions[key] = {"label": record.name, "code": record.code}
            else:
                descriptions[key] = {
                    "label": record.display_name if record else self.env._("Without customer"),
                    "code": False,
                }
        return descriptions

    @api.model
    def get_cell_detail(self, row_key, column_key, period="fiscal_year", display_currency=None,
                        analytic_ids=None, show_budget=True):
        """Detail of one grid cell, loaded on demand by the drill-down popup.

        - a section or group: its leaves, each one can be opened in turn;
        - a cost line: its accounts;
        - a Sales line: its amount by commercial customer;
        - the Unassigned row: the P&L accounts no line includes.

        Amounts are in the display currency and add up exactly to the cell's
        value (same computation as the grid); so do the budgets of a line's
        sub-lines or of a cost line's accounts. Budgets are by account, so a
        Sales line's customers have none (only the line itself).
        """
        request = self._prepare_request(period, display_currency, analytic_ids)
        if not request:
            raise UserError(self.env._("There is no active management P&L structure."))
        column, month_keys = self._get_request_column(request, column_key)
        request["detail_from"] = column["date_from"]
        request["detail_to"] = min(column["date_to"], request["read_to"])
        line = self._get_request_line(request, row_key)
        budget_shown = self._is_budget_shown(request, show_budget) and line is not None
        amounts, budget = self._compute_request_amounts(request, with_budget=budget_shown)
        budget_values = self._build_budget_values(request, budget) if budget_shown else {}
        can_read = {
            model: self.env[model].has_access("read") for model in ("account.move.line", "account.analytic.line")
        }

        entries = []
        if line and (line.is_root or line.child_ids):
            # Descendants share their ancestor's sort key as prefix.
            leaves = request["structure"].line_ids.filtered(
                lambda leaf: not leaf.child_ids and leaf.sort_key.startswith(line.sort_key + "/")
            )
            for leaf in leaves:
                entries.append({
                    "key": "line-%d" % leaf.id,
                    "label": leaf.complete_name.split(" / ", line.level + 1)[-1],
                    "code": False,
                    "amount": sum(amounts["leaf"].get((leaf.id, month_key), 0.0) for month_key in month_keys),
                    "open": "line",
                })
                if budget_shown:
                    entries[-1]["budget"] = sum(
                        budget_values[leaf.id][month_key] or 0.0 for month_key in month_keys
                    )
            kind = "lines"
        else:
            totals = defaultdict(float)
            account_budgets = {}
            if line:
                for (line_id, detail_key, month_key), amount in amounts["leaf_detail"].items():
                    if line_id == line.id and month_key in month_keys:
                        totals[detail_key] += amount
                if budget_shown and line.section != "income":
                    # Budgeted accounts without any movement are listed too, so
                    # that the budgets add up to the cell's budget.
                    for account in line.account_ids:
                        account_budget = sum(budget.get((account.id, month_key), 0.0) for month_key in month_keys)
                        account_budgets["account-%d" % account.id] = account_budget
                        if account_budget:
                            totals.setdefault("account-%d" % account.id, 0.0)
            else:
                for (detail_key, month_key), amount in amounts["unassigned"].items():
                    if month_key in month_keys:
                        totals[detail_key] += amount
            descriptions = self._describe_detail_keys(request, line, totals)
            for detail_key, amount in totals.items():
                model, _domain = self._get_detail_target(request, line, detail_key)
                entries.append({
                    "key": detail_key,
                    **descriptions[detail_key],
                    "amount": amount,
                    "open": "items" if can_read[model] else False,
                })
                if budget_shown:
                    entries[-1]["budget"] = account_budgets.get(detail_key)
            entries.sort(key=lambda entry: (entry["code"] or "", entry["label"]))
            kind = "items"

        total = sum(entry["amount"] for entry in entries)
        total_budget = budget_values[line.id][column_key] if budget_shown else None
        for entry in entries:
            if budget_shown:
                entry["deviation"] = self._deviation(entry["amount"], entry["budget"])
        is_leaf = bool(line) and not line.is_root and not line.child_ids
        return {
            "kind": kind,
            "row_key": row_key,
            "column_key": column_key,
            "currency_id": request["currency"].id,
            "display_currency": request["display_currency"],
            "company_currency_name": request["company"].currency_id.name,
            "section": line.section if line else False,
            "entries": entries,
            "total": total,
            # A line with accounts: every journal item of those accounts for
            # the column's period can be opened at once.
            "can_open_all": is_leaf and bool(line.account_ids) and can_read[
                "account.analytic.line" if request["analytic_ids"] is not None else "account.move.line"
            ],
            "budget_shown": budget_shown,
            "total_budget": total_budget,
            "total_deviation": self._deviation(total, total_budget) if budget_shown else None,
        }

    def _get_detail_target(self, request, line, detail_key):
        """(model, domain) listing the journal items (or, with the analytic
        filter, the analytic lines) behind one drill-down detail entry:

        - "account-<id>": that account's items;
        - "partner-<id>": the items of the Sales line's accounts for that
          commercial customer (its contacts included; 0 = no customer);
        - "all": every item of the line's accounts.
        """
        structure = request["structure"]
        analytic_ids = request["analytic_ids"]
        if analytic_ids is not None:
            plan_field = structure._get_analytic_plan()._column_name()
            domain = [
                ("company_id", "=", structure.company_id.id),
                ("move_line_id.parent_state", "=", "posted"),
                ("move_line_id.date", ">=", request["detail_from"]),
                ("move_line_id.date", "<=", request["detail_to"]),
                (plan_field, "in", analytic_ids),
            ]
            if structure.excluded_journal_ids:
                domain.append(("move_line_id.journal_id", "not in", structure.excluded_journal_ids.ids))
            prefix, model = "move_line_id.", "account.analytic.line"
        else:
            domain = self._base_move_line_domain(structure, request["detail_from"], request["detail_to"])
            prefix, model = "", "account.move.line"

        if detail_key == "all":
            if not line:
                raise UserError(self.env._("This row has no detail."))
            domain.append((prefix + "account_id", "in", line.account_ids.ids))
            return model, domain
        kind, record_id = detail_key.rsplit("-", 1)
        record_id = int(record_id)
        if kind == "account":
            domain.append((prefix + "account_id", "=", record_id))
        elif kind == "partner" and line:
            domain.append((prefix + "account_id", "in", line.account_ids.ids))
            domain.append(
                (prefix + "partner_id.commercial_partner_id", "=", record_id) if record_id
                else (prefix + "partner_id", "=", False)
            )
        else:
            raise UserError(self.env._("This row has no detail."))
        return model, domain

    @api.model
    def get_detail_action(self, row_key, column_key, detail_key, period="fiscal_year", display_currency=None,
                          analytic_ids=None, show_budget=True):
        """Window action listing the journal items behind a popup entry, or
        every journal item of a line's accounts ("all"), for the period of the
        clicked column (in company currency: the list views can't total in
        another currency).

        Takes the same parameters as the other dashboard RPCs (the popup sends
        them all); ``show_budget`` doesn't change which journal items match.
        """
        request = self._prepare_request(period, display_currency, analytic_ids)
        if not request:
            raise UserError(self.env._("There is no active management P&L structure."))
        column, _month_keys = self._get_request_column(request, column_key)
        request["detail_from"] = column["date_from"]
        request["detail_to"] = min(column["date_to"], request["read_to"])
        line = self._get_request_line(request, row_key)
        model, domain = self._get_detail_target(request, line, detail_key)
        description = self._describe_detail_keys(request, line, [detail_key])[detail_key]
        name = " ".join(filter(None, [description["code"], description["label"]]))
        return self._get_drilldown_action(model, domain=domain, name=name)
