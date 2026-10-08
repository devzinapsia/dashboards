import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Layout } from "@web/search/layout";
import { SelectMenu } from "@web/core/select_menu/select_menu";
import { useSetupAction } from "@web/search/action_hook";
import { formatMonetary, formatFloat } from "@web/views/fields/formatters";
import { _t } from "@web/core/l10n/translation";
import { deserializeDate, formatDate } from "@web/core/l10n/dates";
import { isDarkMode, CHART_AXIS_TICK_COLOR, CHART_AXIS_GRID_COLOR } from "@dashboards_base/js/dashboards_theme";
import { DashboardsChart } from "@dashboards_base/components/dashboard_chart/dashboard_chart";
import { PlDetailDialog } from "../pl_detail_dialog/pl_detail_dialog";
import { deviationClass } from "../pl_utils";
import { loadBundle } from "@web/core/assets";
import { Component, onWillStart, useState } from "@odoo/owl";

const { DateTime } = luxon;

const SEGMENT_LABELS_PLUGIN_ID = "accountManagementPlSegmentLabels";

/**
 * Chart.js plugin writing each stacked bar segment's percentage inside it
 * (when the segment is tall enough to hold the text). Registered once, and
 * only active on charts that enable it in options.plugins.
 */
function registerSegmentLabelsPlugin() {
    if (Chart.registry.plugins.get(SEGMENT_LABELS_PLUGIN_ID)) {
        return;
    }
    Chart.register({
        id: SEGMENT_LABELS_PLUGIN_ID,
        afterDatasetsDraw(chart) {
            const config = chart.options.plugins?.[SEGMENT_LABELS_PLUGIN_ID];
            if (!config?.enabled) {
                return;
            }
            const { ctx } = chart;
            ctx.save();
            ctx.font = "bold 12px sans-serif";
            ctx.fillStyle = "#fff";
            ctx.textAlign = "center";
            ctx.textBaseline = "middle";
            chart.data.datasets.forEach((dataset, datasetIndex) => {
                const meta = chart.getDatasetMeta(datasetIndex);
                if (meta.hidden) {
                    return;
                }
                meta.data.forEach((bar, index) => {
                    const label = config.labels?.[datasetIndex]?.[index];
                    const height = Math.abs(bar.base - bar.y);
                    if (label && height >= 16) {
                        ctx.fillText(label, bar.x, (bar.y + bar.base) / 2);
                    }
                });
            });
            ctx.restore();
        },
    });
}

const PERIOD_OPTIONS = [
    { value: "month", label: _t("Current month") },
    { value: "fiscal_year", label: _t("Current fiscal year") },
    { value: "previous_fiscal_year", label: _t("Previous fiscal year") },
    { value: "last_12", label: _t("Last 12 months") },
];

/**
 * Management P&L dashboard: a hierarchical grid (structure lines x months).
 *
 * Every figure comes ready from account.pl.dashboard.get_dashboard_data();
 * this component only handles display concerns (collapsing, formatting,
 * toolbar state). Amounts arrive unrounded and are only rounded here, when
 * formatted.
 */
export class PlDashboard extends Component {
    static template = "account_management_pl_dashboard.PlDashboard";
    static components = { Layout, SelectMenu, DashboardsChart };
    static props = ["*"];

