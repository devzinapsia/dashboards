import { loadBundle } from "@web/core/assets";
import { Component, onWillStart, onWillUnmount, useEffect, useRef } from "@odoo/owl";

/**
 * Thin Chart.js wrapper shared by every dashboard: it only takes care of
 * loading the "web.chartjs_lib" bundle and (re)instantiating a Chart.js
 * canvas whenever its props change. Concept modules build the Chart.js
 * `type`/`data`/`options` themselves (this component does not add any
 * dashboard-specific logic).
 */
export class DashboardsChart extends Component {
    static template = "dashboards_base.DashboardChart";
    static props = {
        type: { type: String },
        data: { type: Object },
        options: { type: Object, optional: true },
    };

    setup() {
        this.canvasRef = useRef("canvas");
        this.chart = null;

        onWillStart(async () => {
            await loadBundle("web.chartjs_lib");
        });

        useEffect(() => this.renderChart());
        onWillUnmount(() => {
            this.chart?.destroy();
        });
    }

    renderChart() {
        this.chart?.destroy();
        this.chart = new Chart(this.canvasRef.el, {
            type: this.props.type,
            data: this.props.data,
            options: this.props.options || {},
        });
    }
}
