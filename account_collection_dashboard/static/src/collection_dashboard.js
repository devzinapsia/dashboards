import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Layout } from "@web/search/layout";
import { formatMonetary } from "@web/views/fields/formatters";
import { today, serializeDate } from "@web/core/l10n/dates";
import { _t } from "@web/core/l10n/translation";
import { DashboardsKpiCard } from "@dashboards_base/components/kpi_card/kpi_card";
import { Component, onWillStart, useState } from "@odoo/owl";

export class CollectionDashboard extends Component {
    static template = "account_collection_dashboard.CollectionDashboard";
    static components = { Layout, DashboardsKpiCard };
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.labels = {
            treasurySection: _t("Treasury"),
            reconciliationSection: _t("Reconciliation"),
            multiCurrencySection: _t("Multi-currency"),
            bySalespersonSection: _t("By salesperson"),
            totalReceivable: _t("Total receivable"),
            rejectedChecks: _t("Rejected checks"),
            collectionTurnover: _t("Collection turnover"),
            collectionPaymentRatio: _t("Collection/Payment ratio"),
            customersWithDebt: _t("Customers with debt"),
            undueDebt: _t("Not yet due"),
            dueToday: _t("Due today"),
            dueNext7Days: _t("Due in 7 days"),
            fixedFund: _t("Fixed fund"),
            dueSoonByLevel: _t("Due soon, by Follow-up level"),
            overdueByAge: _t("Overdue, by age"),
            topOverduePartners: _t("Top overdue customers"),
            cashCollections: _t("Cash/transfer collections"),
            pendingReconciliation: _t("Pending reconciliation"),
            checksInPortfolio: _t("Third-party checks in portfolio"),
            pendingExchangeDifference: _t("Pending exchange difference"),
            allCurrencies: _t("All currencies"),
            currentFiscalYear: _t("Current fiscal year"),
            previousFiscalYear: _t("Previous fiscal year"),
            last12Months: _t("Last 12 months"),
        };
        this.state = useState({
            dateFrom: today().startOf("month"),
            dateTo: today().endOf("month"),
            currencies: [],
            selectedCurrencyId: null,
            turnoverPeriod: "current_fiscal_year",
            totalReceivable: null,
            rejectedChecks: null,
            collectionTurnover: null,
            collectionPaymentRatio: null,
            customersWithDebt: null,
            undueDebt: null,
            dueToday: null,
            dueNext7Days: null,
            dueSoonByLevel: [],
            overdueByAge: [],
            topOverduePartners: [],
            bankBalances: [],
            fixedFund: null,
            cashCollections: null,
            pendingReconciliation: null,
            checksInPortfolio: null,
            pendingExchangeDifference: null,
            collectionByUser: [],
        });

        onWillStart(() => this.fetchData());
    }

    get display() {
        return { controlPanel: {} };
    }

    formatMonetary(value, currencyId) {
        return formatMonetary(value || 0, { currencyId });
    }

    async fetchData() {
        const dateFrom = serializeDate(this.state.dateFrom);
        const dateTo = serializeDate(this.state.dateTo);
        const currencyId = this.state.selectedCurrencyId || undefined;
        const [
            currencies,
            totalReceivable,
            rejectedChecks,
            collectionTurnover,
            collectionPaymentRatio,
            customersWithDebt,
            undueDebt,
            dueToday,
            dueNext7Days,
            dueSoonByLevel,
            overdueByAge,
            topOverduePartners,
            bankBalances,
            fixedFund,
            cashCollections,
            pendingReconciliation,
            checksInPortfolio,
            pendingExchangeDifference,
            collectionByUser,
        ] = await Promise.all([
            this.orm.call("account.collection.dashboard", "get_active_currencies", []),
            this.orm.call("account.collection.dashboard", "get_total_receivable", [currencyId]),
            this.orm.call("account.collection.dashboard", "get_rejected_checks", [currencyId]),
            this.orm.call("account.collection.dashboard", "get_collection_turnover", [this.state.turnoverPeriod]),
            this.orm.call("account.collection.dashboard", "get_collection_payment_ratio", [dateFrom, dateTo]),
            this.orm.call("account.collection.dashboard", "get_customers_with_debt", [currencyId]),
            this.orm.call("account.collection.dashboard", "get_undue_debt", [currencyId]),
            this.orm.call("account.collection.dashboard", "get_due_today", [currencyId]),
            this.orm.call("account.collection.dashboard", "get_due_next_7_days", [currencyId]),
            this.orm.call("account.collection.dashboard", "get_due_soon_by_followup_level", [currencyId]),
            this.orm.call("account.collection.dashboard", "get_overdue_by_age", [currencyId]),
            this.orm.call("account.collection.dashboard", "get_top_overdue_partners", [currencyId]),
            this.orm.call("account.collection.dashboard", "get_bank_balances", []),
            this.orm.call("account.collection.dashboard", "get_fixed_fund_balance", []),
            this.orm.call("account.collection.dashboard", "get_cash_collections", [dateFrom, dateTo]),
            this.orm.call("account.collection.dashboard", "get_pending_reconciliation", []),
            this.orm.call("account.collection.dashboard", "get_third_party_checks_in_portfolio", []),
            this.orm.call("account.collection.dashboard", "get_pending_exchange_difference", []),
            this.orm.call("account.collection.dashboard", "get_collection_by_user", [dateFrom, dateTo]),
        ]);
        Object.assign(this.state, {
            currencies,
            totalReceivable,
            rejectedChecks,
            collectionTurnover,
            collectionPaymentRatio,
            customersWithDebt,
            undueDebt,
            dueToday,
            dueNext7Days,
            dueSoonByLevel,
            overdueByAge,
            topOverduePartners,
            bankBalances,
            fixedFund,
            cashCollections,
            pendingReconciliation,
            checksInPortfolio,
            pendingExchangeDifference,
            collectionByUser,
        });
    }

    onCurrencyChange(ev) {
        this.state.selectedCurrencyId = ev.target.value ? Number(ev.target.value) : null;
        this.fetchData();
    }

    onTurnoverPeriodChange(ev) {
        this.state.turnoverPeriod = ev.target.value;
        this.fetchData();
    }

    async onDrilldownClick(drilldown) {
        if (drilldown) {
            await this.action.doAction(drilldown);
        }
    }
}

registry.category("actions").add("account_collection_dashboard.dashboard", CollectionDashboard);
