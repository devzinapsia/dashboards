/**
 * Open a window action for a dashboard KPI drill-down.
 *
 * Thin wrapper around the "action" service so every concept dashboard opens
 * drill-downs the same way instead of building the action dict inline on
 * every KPI card.
 *
 * @param {import("@web/env").OdooEnv} env
 * @param {Object} params
 * @param {string} params.resModel
 * @param {Array} [params.domain]
 * @param {string} [params.viewType="list"]
 * @param {string} [params.name]
 * @param {Object} [params.context]
 */
export async function openDashboardDrilldown(env, params) {
    const { resModel, domain = [], viewType = "list", name, context = {} } = params;
    const viewModes = viewType === "form" ? ["form"] : [viewType, "form"];
    await env.services.action.doAction({
        type: "ir.actions.act_window",
        name,
        res_model: resModel,
        domain,
        views: viewModes.map((mode) => [false, mode]),
        target: "current",
        context,
    });
}
