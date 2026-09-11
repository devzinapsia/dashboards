import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Layout } from "@web/search/layout";
import { formatMonetary } from "@web/views/fields/formatters";
import { today, serializeDate } from "@web/core/l10n/dates";
import { _t } from "@web/core/l10n/translation";
import { loadBundle } from "@web/core/assets";
import { DashboardsKpiCard } from "@dashboards_base/components/kpi_card/kpi_card";
import { DashboardsChart } from "@dashboards_base/components/dashboard_chart/dashboard_chart";
import { isDarkMode, CHART_AXIS_TICK_COLOR, CHART_AXIS_GRID_COLOR } from "@dashboards_base/js/dashboards_theme";
import { Component, onWillStart, useState } from "@odoo/owl";

const COLLECTION_PROJECTION_LABELS_PLUGIN_ID = "accountCollectionDashboardProjectionLabels";

export class CollectionDashboard extends Component {
    static template = "account_collection_dashboard.CollectionDashboard";
    static components = { Layout, DashboardsKpiCard, DashboardsChart };
    static props = ["*"];

    isDarkMode = isDarkMode;

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.labels = {
            totalReceivable: _t("Total receivable"),
            rejectedChecks: _t("Rejected checks"),
            collectionTurnover: _t("Collection turnover"),
            collectionPaymentRatio: _t("Collection/Payment ratio"),
            overdueDebt: _t("Overdue debt"),
            undueDebt: _t("Not yet due"),
            dueToday: _t("Due today"),
            dueNext7Days: _t("Due in 7 days"),
            topSlowPayingCustomers: _t("Top 10 - Slowest paying customers (average days)"),
            collectionProjection: _t("Collection projection"),
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
            overdueDebt: null,
            undueDebt: null,
            dueToday: null,
            dueNext7Days: null,
            topSlowPayingCustomers: [],
            collectionProjection: [],
        });

        onWillStart(async () => {
            await loadBundle("web.chartjs_lib");
            this.registerChartPlugins();
            await this.fetchData();
        });
    }

    get display() {
        return { controlPanel: {} };
    }

    formatMonetary(value, currencyId) {
        return formatMonetary(value || 0, { currencyId });
    }

    registerChartPlugins() {
        if (Chart.registry.plugins.get(COLLECTION_PROJECTION_LABELS_PLUGIN_ID)) {
            return;
        }
        Chart.register({
            id: COLLECTION_PROJECTION_LABELS_PLUGIN_ID,
            afterDatasetsDraw(chart) {
                const values = chart.options.plugins?.[COLLECTION_PROJECTION_LABELS_PLUGIN_ID]?.values;
                if (!values) {
                    return;
                }
                const { ctx } = chart;
                ctx.save();
                ctx.fillStyle = CHART_AXIS_TICK_COLOR;
                ctx.font = "12px sans-serif";
                ctx.textAlign = "center";
                ctx.textBaseline = "bottom";
                chart.getDatasetMeta(0).data.forEach((bar, index) => {
                    const label = values[index];
                    if (label !== undefined) {
                        ctx.fillText(label, bar.x, bar.y - 4);
                    }
                });
                ctx.restore();
            },
        });
    }

    get topSlowPayingCustomersChartData() {
        const rows = this.state.topSlowPayingCustomers;
        return {
            labels: rows.map((row) => row.partner_name),
            datasets: [{ data: rows.map((row) => row.days), backgroundColor: "#4285f4" }],
        };
    }

    get topSlowPayingCustomersChartOptions() {
        return {
            indexAxis: "y",
            plugins: { legend: { display: false } },
            scales: {
                x: {
                    title: { display: true, text: _t("Days"), color: CHART_AXIS_TICK_COLOR },
                    ticks: { color: CHART_AXIS_TICK_COLOR },
                    grid: { color: CHART_AXIS_GRID_COLOR },
                },
                y: {
                    title: { display: true, text: _t("Customer"), color: CHART_AXIS_TICK_COLOR },
                    ticks: { color: CHART_AXIS_TICK_COLOR },
                    grid: { color: CHART_AXIS_GRID_COLOR },
                },
            },
        };
    }

    get collectionProjectionChartData() {
        const buckets = this.state.collectionProjection;
        return {
            labels: buckets.map((bucket) => bucket.label),
            datasets: [{
                data: buckets.map((bucket) => bucket.amount),
                backgroundColor: "#4285f4",
            }],
        };
    }

    get collectionProjectionChartOptions() {
        const buckets = this.state.collectionProjection;
        const currencyId = buckets[0]?.currency_id;
        return {
            plugins: {
                legend: { display: false },
                [COLLECTION_PROJECTION_LABELS_PLUGIN_ID]: {
                    values: buckets.map((bucket) => `${bucket.percentage.toFixed(1)}%`),
                },
                tooltip: {
                    callbacks: {
                        label: (ctx) => this.formatMonetary(ctx.parsed.y, currencyId),
                    },
                },
            },
            scales: {
                x: {
                    ticks: { color: CHART_AXIS_TICK_COLOR },
                    grid: { color: CHART_AXIS_GRID_COLOR },
                },
                y: {
                    title: { display: true, text: _t("Balance"), color: CHART_AXIS_TICK_COLOR },
                    ticks: {
                        callback: (value) => this.formatMonetary(value, currencyId),
                        color: CHART_AXIS_TICK_COLOR,
                    },
                    grid: { color: CHART_AXIS_GRID_COLOR },
                },
            },
        };
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
            overdueDebt,
            undueDebt,
            dueToday,
            dueNext7Days,
            topSlowPayingCustomers,
            collectionProjection,
        ] = await Promise.all([
            this.orm.call("account.collection.dashboard", "get_active_currencies", []),
            this.orm.call("account.collection.dashboard", "get_total_receivable", [currencyId]),
            this.orm.call("account.collection.dashboard", "get_rejected_checks", [currencyId]),
            this.orm.call("account.collection.dashboard", "get_collection_turnover", [this.state.turnoverPeriod]),
            this.orm.call("account.collection.dashboard", "get_collection_payment_ratio", [dateFrom, dateTo]),
            this.orm.call("account.collection.dashboard", "get_overdue_debt", [currencyId]),
            this.orm.call("account.collection.dashboard", "get_undue_debt", [currencyId]),
            this.orm.call("account.collection.dashboard", "get_due_today", [currencyId]),
            this.orm.call("account.collection.dashboard", "get_due_next_7_days", [currencyId]),
            this.orm.call("account.collection.dashboard", "get_top_slow_paying_customers", [this.state.turnoverPeriod]),
            this.orm.call("account.collection.dashboard", "get_collection_projection", [currencyId]),
        ]);
        Object.assign(this.state, {
            currencies,
            totalReceivable,
            rejectedChecks,
            collectionTurnover,
            collectionPaymentRatio,
            overdueDebt,
            undueDebt,
            dueToday,
            dueNext7Days,
            topSlowPayingCustomers,
            collectionProjection,
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
