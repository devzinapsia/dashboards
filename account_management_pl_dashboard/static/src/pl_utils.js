/**
 * Whether a budget deviation is good or bad news: spending more than
 * budgeted is bad for costs, earning less than budgeted is bad for Income.
 * Shared by the grid and the drill-down popup.
 *
 * @param {string} section "income", "direct_cost" or "indirect_cost"
 * @param {number|null} deviation deviation in %
 * @returns {string} CSS class
 */
export function deviationClass(section, deviation) {
    if (deviation === null || deviation === undefined || Math.abs(deviation) < 0.05) {
        return "";
    }
    const favorable = section === "income" ? deviation > 0 : deviation < 0;
    return favorable ? "o_pl_favorable" : "o_pl_unfavorable";
}
