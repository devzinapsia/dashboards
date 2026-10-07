import { registry } from "@web/core/registry";
import { X2ManyField, x2ManyField } from "@web/views/fields/x2many/x2many_field";

// Same values as the server's END_SEQUENCE ("after the parent's last line")
// and INSERT_AFTER ("INSERT_AFTER + n: right after the sibling of sequence n").
const END_SEQUENCE = 1000000;
const INSERT_AFTER = 2000000;

/**
 * Lines of a management P&L structure: "Add a line" never creates a section
 * (there are exactly three). The new line goes:
 * - next to the row being edited (same parent, right after it);
 * - at the end of the section, when that row is a section;
 * - at the end of Indirect costs, when no row is being edited.
 */
export class PlStructureLinesField extends X2ManyField {
    async onAdd(params = {}) {
        const anchor = this.list.editedRecord;
        let parentId;
        let sequence = END_SEQUENCE;
        if (anchor && anchor.data.is_root) {
            parentId = anchor.resId;
        } else if (anchor && anchor.data.parent_id) {
            parentId = anchor.data.parent_id.id;
            sequence = INSERT_AFTER + anchor.data.sequence;
        } else {
            const indirectCosts = this.list.records.find(
                (record) => record.data.is_root && record.data.section === "indirect_cost"
            );
            parentId = indirectCosts?.resId;
        }
        const context = { ...(params.context || {}), default_sequence: sequence };
        if (parentId) {
            context.default_parent_id = parentId;
        }
        return super.onAdd({ ...params, context });
    }
}

registry.category("fields").add("pl_structure_lines", {
    ...x2ManyField,
    component: PlStructureLinesField,
});