    isDarkMode = isDarkMode;
    periodOptions = PERIOD_OPTIONS;

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.dialog = useService("dialog");
        this.labels = {
            grid: _t("Grid"),
            chart: _t("Chart"),
            chartAxis: _t("% of the month's total"),
            chartHelp: _t(
                "Each month's bar is its income + direct costs + indirect costs (100%), split by section."
            ),
            exportXlsx: _t("Export"),
            exportXlsxHelp: _t("Export the dashboard, as shown, to an Excel file"),
            expandAll: _t("Expand all"),
            collapseAll: _t("Collapse all"),
            refresh: _t("Refresh"),
            total: _t("Total"),
            noStructure: _t("There is no active management P&L structure for %s yet."),
            configure: _t("Configure the structure"),
            viewInCompanyCurrency: _t("View in company currency"),
            noAnalyticFilter: _t("No analytic filter"),
            allAnalyticAccounts: _t("Select analytic accounts or projects"),
            noBudgetSelected: _t("No budget"),
            withoutAssignments: _t("Shown as 0 until something is assigned to it."),
            budget: _t("Budget"),
            actual: _t("Actual"),
            deviation: _t("Deviation %"),
            notAvailable: _t("n/a"),
            noBudget: _t("—"),
            noBudgetHelp: _t("The budget is by account."),
            secondaryRateNote: _t(
                "Amounts in the company currency converted at the latest %(currency)s rate: %(rate)s (%(date)s), the same for every month; journal items made in %(currency)s keep their original amount."
            ),
            unassignedHelp: _t(
                "Control row: movements of P&L accounts not included in any line. " +
                "Not included in the totals. Net profit + Unassigned = accounting result of the period."
            ),
        };
        // Toolbar choices and collapsed rows survive a round trip through a
        // drill-down list (breadcrumb back to the dashboard).
        const savedState = this.props.state?.plDashboard || {};
        this.state = useState({
            loading: true,
            config: null,
            period: savedState.period || "fiscal_year",
            displayCurrency: savedState.displayCurrency || null,
            analyticPlanId: savedState.analyticPlanId || false,
            analyticAccounts: [],
            analyticIds: savedState.analyticIds || [],
            budgetId: savedState.budgetId || false,
            view: savedState.view || "grid",
            data: null,
            error: null,
            collapsed: savedState.collapsed || {},
        });
        useSetupAction({
            getLocalState: () => ({
                plDashboard: {
                    period: this.state.period,
                    displayCurrency: this.state.displayCurrency,
                    analyticPlanId: this.state.analyticPlanId,
                    analyticIds: this.state.analyticIds,
                    budgetId: this.state.budgetId,
                    view: this.state.view,
                    collapsed: this.state.collapsed,
                },
            }),
        });

