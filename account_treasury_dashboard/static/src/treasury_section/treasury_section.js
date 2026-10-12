import { _t } from "@web/core/l10n/translation";
import { formatMonetary } from "@web/views/fields/formatters";
import { DashboardsKpiCard } from "@dashboards_base/components/kpi_card/kpi_card";
import { DashboardsChart } from "@dashboards_base/components/dashboard_chart/dashboard_chart";
import { isDarkMode, CHART_AXIS_TICK_COLOR, CHART_AXIS_GRID_COLOR } from "@dashboards_base/js/dashboards_theme";
import { formatTreasuryValue, isNegative } from "../treasury_utils";
import { Component } from "@odoo/owl";

// Chart colors: Chart.js draws on a <canvas>, so they are literal values
// resolved from the theme (see dashboards_base's dashboards_theme.js).
const CHART_BAR_POSITIVE = isDarkMode ? "rgba(86, 211, 100, .55)" : "rgba(30, 132, 73, .55)";
const CHART_BAR_NEGATIVE = isDarkMode ? "rgba(255, 123, 114, .6)" : "rgba(192, 57, 43, .55)";
const CHART_LINE = isDarkMode ? "#6cb6ff" : "#2c6fbb";
const CHART_ZERO_LINE = isDarkMode ? "rgba(255, 255, 255, .45)" : "rgba(0, 0, 0, .45)";

/**
 * One collapsible section of the treasury dashboard.
 *
 * It renders whatever generic blocks its backend method returned (cards,
 * tables, charts and alerts, see models/treasury_blocks.py) without knowing
 * which section it is, so that a section added by another module needs no
 * JavaScript of its own.
 */
export class TreasurySection extends Component {
    static template = "account_treasury_dashboard.TreasurySection";
    static components = { DashboardsKpiCard, DashboardsChart };
    static props = {
        section: Object,
        content: Object,
        collapsed: Boolean,
        onToggle: Function,
        onDrilldown: Function,
        onRetry: Function,
    };

    isDarkMode = isDarkMode;
    formatValue = formatTreasuryValue;
    isNegative = isNegative;
    labels = {
        loading: _t("Loading…"),
        retry: _t("Retry"),
        empty: _t("Nothing to show."),
    };

    cellClass(column, cell) {
        return {
            "text-end": column.type !== "text",
            o_treasury_negative: isNegative(cell),
            o_treasury_clickable: Boolean(cell?.drilldown),
            [`o_treasury_alert_${cell?.alert}`]: Boolean(cell?.alert),
        };
    }

    hasCount(cell) {
        return Boolean(cell) && cell.count !== false && cell.count !== undefined;
    }

    onCellClick(cell) {
        if (cell?.drilldown) {
            this.props.onDrilldown(this.props.section.id, cell.drilldown);
        }
    }

    cardClickHandler(item) {
        return item.main.drilldown ? () => this.onCellClick(item.main) : undefined;
    }

    alertIcon(level) {
        return level === "info" ? "fa-info-circle" : "fa-exclamation-triangle";
    }

    chartConfig(block) {
        const currencyId = block.currency_id;
        const format = (value) => (currencyId ? formatMonetary(value, { currencyId }) : String(value));
        const datasets = block.series.map((serie) => {
            if (serie.kind === "line") {
                return {
                    type: "line",
                    label: serie.label,
                    data: serie.values,
                    borderColor: CHART_LINE,
                    backgroundColor: CHART_LINE,
                    tension: 0.2,
                    order: 0,
                };
            }
            return {
                type: "bar",
                label: serie.label,
                data: serie.values,
                backgroundColor: serie.values.map((value) => (value < 0 ? CHART_BAR_NEGATIVE : CHART_BAR_POSITIVE)),
                order: 1,
            };
        });
        return {
            type: "bar",
            data: { labels: block.labels, datasets },
            options: {
                plugins: {
                    legend: { labels: { color: CHART_AXIS_TICK_COLOR } },
                    tooltip: {
                        callbacks: { label: (context) => `${context.dataset.label}: ${format(context.parsed.y)}` },
                    },
                },
                scales: {
                    x: { ticks: { color: CHART_AXIS_TICK_COLOR }, grid: { color: CHART_AXIS_GRID_COLOR } },
                    y: {
                        ticks: { color: CHART_AXIS_TICK_COLOR, callback: (value) => format(value) },
                        grid: {
                            color: (context) =>
                                block.zero_line && context.tick?.value === 0 ? CHART_ZERO_LINE : CHART_AXIS_GRID_COLOR,
                            lineWidth: (context) => (block.zero_line && context.tick?.value === 0 ? 2 : 1),
                        },
                    },
                },
            },
        };
    }
}
