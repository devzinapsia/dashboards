import { _t } from "@web/core/l10n/translation";
import { deserializeDate, formatDate } from "@web/core/l10n/dates";
import { formatFloat, formatInteger, formatMonetary } from "@web/views/fields/formatters";

/**
 * Display text of a value sent by the backend (see the module's
 * models/treasury_blocks.py): {value, type, currency_id}. Display only:
 * amounts arrive unrounded and are only rounded here.
 *
 * @param {Object} cell
 * @returns {string}
 */
export function formatTreasuryValue(cell) {
    if (!cell) {
        return "";
    }
    const { value, type, currency_id: currencyId } = cell;
    if (value === false || value === null || value === undefined || value === "") {
        return type === "text" ? "" : "—";
    }
    switch (type) {
        case "monetary":
            return formatMonetary(value, { currencyId });
        case "integer":
            return formatInteger(value);
        case "float":
            return formatFloat(value, { digits: [16, 2] });
        case "percent":
            return `${formatFloat(value, { digits: [16, 1] })} %`;
        case "date":
            return formatDate(deserializeDate(value));
        case "days":
            return value === 1 ? _t("1 day") : _t("%s days", formatInteger(value));
        default:
            return String(value);
    }
}

/**
 * Whether a value is a negative amount (shown in red). Percentages are left
 * out: a drop is good news for outflows and bad news for inflows.
 */
export function isNegative(cell) {
    return Boolean(cell) && ["monetary", "float", "integer"].includes(cell.type) && cell.value < 0;
}
