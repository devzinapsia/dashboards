import { Dialog } from "@web/core/dialog/dialog";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { isDarkMode } from "@dashboards_base/js/dashboards_theme";
import { formatTreasuryValue, isNegative } from "../treasury_utils";
import { Component, onWillStart, useState } from "@odoo/owl";

/**
 * Drill-down popup of a treasury dashboard figure.
 *
 * Its content is computed on demand by
 * account.treasury.dashboard.get_drilldown() from the module's own data.
 * A row links to its record, and "View all" to the standard list, only when
 * the backend offers them (i.e. when the user can read that model).
 */
export class TreasuryDetailDialog extends Component {
    static template = "account_treasury_dashboard.TreasuryDetailDialog";
    static components = { Dialog };
    static props = {
        close: Function,
        sectionId: String,
        drilldown: Object,
    };

    isDarkMode = isDarkMode;
    formatValue = formatTreasuryValue;
    isNegative = isNegative;

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.labels = {
            loading: _t("Loading…"),
            empty: _t("Nothing to show."),
            total: _t("Total"),
            viewAll: _t("View all"),
            open: _t("Open"),
            detail: _t("Detail"),
        };
        this.state = useState({ loading: true, detail: null, error: null });
        onWillStart(() => this.load());
    }

    async load() {
        try {
            this.state.detail = await this.orm.call("account.treasury.dashboard", "get_drilldown", [
                this.props.sectionId,
                this.props.drilldown.key,
                this.props.drilldown.params,
            ]);
        } catch (error) {
            const message = error.data?.message;
            if (!message) {
                throw error;
            }
            this.state.error = message;
        } finally {
            this.state.loading = false;
        }
    }

    get title() {
        return this.state.detail?.title || this.labels.detail;
    }

    cellClass(column, cell) {
        return { "text-end": column.type !== "text", o_treasury_negative: isNegative(cell) };
    }

    async openRecord(row) {
        if (!row.record) {
            return;
        }
        await this.action.doAction({
            type: "ir.actions.act_window",
            res_model: row.record.model,
            res_id: row.record.id,
            views: [[false, "form"]],
            target: "current",
        });
        this.props.close();
    }

    async openList() {
        await this.action.doAction(this.state.detail.list_action);
        this.props.close();
    }
}