        onWillStart(async () => {
            await loadBundle("web.chartjs_lib");
            registerSegmentLabelsPlugin();
            await this.load();
        });
    }

    get display() {
        return { controlPanel: {} };
    }

    async load() {
        const config = await this.orm.call("account.pl.dashboard", "get_dashboard_config", []);
        this.state.config = config;
        if (!config.has_structure) {
            this.state.loading = false;
            return;
        }
        this.state.displayCurrency = this.state.displayCurrency || config.default_display_currency;
        await this.loadAnalyticAccounts();
        await this.fetchData();
    }

    async fetchData() {
        this.state.loading = true;
        try {
            this.state.data = await this.orm.call(
                "account.pl.dashboard", "get_dashboard_data", [], this.requestParams
            );
            this.state.error = null;
        } catch (error) {
            // A missing exchange rate (UserError) is shown as a warning in
            // the dashboard itself, without breaking the screen; the company
            // currency stays one click away in the toolbar.
            const message = error.data?.message;
            if (!message) {
                throw error;
            }
            this.state.error = message;
            this.state.data = null;
        } finally {
            this.state.loading = false;
        }
    }

    get requestParams() {
        return {
            period: this.state.period,
            display_currency: this.state.displayCurrency,
            analytic_ids: this.state.analyticIds,
            budget_id: this.state.budgetId,
        };
    }

    // ---------------------------------------------------------------------
    // Chart
    // ---------------------------------------------------------------------

    setView(view) {
        this.state.view = view;
    }

    /**
     * Per month (the grid's columns, without the Total), the share of each
     * section in income + direct costs + indirect costs, as stacked bars
     * adding up to 100%. Negative section amounts (e.g. a month of credit
     * notes) count as 0 in the shares; the tooltip shows the real amount.
     */
    get chartSeries() {
        const data = this.state.data;
        const columns = data.columns.filter((column) => !column.is_total);
        const sections = [
            { key: "income", color: "#1f6fd1" },
            { key: "direct_cost", color: "#d93838" },
            { key: "indirect_cost", color: "#f28c28" },
        ].map((section) => ({
            ...section,
            row: data.rows.find((row) => row.kind === "section" && row.section === section.key),
        }));
        const totals = columns.map((column) =>
            sections.reduce((sum, section) => sum + Math.max(section.row?.values[column.key] || 0, 0), 0)
        );
        return { columns, sections, totals };
    }

    get chartData() {
        const { columns, sections, totals } = this.chartSeries;
        return {
            labels: columns.map((column) => this.columnLabel(column)),
            datasets: sections.map((section) => ({
                label: section.row?.name || section.key,
                backgroundColor: section.color,
                // Wide bars, like the grid's columns.
                barPercentage: 0.9,
                categoryPercentage: 0.8,
                data: columns.map((column, index) => {
                    const value = section.row?.values[column.key];
                    if (value === null || value === undefined || !totals[index]) {
                        return null;
                    }
                    return (Math.max(value, 0) / totals[index]) * 100;
                }),
                amounts: columns.map((column) => section.row?.values[column.key]),
            })),
        };
    }

    get chartOptions() {
        const currencyId = this.state.data.currency_id;
        return {
            plugins: {
                tooltip: {
                    callbacks: {
                        label: (ctx) => {
                            const amount = ctx.dataset.amounts[ctx.dataIndex];
                            return `${ctx.dataset.label}: ${formatFloat(ctx.parsed.y, { digits: [16, 1] })} % (${formatMonetary(amount, { currencyId })})`;
                        },
                    },
                },
                legend: { position: "top", align: "end", labels: { color: CHART_AXIS_TICK_COLOR } },
                [SEGMENT_LABELS_PLUGIN_ID]: {
                    enabled: true,
                    // Pre-formatted: Chart.js would call a function option itself.
                    labels: this.chartData.datasets.map((dataset) =>
                        dataset.data.map((value) => (value ? `${formatFloat(value, { digits: [16, 1] })} %` : ""))
                    ),
                },
            },
            scales: {
                x: {
                    stacked: true,
                    ticks: { color: CHART_AXIS_TICK_COLOR },
                    grid: { display: false },
                },
                y: {
                    stacked: true,
                    min: 0,
                    max: 100,
                    ticks: { color: CHART_AXIS_TICK_COLOR, callback: (value) => `${value} %` },
                    grid: { color: CHART_AXIS_GRID_COLOR },
                    title: { display: true, text: this.labels.chartAxis, color: CHART_AXIS_TICK_COLOR },
                },
            },
        };
    }

    /** The grid as shown (same toolbar choices) in an Excel file. */
    async exportXlsx() {
        const { filename, content } = await this.orm.call(
            "account.pl.dashboard", "get_dashboard_xlsx", [], this.requestParams
        );
        const bytes = Uint8Array.from(atob(content), (char) => char.charCodeAt(0));
        const url = URL.createObjectURL(
            new Blob([bytes], { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" })
        );
        const link = Object.assign(document.createElement("a"), { href: url, download: filename });
        link.click();
        URL.revokeObjectURL(url);
    }

    async refresh() {
        await this.load();
    }

    // ---------------------------------------------------------------------
    // Toolbar
    // ---------------------------------------------------------------------

    get currencyOptions() {
        const config = this.state.config;
        const options = [{ value: "company", label: config.company_currency_name }];
        if (config.secondary_currency_id) {
            options.push({ value: "secondary", label: config.secondary_currency_name });
        }
        return options;
    }

    get analyticChoices() {
        return this.state.analyticAccounts.map((option) => ({ value: option.id, label: option.name }));
    }

    /** Analytic accounts (or projects) of the selected plan, for the second filter. */
    async loadAnalyticAccounts() {
        this.state.analyticAccounts = this.state.analyticPlanId
            ? await this.orm.call("account.pl.dashboard", "get_analytic_accounts", [this.state.analyticPlanId])
            : [];
    }

    async onAnalyticPlanChange(ev) {
        this.state.analyticPlanId = ev.target.value ? Number(ev.target.value) : false;
        this.state.analyticIds = [];
        await this.loadAnalyticAccounts();
        // Choosing a plan alone doesn't filter anything yet: the analytic
        // accounts (or projects) to keep are picked next.
        if (!this.state.analyticPlanId) {
            this.fetchData();
        }
    }

    onBudgetChange(ev) {
        this.state.budgetId = ev.target.value ? Number(ev.target.value) : false;
        this.fetchData();
    }

    onPeriodChange(ev) {
        this.state.period = ev.target.value;
        this.fetchData();
    }

    onCurrencyChange(value) {
        if (value !== this.state.displayCurrency) {
            this.state.displayCurrency = value;
            this.fetchData();
        }
    }

    onAnalyticChange(values) {
        this.state.analyticIds = values;
        this.fetchData();
    }

    showCompanyCurrency() {
        this.onCurrencyChange("company");
    }

    expandAll() {
        this.state.collapsed = {};
    }

    collapseAll() {
        const collapsed = {};
        for (const row of this.state.data?.rows || []) {
            if (row.kind === "section" || row.kind === "group") {
                collapsed[row.key] = true;
            }
        }
        this.state.collapsed = collapsed;
    }

    async openConfiguration() {
        await this.action.doAction("account_management_pl_dashboard.action_account_pl_structure_config");
    }

    // ---------------------------------------------------------------------
    // Grid
    // ---------------------------------------------------------------------

    get columns() {
        return this.state.data?.columns || [];
    }

    get visibleRows() {
        const rows = this.state.data?.rows || [];
        const byKey = Object.fromEntries(rows.map((row) => [row.key, row]));
        return rows.filter((row) => {
            let parentKey = row.parent_key;
            while (parentKey) {
                if (this.state.collapsed[parentKey]) {
                    return false;
                }
                parentKey = byKey[parentKey]?.parent_key;
            }
            return true;
        });
    }

    isCollapsible(row) {
        return row.kind === "section" || row.kind === "group";
    }

    toggleRow(row) {
        if (this.isCollapsible(row)) {
            this.state.collapsed[row.key] = !this.state.collapsed[row.key];
        }
    }

    columnLabel(column) {
        if (column.is_total) {
            return this.labels.total;
        }
        return DateTime.fromISO(column.date_from).toFormat("LLL yyyy");
    }

    rowClass(row) {
        return {
            o_pl_row_section: row.kind === "section",
            o_pl_row_group: row.kind === "group",
            o_pl_row_leaf: row.kind === "leaf",
            o_pl_row_computed: row.kind.startsWith("computed_"),
            o_pl_row_computed_percent: row.kind === "computed_percent",
            o_pl_row_unassigned: row.kind === "unassigned",
        };
    }

    formatValue(row, column) {
        const value = row.values[column.key];
        if (value === null || value === undefined) {
            return "";
        }
        if (row.kind === "computed_percent") {
            return `${formatFloat(value, { digits: [16, 1] })} %`;
        }
        return formatMonetary(value, { currencyId: this.state.data.currency_id });
    }

    isCellClickable(row, column) {
        const value = row.values[column.key];
        return row.drilldown && !column.is_future && value !== null && value !== undefined;
    }

    openCell(row, column) {
        if (!this.isCellClickable(row, column)) {
            return;
        }
        this.dialog.add(PlDetailDialog, {
            rowKey: row.key,
            rowName: row.name,
            columnKey: column.key,
            columnLabel: this.columnLabel(column),
            requestParams: this.requestParams,
        });
    }

    // ---------------------------------------------------------------------
    // Budget
    // ---------------------------------------------------------------------

    get budgetShown() {
        return Boolean(this.state.data?.budget_shown);
    }

    /** "Month" period with budget: explicit Actual | Budget | Deviation columns. */
    get budgetSplitColumns() {
        return this.budgetShown && this.columns.length === 1;
    }

    hasBudgetLine(row) {
        return this.budgetShown && "budget" in row;
    }

    formatBudget(row, column) {
        const budget = row.budget[column.key];
        if (budget === null || budget === undefined) {
            return column.is_future ? "" : this.labels.noBudget;
        }
        return formatMonetary(budget, { currencyId: this.state.data.currency_id });
    }

    formatDeviation(row, column) {
        if (column.is_future) {
            return "";
        }
        const budget = row.budget[column.key];
        if (budget === null || budget === undefined) {
            return this.labels.noBudget;
        }
        const deviation = row.deviation[column.key];
        if (deviation === null || deviation === undefined) {
            return this.labels.notAvailable;
        }
        const sign = deviation > 0 ? "+" : "";
        return `${sign}${formatFloat(deviation, { digits: [16, 1] })} %`;
    }

    deviationClass(row, column) {
        return deviationClass(row.section, row.deviation?.[column.key]);
    }

    get secondaryRateNote() {
        const data = this.state.data;
        const rate = data?.secondary_rate;
        if (!rate) {
            return false;
        }
        return this.labels.secondaryRateNote
            .replaceAll("%(currency)s", data.currency_name)
            .replace("%(rate)s", formatMonetary(rate.value, { currencyId: rate.company_currency_id }))
            .replace("%(date)s", formatDate(deserializeDate(rate.date)));
    }

    isNegative(row, column) {
        const value = row.values[column.key];
        return typeof value === "number" && value < 0;
    }
}

registry.category("actions").add("account_management_pl_dashboard.dashboard", PlDashboard);
