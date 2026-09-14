# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, AccessError
from markupsafe import Markup
import logging

_logger = logging.getLogger(__name__)


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    division_delivery = fields.Boolean(
        string='Channel Delivery',
        default=False,
        help='This picking was created by the Channel Inventory system',
    )

    is_locked = fields.Boolean(
        string='Locked',
        default=False,
        copy=False,
        help='When True the Details tab is read-only. Use Lock/Unlock buttons.',
    )

    metal_done_w21 = fields.Float(
        string='Done W21',
        compute='_compute_metal_done_w21',
        store=True,
        digits=(16, 4),
        help='Sum of Done W21 across all moves (product.weight_21 × quantity done).',
    )

    metal_demand_w21 = fields.Float(
        string='Demand W21',
        compute='_compute_metal_demand_w21',
        store=True,
        digits=(16, 4),
        help='Sum of Demand W21 across all moves (product.weight_21 × quantity).',
    )

    metal_reserved_w21 = fields.Float(
        string='Reserved W21',
        compute='_compute_metal_reserved_w21',
        store=False,
        digits=(16, 4),
        help='Sum of Reserved W21 across all moves (product.weight_21 × reserved qty).',
    )

    # ── Re-declare weight & shipping_weight to override parent compute ────
    # IMPORTANT: We re-declare the fields here so Odoo uses OUR compute method
    # and OUR depends chain. Without this, Odoo 18 ignores the overridden method
    # and uses the parent's depends, causing weight to stay 0.
    weight = fields.Float(
        compute='_cal_weight',
        digits=(16, 4),
        store=True,
        string='Weight (g)',
    )

    shipping_weight = fields.Float(
        compute='_compute_shipping_weight',
        digits=(16, 4),
        store=True,
        string='Weight for shipping (g)',
    )

    @api.depends('move_ids.move_line_ids.quantity', 'move_ids.move_line_ids.product_id', 'state')
    def _compute_metal_done_w21(self):
        from decimal import Decimal
        for picking in self:
            # Only show Done W21 after the picking is fully validated
            if picking.state != 'done':
                picking.metal_done_w21 = 0.0
                continue
            total = Decimal('0')
            for move in picking.move_ids.filtered(
                lambda m: m.state not in ('cancel',)
            ):
                w21_unit = Decimal(str(
                    getattr(move.product_id, 'weight_21', 0.0) or 0.0
                ))
                qty_done = Decimal(str(sum(
                    line.quantity for line in move.move_line_ids
                ) or 0.0))
                total += w21_unit * qty_done
            picking.metal_done_w21 = float(total)

    @api.depends(
        'move_ids.product_qty',
        'move_ids.product_id',
        'move_ids.product_id.weight_21',
    )
    def _compute_metal_demand_w21(self):
        from decimal import Decimal
        for picking in self:
            total = Decimal('0')
            for move in picking.move_ids.filtered(
                lambda m: m.state not in ('cancel',)
            ):
                w21_unit = Decimal(str(
                    getattr(move.product_id, 'weight_21', 0.0) or 0.0
                ))
                qty_demand = Decimal(str(move.product_qty or 0.0))
                total += w21_unit * qty_demand
            picking.metal_demand_w21 = float(total)

    @api.depends('move_ids.move_line_ids.quantity', 'move_ids.product_id.weight_21', 'state')
    def _compute_metal_reserved_w21(self):
        from decimal import Decimal
        for picking in self:
            if picking.state == 'done':
                picking.metal_reserved_w21 = 0.0
                continue
            total = Decimal('0')
            for move in picking.move_ids.filtered(lambda m: m.state not in ('cancel', 'done')):
                w21 = Decimal(str(getattr(move.product_id, 'weight_21', 0.0) or 0.0))
                reserved = Decimal(str(sum(move.move_line_ids.mapped('quantity')) or 0.0))
                total += w21 * reserved
            picking.metal_reserved_w21 = float(total)

    @api.depends('move_ids.move_line_ids.quantity', 'move_ids.move_line_ids.product_id', 'metal_done_w21')
    def _cal_weight(self):
        """Override: weight = metal_done_w21 (grams, not kg)."""
        for picking in self:
            picking.weight = picking.metal_done_w21

    @api.depends('move_ids.move_line_ids.quantity', 'move_ids.move_line_ids.product_id', 'metal_done_w21')
    def _compute_shipping_weight(self):
        """Override: shipping_weight = metal_done_w21 (grams)."""
        for picking in self:
            picking.shipping_weight = picking.metal_done_w21

    def _log_lock_action(self, action_label, extra_note=''):
        """Post a chatter note describing a lock/unlock action."""
        import pytz
        from datetime import datetime
        user = self.env.user
        try:
            tz = pytz.timezone(user.tz or 'UTC')
            now_local = datetime.utcnow().replace(tzinfo=pytz.utc).astimezone(tz)
            ts = now_local.strftime('%Y-%m-%d %H:%M:%S') + ' (' + (user.tz or 'UTC') + ')'
        except Exception:
            ts = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S') + ' (UTC)'

        body = Markup(
            '<p style="margin:0;"><b>%s</b><br/>'
            'By: <b>%s</b> &nbsp;|&nbsp; %s%s</p>'
        ) % (
            action_label,
            user.name,
            ts,
            Markup('<br/>') + Markup(extra_note) if extra_note else Markup(''),
        )
        self.message_post(body=body)

    def action_lock(self):
        """
        Lock — set is_locked=True.
        Any group_user and above can lock.
        Only Managers/Admins can unlock (enforced in action_reset_to_draft).
        """
        for picking in self:
            if picking.state == 'cancel':
                raise UserError(_('Cannot lock a cancelled transfer.'))
            picking.write({'is_locked': True})
            picking._log_lock_action(
                'Transfer Locked',
                'Details tab is now read-only. Only Managers can unlock.',
            )

    def action_reset_to_draft(self):
        """
        Unlock entry-point — permission check first, then open wizard.
        The wizard collects the mandatory reason and calls
        pm.unlock.reason.wizard.action_confirm_unlock() to do the actual work.

        Permission:
          • group_manager (includes group_admin) → open wizard
          • group_user only                       → AccessError
        """
        self.ensure_one()

        # ── Permission check ─────────────────────────────────────────────────
        if not self.env.user.has_group('precious_metals_suite.group_manager'):
            raise AccessError(_(
                'You do not have permission to unlock a transfer. '
                'Only Precious Metals Managers and Administrators can do this.'
            ))

        if self.state == 'cancel':
            raise UserError(_('Cannot unlock a cancelled transfer.'))

        # ── Open the reason wizard ───────────────────────────────────────────
        wizard = self.env['pm.unlock.reason.wizard'].create({
            'picking_id': self.id,
        })
        return {
            'type':      'ir.actions.act_window',
            'name':      _('Unlock Transfer — Reason Required'),
            'res_model': 'pm.unlock.reason.wizard',
            'res_id':    wizard.id,
            'view_mode': 'form',
            'target':    'new',
        }

    # ── Validate: demand must equal done before allowing validation ────────
    def button_validate(self):
        """
        Behavior depends on Settings → Inventory → Precious Metals Suite →
        "Allow Backorders on Incomplete Transfers" (pm_allow_backorder):

          - ENABLED  (default): do nothing custom — defer entirely to Odoo's
            native button_validate(), which shows the standard backorder
            dialog (Create Backorder / No Backorder / Cancel) when Demand
            != Done. This is the normal, familiar Odoo flow.

          - DISABLED: block validation with a clear error whenever any move
            is incomplete (Demand != Done). No backorder can be created;
            the user must fill in all done quantities to match demand.
        """
        allow_backorder = self.env['ir.config_parameter'].sudo().get_param(
            'precious_metals_suite.allow_backorder', 'True'
        ) in ('True', 'true', '1')

        if allow_backorder:
            return super().button_validate()

        from decimal import Decimal

        TOLERANCE = Decimal('0.0001')

        incomplete = []
        for picking in self:
            if picking.state in ('done', 'cancel'):
                continue
            for move in picking.move_ids.filtered(lambda m: m.state not in ('done', 'cancel')):
                qty_demand = Decimal(str(move.product_uom_qty or 0.0))
                qty_done   = Decimal(str(
                    sum(line.quantity for line in move.move_line_ids) or 0.0
                ))

                w21_demand = Decimal(str(move.move_demand_w21 or 0.0))
                w21_done   = Decimal(str(move.move_done_w21   or 0.0))

                qty_ok = abs(qty_demand - qty_done)   <= TOLERANCE or qty_demand == 0
                w21_ok = abs(w21_demand - w21_done)   <= TOLERANCE or w21_demand == 0

                if not (qty_ok or w21_ok):
                    incomplete.append(
                        _('• %(product)s  |  Demand: %(demand)s → Reserve: %(done)s') % {
                            'product': move.product_id.display_name,
                            'demand':  float(qty_demand),
                            'done':    float(qty_done),
                            'w21d':    float(w21_demand),
                            'w21o':    float(w21_done),
                        }
                    )

        if incomplete:
            raise UserError(
                _('The following products are not fully processed:\n\n%(lines)s\n\n'
                  'Every product must be fully done (Demand = Reserve) before validating.\n') % {
                    'lines': '\n'.join(incomplete),
                }
            )

        return super().button_validate()

    def _action_done(self):
        """
        After validating, auto-lock the picking.
        """
        result = super()._action_done()
        # Auto-lock: lock the picking immediately after validation
        for picking in self:
            if picking.state == 'done' and not picking.is_locked:
                picking.write({'is_locked': True})
                picking._log_lock_action(
                    'Transfer Locked Automatically',
                    'Picking was validated and locked automatically. Click Unlock to edit.',
                )
        return result


