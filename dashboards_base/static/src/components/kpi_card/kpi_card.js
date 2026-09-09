import { Component } from "@odoo/owl";

/**
 * Generic KPI tile: a title, a main value, an optional secondary value, and
 * an optional click handler for drill-down (combine with
 * @see openDashboardDrilldown from "@dashboards_base/js/drilldown").
 *
 * A default slot is also available for concept dashboards that need to add
 * extra content inside the card (e.g. a small chart, a badge, ...).
 */
export class DashboardsKpiCard extends Component {
    static template = "dashboards_base.KpiCard";
    static props = {
        title: { type: String },
        value: { type: [String, Number] },
        secondaryValue: { type: [String, Number], optional: true },
        onClick: { type: Function, optional: true },
        slots: { type: Object, optional: true },
    };

    get isClickable() {
        return Boolean(this.props.onClick);
    }

    onCardClick() {
        this.props.onClick?.();
    }
}
