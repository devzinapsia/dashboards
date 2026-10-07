import { Dialog } from "@web/core/dialog/dialog";
import { useService } from "@web/core/utils/hooks";
import { formatFloat, formatMonetary } from "@web/views/fields/formatters";
import { _t } from "@web/core/l10n/translation";
import { isDarkMode } from "@dashboards_base/js/dashboards_theme";
import { deviationClass } from "../pl_utils";
import { Component, onWillStart, useState } from "@odoo/owl";

/**
 * Drill-down popup of a management P&L cell.
 *
 * Its content is loaded on demand (account.pl.dashboard.get_cell_detail),
 * never with the grid. A section or group lists its leaves, which can be
 * opened in place (with a "back" breadcrumb); a leaf lists its accounts,
 * customers or analytic accounts, which open the underlying journal items
 * (or analytic lines) in a regular list view.
 */
export class PlDetailDialog extends Component {
    static template = "account_management_pl_dashboard.PlDetailDialog";
    static components = { Dialog };
    static props = {
        close: Function,
        rowKey: String,
        rowName: String,
        columnKey: String,
        columnLabel: String,
        requestParams: Object,
    };

    isDarkMode = isDarkMode;

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.labels = {
            back: _t("Back"),
            close: _t("Close"),
            total: _t("Total"),
            amount: _t("Amount"),
            code: _t("Code"),
            empty: _t("No movements in this period."),
            line: _t("Line"),
            detail: _t("Detail"),
            budget: _t("Budget"),
            deviation: _t("Deviation %"),
            notAvailable: _t("n/a"),
            noBudget: _t("—"),
        };
        this.state = useState({ stack: [], loading: true });
        onWillStart(() => this.push(this.props.rowKey, this.props.rowName));
    }

    get current() {
        return this.state.stack[this.state.stack.length - 1];
    }

    get title() {
        return `${this.state.stack.map((level) => level.name).join(" › ")} — ${this.props.columnLabel}`;
    }

    get secondaryNote() {
        const detail = this.current?.detail;
        if (!detail || detail.display_currency !== "secondary") {
            return false;
        }
        return _t(
            "Amounts in the secondary currency. The journal item lists open in %s (company currency) and can't total in the secondary currency.",
            detail.company_currency_name
        );
    }

    get hasCodes() {
        return this.current.detail.entries.some((entry) => entry.code);
    }

    async push(rowKey, name) {
        this.state.loading = true;
        const detail = await this.orm.call(
            "account.pl.dashboard",
            "get_cell_detail",
            [rowKey, this.props.columnKey],
            this.props.requestParams
        );
        this.state.stack.push({ rowKey, name, detail });
        this.state.loading = false;
    }

    back() {
        if (this.state.stack.length > 1) {
            this.state.stack.pop();
        }
    }

    formatBudget(budget) {
        return budget === null || budget === undefined ? this.labels.noBudget : this.formatAmount(budget);
    }

    formatDeviation(budget, deviation) {
        if (budget === null || budget === undefined) {
            return this.labels.noBudget;
        }
        if (deviation === null || deviation === undefined) {
            return this.labels.notAvailable;
        }
        return `${deviation > 0 ? "+" : ""}${formatFloat(deviation, { digits: [16, 1] })} %`;
    }

    deviationClass(deviation) {
        return deviationClass(this.current.detail.section, deviation);
    }

    formatAmount(value) {
        return formatMonetary(value, { currencyId: this.current.detail.currency_id });
    }

    async onEntryClick(entry) {
        if (entry.open === "line") {
            await this.push(entry.key, entry.label);
        } else if (entry.open === "items") {
            const action = await this.orm.call(
                "account.pl.dashboard",
                "get_detail_action",
                [this.current.rowKey, this.props.columnKey, entry.key],
                this.props.requestParams
            );
            this.props.close();
            await this.action.doAction(action);
        }
    }
}
