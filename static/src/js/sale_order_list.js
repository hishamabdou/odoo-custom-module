/** @odoo-module **/
/**
 * Precious Metals Suite — Inventory Status Row Coloring (Odoo 19 / OWL)
 * Patches the List renderer to add a CSS class per inventory state value
 * on each <tr>, enabling distinct colors via CSS.
 */

import { patch } from "@web/core/utils/patch";
import { ListRenderer } from "@web/views/list/list_renderer";

const STATE_CLASS = {
    // ── Main Vault ──────────────────────────────────────────────────
    pending:                   "pm-inv-pending",
    waiting:                   "pm-inv-waiting",
    reserved:                  "pm-inv-reserved",
    reserved_waiting:          "pm-inv-reserved-waiting",
    custody_reserved:          "pm-inv-custody-reserved",
    custody_reserved_waiting:  "pm-inv-custody-reserved-waiting",
    custody_ready:             "pm-inv-custody-ready",
    custody_waiting:           "pm-inv-custody-waiting",
    sent_to_provider:          "pm-inv-sent-to-provider",
    batched:                   "pm-inv-batched",
    // ── Branch (same color as main vault equivalent) ────────────────
    waiting_in_branch:         "pm-inv-waiting",
    reserved_in_branch:        "pm-inv-reserved",
    reserved_waiting_in_branch: "pm-inv-reserved-waiting",
    custody_waiting_in_branch: "pm-inv-custody-waiting",
    custody_in_branch:         "pm-inv-custody-ready",
    custody_ready_in_branch:   "pm-inv-custody-ready",
    batched_in_branch:         "pm-inv-batched",
    batched_in_main_vault:     "pm-inv-batched",
};

const INV_FIELDS = new Set([
]);

patch(ListRenderer.prototype, {
    getRowClass(record) {
        const base = super.getRowClass(record);
        for (const fieldName of INV_FIELDS) {
            const val = record.data[fieldName];
            if (val && STATE_CLASS[val]) {
                return base + " " + STATE_CLASS[val];
            }
        }
        return base;
    },
});