class StockQuant(models.Model):
    """weight_21 and metal_type on stock.quant — shown in Inventory list."""
    _inherit = 'stock.quant'

    x_metal_type = fields.Selection(
        related='product_id.x_metal_type',
        string='Metal Type',
        store=True, readonly=True,
    )
    weight_21_unit = fields.Float(
        related='product_id.weight_21',
        string='Weight21/Unit',
        store=True, readonly=True,
        digits=(16, 6),
    )
    total_weight_21_quant = fields.Float(
        string='Weight 21',
        compute='_compute_quant_weight21',
        store=True, readonly=True,
        digits=(16, 6),
        help='quantity × weight_21/unit (full precision stored for accurate totals)',
    )

    @api.depends('quantity', 'weight_21_unit', 'product_id')
    def _compute_quant_weight21(self):
        from decimal import Decimal
        for quant in self:
            w = quant.weight_21_unit or 0.0
            qty = quant.quantity or 0.0
            if w and qty:
                quant.total_weight_21_quant = float(Decimal(str(qty)) * Decimal(str(w)))
            else:
                quant.total_weight_21_quant = 0.0


class StockMoveLineW21(models.Model):
    """
    Extend stock.move.line with weight_21 — shown in Operations list views.
    weight_21 = product.weight_21 × quantity (done qty).
    """
    _inherit = 'stock.move.line'

    weight_21 = fields.Float(
        string='Weight 21 (g)',
        compute='_compute_move_line_weight_21',
        store=True,
        digits=(16, 4),
        help='Done W21: product.weight_21 × quantity done.',
    )

    @api.depends('product_id', 'product_id.weight_21', 'quantity')
    def _compute_move_line_weight_21(self):
        from decimal import Decimal
        for line in self:
            w21_unit = Decimal(str(
                getattr(line.product_id, 'weight_21', 0.0) or 0.0
            ))
            qty = Decimal(str(line.quantity or 0.0))
            line.weight_21 = float(w21_unit * qty)


