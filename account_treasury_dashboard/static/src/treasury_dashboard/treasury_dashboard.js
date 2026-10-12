import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Layout } from "@web/search/layout";
import { useSetupAction } from "@web/search/action_hook";
import { _t } from "@web/core/l10n/translation";
import { deserializeDate, formatDate } from "@web/core/l10n/dates";
import { loadBundle } from "@web/core/assets";
import { isDarkMode } from "@dashboards_base/js/dashboards_theme";
import { TreasurySection } from "../treasury_section/treasury_section";
import { TreasuryDetailDialog } from "../treasury_detail_dialog/treasury_detail_dialog";
import { Component, onWillStart, useState } from "@odoo/owl";

/**
 * Treasury dashboard client action: one screen of collapsible sections.
 *
 * account.treasury.dashboard.get_dashboard() gives the frame (company,
 * today, visible sections); each section is then loaded by its own
 * get_section_data() call, in parallel, so that one that fails shows its
 * error in place while the others keep working. No business logic here:
 * figures come ready from the backend and are only formatted.
 */
export class TreasuryDashboard extends Component {
    static template = "account_treasury_dashboard.TreasuryDashboard";
    static components = { Layout, TreasurySection };
    static props = ["*"];

    isDarkMode = isDarkMode;

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.dialog = useService("dialog");
        this.labels = {
            refresh: _t("Refresh"),
            expandAll: _t("Expand all"),
            collapseAll: _t("Collapse all"),
            configure: _t("Settings"),
            asOf: _t("As of %s"),
            sectionFailed: _t("This section couldn't be loaded."),
        };
        // Collapsed sections survive a round trip through a drill-down
        // (breadcrumb back to the dashboard).
        const savedState = this.props.state?.treasuryDashboard || {};
        this.state = useState({
            frame: null,
            contents: {},
            collapsed: savedState.collapsed || {},
        });
        useSetupAction({
            getLocalState: () => ({ treasuryDashboard: { collapsed: this.state.collapsed } }),
        });
        onWillStart(async () => {
            await loadBundle("web.chartjs_lib");
            await this.load();
        });
    }

    get display() {
        return { controlPanel: {} };
    }

    get visibleSections() {
        return (this.state.frame?.sections || []).filter((section) => section.visible);
    }

    get asOfLabel() {
        return this.labels.asOf.replace("%s", formatDate(deserializeDate(this.state.frame.today)));
    }

    async load() {
        this.state.frame = await this.orm.call("account.treasury.dashboard", "get_dashboard", []);
        this.state.contents = {};
        for (const section of this.visibleSections) {
            this.state.contents[section.id] = { loading: true };
        }
        // Not awaited by onWillStart's caller on purpose: the frame shows
        // right away, and each section fills in as soon as it's ready.
        this.visibleSections.forEach((section) => this.loadSection(section.id));
    }

    async loadSection(sectionId) {
        this.state.contents[sectionId] = { loading: true };
        try {
            this.state.contents[sectionId] = await this.orm.call(
                "account.treasury.dashboard", "get_section_data", [sectionId]
            );
        } catch (error) {
            // A server error on this call (not a computed-section error,
            // which comes back as {error}) also stays in this section.
            this.state.contents[sectionId] = { error: error.data?.message || this.labels.sectionFailed };
        }
    }

    async refresh() {
        await this.load();
    }

    toggleSection(sectionId) {
        this.state.collapsed[sectionId] = !this.state.collapsed[sectionId];
    }

    setAllCollapsed(collapsed) {
        for (const section of this.visibleSections) {
            this.state.collapsed[section.id] = collapsed;
        }
    }

    openDrilldown(sectionId, drilldown) {
        this.dialog.add(TreasuryDetailDialog, { sectionId, drilldown });
    }

    async openConfiguration() {
        await this.action.doAction("account_treasury_dashboard.action_account_treasury_config");
    }
}

registry.category("actions").add("account_treasury_dashboard.dashboard", TreasuryDashboard);
