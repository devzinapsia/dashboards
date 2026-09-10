import { cookie } from "@web/core/browser/cookie";

/**
 * Whether the user has dark mode active, resolved once from Odoo's own
 * theme cookie. Odoo's dark-theme CSS bundle isn't reliably loaded yet
 * by the time a plain ir.actions.client component like a dashboard
 * renders (unlike a regular list/form view, which triggers it itself),
 * so dashboard components read this cookie directly instead of relying
 * on CSS to adapt on its own.
 */
export const isDarkMode = cookie.get("color_scheme") === "dark";

/**
 * Axis tick label / grid line colors for Chart.js-based dashboard
 * charts. Chart.js renders to a <canvas>, so these can't be plain CSS
 * either way - they need a literal color resolved in JS.
 */
export const CHART_AXIS_TICK_COLOR = isDarkMode ? "#9095a6" : "#6c757d";
export const CHART_AXIS_GRID_COLOR = isDarkMode ? "rgba(255, 255, 255, .08)" : "rgba(0, 0, 0, .06)";
