# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import logging

_logger = logging.getLogger(__name__)


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    def action_multi_add_products(self):
        """Delegate to parent sale.order."""
        order = self.mapped('order_id')[:1]
        if not order:
            ctx = self.env.context
            active_id = ctx.get('active_id')
            if active_id:
                if ctx.get('active_model') == 'sale.order':
                    order = self.env['sale.order'].browse(active_id)
                elif ctx.get('active_model') == 'sale.order.line':
                    order = self.env['sale.order.line'].browse(active_id).order_id
        if not order:
            for aid in self.env.context.get('active_ids', []):
                rec = self.env['sale.order'].browse(aid).exists()
                if rec:
                    order = rec
                    break
        return order.action_multi_add_products() if order else {}


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    # NOTE: x_price_21 and x_weight_21 are defined ONCE, in gold_pricing.py
    # (x_weight_21 is a computed/stored field there). Do NOT redeclare them
    # here — a second field() declaration on the same model/name silently
    # overrides attributes from the first (e.g. it previously dropped the
    # `compute` on x_weight_21, turning it into a manually-editable field
    # and breaking auto-calculation from karat/weight).

    def write(self, vals):
        # Block x_price_21 edits after confirmation, unless the user holds
        # the dedicated "Edit Price 21 After Confirm/Post" permission.
        recompute_orders = self.browse()
        if 'x_price_21' in vals:
            for order in self:
                if order.x_price_21 == vals['x_price_21']:
                    continue
                if (order.state in ('sale', 'done')
                        and not self.env.user.has_group(
                            'precious_metals_suite.group_price21_edit_locked')):
                    raise UserError(_(
                        'Price 21 cannot be modified after the quotation has been confirmed.\n'
                        'Order: %s\n'
                        'Only users with the "Edit Price 21 After Confirm/Post" '
                        'permission can do this.'
                    ) % order.name)
                recompute_orders |= order
        res = super().write(vals)
        if recompute_orders:
            # Re-derive unit prices and totals from scratch, exactly as if
            # Price 21 had just been entered on a fresh quotation.
            for order in recompute_orders:
                for line in order.order_line:
                    line._compute_price_unit_from_gold()
        return res

    def action_bulk_confirm_quotations(self):
        """Confirm multiple quotations at once from the list view Actions menu."""
        confirmed, skipped, errors = [], [], []
        for order in self:
            if order.state not in ('draft', 'sent'):
                skipped.append(_('⏭ %s — already %s') % (order.name, order.state))
                continue
            try:
                order.action_confirm()
                confirmed.append(order.name)
            except Exception as e:
                errors.append(_('%s — %s') % (order.name, str(e)))
        parts = []
        if confirmed:
            parts.append(_('Confirmed (%d): %s') % (len(confirmed), ', '.join(confirmed)))
        if skipped:
            parts.append(_('⏭ Skipped (%d):\n%s') % (len(skipped), '\n'.join(skipped)))
        if errors:
            parts.append(_('Errors (%d):\n%s') % (len(errors), '\n'.join(errors)))
        msg_type = 'success' if confirmed and not errors else ('warning' if not errors else 'danger')
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Bulk Confirm — Done'),
                'message': '\n\n'.join(parts) or _('Nothing to confirm.'),
                'type': msg_type,
                'sticky': True,
            },
        }

    def action_multi_add_products(self):
        """Open the multi-add products wizard for this sale order."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Add Multiple Products',
            'res_model': 'sale.multi.add.products.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_order_id': self.id},
        }