class StockMoveW21(models.Model):
    """
    Extend stock.move with W21 weight fields + reserved qty fields.
    - move_done_w21    : Done W21 (g) — shown in Moves list
    - move_demand_w21  : Demand W21 (g) — shown in Moves list
    - metal_reserved_qty : Reserved quantity (from move lines before validate)
    - metal_reserved_w21 : Reserved W21 weight
    - metal_done_qty_display : Done qty — 0 until picking is validated
    - metal_demand_w21 / metal_done_w21 : used in Details tab (metal_manufacturing compat)
    """
    _inherit = 'stock.move'

    move_done_w21 = fields.Float(
        string='Done W21 (g)',
        compute='_compute_move_done_w21',
        store=True,
        digits=(16, 4),
        help='Done W21: product.weight_21 × sum of done quantity on move lines.',
    )
    move_demand_w21 = fields.Float(
        string='Demand W21 (g)',
        compute='_compute_move_demand_w21',
        store=True,
        digits=(16, 4),
        help='Demand W21: product.weight_21 × product_uom_qty.',
    )

    # ── Fields for Details tab (Reserved + Done display) ─────────────────
    metal_demand_w21 = fields.Float(
        string='Demand W21',
        compute='_compute_metal_details_w21',
        digits=(16, 4),
    )
    metal_reserved_qty = fields.Float(
        string='Reserved Qty',
        compute='_compute_metal_details_w21',
        digits=(16, 3),
        help='Quantity reserved — sum of move lines before validation.',
    )
    metal_reserved_w21 = fields.Float(
        string='Reserved W21',
        compute='_compute_metal_details_w21',
        digits=(16, 4),
        help='W21 weight for the reserved quantity.',
    )
    metal_done_qty_display = fields.Float(
        string='Done Qty',
        compute='_compute_metal_details_w21',
        digits=(16, 3),
        help='Done quantity — 0 until the picking is validated.',
    )
    metal_done_w21 = fields.Float(
        string='Done W21',
        compute='_compute_metal_details_w21',
        digits=(16, 4),
        help='W21 weight for done quantity — 0 until validated.',
    )

    @api.depends('move_line_ids.quantity', 'move_line_ids.product_id',
                 'product_id.weight_21', 'state', 'picking_id.state')
    def _compute_move_done_w21(self):
        from decimal import Decimal
        for move in self:
            # Only show Done W21 after the picking is fully validated
            picking_done = (
                move.picking_id.state == 'done' if move.picking_id
                else move.state == 'done'
            )
            if move.state == 'cancel' or not picking_done:
                move.move_done_w21 = 0.0
                continue
            w21_unit = Decimal(str(getattr(move.product_id, 'weight_21', 0.0) or 0.0))
            qty_done = Decimal(str(sum(line.quantity for line in move.move_line_ids) or 0.0))
            move.move_done_w21 = float(w21_unit * qty_done)

    @api.depends('product_uom_qty', 'product_id', 'product_id.weight_21')
    def _compute_move_demand_w21(self):
        from decimal import Decimal
        for move in self:
            if move.state == 'cancel':
                move.move_demand_w21 = 0.0
                continue
            w21_unit = Decimal(str(getattr(move.product_id, 'weight_21', 0.0) or 0.0))
            qty = Decimal(str(move.product_uom_qty or 0.0))
            move.move_demand_w21 = float(w21_unit * qty)

    @api.depends('product_id', 'product_uom_qty', 'quantity',
                 'move_line_ids.quantity', 'state', 'picking_id.state')
    def _compute_metal_details_w21(self):
        """Compute fields for the Details tab — reserved/done show 0 before validate."""
        from decimal import Decimal
        for move in self:
            w21 = Decimal(str(getattr(move.product_id, 'weight_21', 0.0) or 0.0))
            picking_done = (
                (move.picking_id.state == 'done') if move.picking_id
                else (move.state == 'done')
            )
            reserved = (
                Decimal(str(sum(move.move_line_ids.mapped('quantity'))))
                if not picking_done else Decimal('0')
            )
            done_qty = Decimal(str(move.quantity)) if picking_done else Decimal('0')

            move.metal_demand_w21       = float(w21 * Decimal(str(move.product_uom_qty or 0.0)))
            move.metal_reserved_qty     = float(reserved)
            move.metal_reserved_w21     = float(w21 * reserved)
            move.metal_done_qty_display = float(done_qty)
            move.metal_done_w21         = float(w21 * done_qty)

    def write(self, vals):
        """
        Intercept writes on stock.move to log manual edits in the picking chatter.

        Guards:
          • Only runs when called from a real user session (not superuser / cron).
          • Only logs fields in TRACKED.
          • Only logs when the parent picking is explicitly unlocked (is_locked=False)
            — avoids noise during validation, reservation, and internal Odoo writes.
          • Skips logging if no tracked value actually changed.
        """
        import pytz
        from datetime import datetime

        # Fields we track with human-readable labels
        TRACKED = {
            'product_id':       'Product',
            'location_id':      'Source Location',
            'location_dest_id': 'Destination Location',
            'product_uom_qty':  'Demand Qty',
            'quantity':         'Done Qty',
        }

        # ── Skip logging entirely if no tracked field is being written ────────
        tracked_in_vals = {f for f in TRACKED if f in vals}
        should_log = (
            bool(tracked_in_vals)
            and not self.env.su                  # not superuser / system
            and self.env.uid                     # real user
        )

        # Snapshot old values BEFORE super().write()
        old_vals = {}
        if should_log:
            for move in self:
                # Only log for unlocked pickings
                picking = move.picking_id
                if picking and not picking.is_locked:
                    old_vals[move.id] = {f: move[f] for f in tracked_in_vals}

        result = super().write(vals)

        # ── Build chatter notes AFTER write ──────────────────────────────────
        if not old_vals:
            return result

        user = self.env.user
        try:
            tz = pytz.timezone(user.tz or 'UTC')
            now_local = datetime.utcnow().replace(tzinfo=pytz.utc).astimezone(tz)
            ts = now_local.strftime('%Y-%m-%d %H:%M:%S') + ' (' + (user.tz or 'UTC') + ')'
        except Exception:
            ts = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S') + ' (UTC)'

        for move in self:
            snap = old_vals.get(move.id)
            if not snap:
                continue

            def fmt(v):
                if hasattr(v, 'display_name'):
                    return v.display_name or '—'
                if isinstance(v, float):
                    return '%.4f' % v
                return str(v) if v not in (False, None, '') else '—'

            rows = []
            for field, label in TRACKED.items():
                if field not in snap:
                    continue
                old_str = fmt(snap[field])
                new_str = fmt(move[field])
                if old_str == new_str:
                    continue
                rows.append(
                    '<tr>'
                    '<td style="padding:2px 8px;"><b>%s</b></td>'
                    '<td style="padding:2px 8px;color:#c0392b;">%s</td>'
                    '<td style="padding:2px 8px;">→</td>'
                    '<td style="padding:2px 8px;color:#27ae60;"><b>%s</b></td>'
                    '</tr>' % (label, old_str, new_str)
                )

            if not rows or not move.picking_id:
                continue

            table = (
                '<table style="border-collapse:collapse;font-size:13px;">'
                '<thead><tr>'
                '<th style="padding:2px 8px;text-align:left;">Field</th>'
                '<th style="padding:2px 8px;text-align:left;">Old Value</th>'
                '<th></th>'
                '<th style="padding:2px 8px;text-align:left;">New Value</th>'
                '</tr></thead><tbody>%s</tbody></table>'
            ) % ''.join(rows)

            product_name = ''
            try:
                product_name = move.product_id.display_name or str(move.id)
            except Exception:
                product_name = str(move.id)

            body = Markup(
                '<p style="margin:0 0 4px 0;">'
                '&#x270F;&#xFE0F; <b>Transfer Line Edited</b> — <b>%s</b><br/>'
                'By: <b>%s</b> &nbsp;|&nbsp; %s'
                '</p>%s'
            ) % (product_name, user.name, ts, Markup(table))

            try:
                move.picking_id.message_post(body=body)
            except Exception as e:
                _logger.warning('PM chatter log failed for move %s: %s', move.id, e)

        return result