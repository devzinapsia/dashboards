import { registry } from "@web/core/registry";
import { CharField, charField } from "@web/views/fields/char/char_field";

/**
 * Char field that indents its content according to the record's "level"
 * field, so that a flat list of account.pl.structure.line records reads as
 * a tree. Group and section rows get a folder icon.
 */
export class PlIndentedCharField extends CharField {
    static template = "account_management_pl_dashboard.PlIndentedCharField";

    get indent() {
        return (this.props.record.data.level || 0) * 1.5;
    }

    get isGroup() {
        const data = this.props.record.data;
        return Boolean(data.is_root || data.is_group);
    }
}

registry.category("fields").add("pl_indented_char", {
    ...charField,
    component: PlIndentedCharField,
});
