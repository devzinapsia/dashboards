import { formatFloat, formatMonetary } from "@web/views/fields/formatters";

/** Amount display scales offered by the dashboard's toolbar. */
export const AMOUNT_SCALES = {
    units: { divisor: 1, suffix: "" },
    k: { divisor: 1000, suffix: "K" },
    m: { divisor: 1000000, suffix: "M" },
};

/**
 * An amount as displayed by the dashboard: with its currency in units
 * (e.g. "$ 2.500,00"), or divided and suffixed in thousands / millions with
 * two decimals (e.g. "2,50 K"). Display only: amounts stay exact.
 *
 * @param {number} value
 * @param {number} currencyId
 * @param {string} scale "units", "k" or "m"
 * @returns {string}
 */
export function formatAmount(value, currencyId, scale = "units") {
    const { divisor, suffix } = AMOUNT_SCALES[scale] || AMOUNT_SCALES.units;
    if (!suffix) {
        return formatMonetary(value, { currencyId });
    }
    return `${formatFloat(value / divisor, { digits: [16, 2] })} ${suffix}`;
}

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
