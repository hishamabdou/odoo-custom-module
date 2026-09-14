# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from .const import METAL_GOLD, METAL_SILVER, METAL_MIXED, KARAT_SILVER, KARAT_ZERO, METAL_TYPES
from odoo.exceptions import ValidationError, UserError
from decimal import Decimal, getcontext, ROUND_HALF_UP
import logging

_logger = logging.getLogger(__name__)

getcontext().prec = 50


# ─────────────────────────────────────────────────────────────────────────────
# 🔴 FIX 1 — Replaced custom_round_down with round_half_up.
#   The old function was pattern-matching on '.285714' in the string
#   representation and hard-coding the result as .29 — which is actually
#   rounding UP, not down. It also silently broke for any other repeating
#   fraction. Standard ROUND_HALF_UP via Python Decimal is correct for all
#   values and consistent with accounting conventions.
# ─────────────────────────────────────────────────────────────────────────────
def round_half_up(value, decimals=2):
    """Round value to `decimals` places using ROUND_HALF_UP. Returns float."""
    if not isinstance(value, Decimal):
        value = Decimal(str(value))
    quantizer = Decimal(10) ** -decimals
    return float(value.quantize(quantizer, rounding=ROUND_HALF_UP))


def _check_mixed_metals(metal_types, context='document'):
    """Raise ValidationError if gold and silver are mixed."""
    if 'gold' in metal_types and 'silver' in metal_types:
        raise ValidationError(
            f"Cannot combine gold and silver products in the same {context}."
        )


# ─────────────────────────────────────────────────────────────────────────────
# Sale Order
# ─────────────────────────────────────────────────────────────────────────────
class SaleOrder(models.Model):
    _inherit = 'sale.order'

    x_price_21 = fields.Float(
        string='Price 21', digits='Product Price',
        help='Price for 21 karat per gram',
        tracking=True,
    )
    x_weight_21 = fields.Float(
        string='Weight21', compute='_compute_weight_21', store=True,
        help='Total weight in 21 karat',
    )
    x_metal_type = fields.Char(
        string='Metal Type', compute='_compute_metal_type', store=True,
        help='Gold / Silver / Mixed — derived from order lines',
    )
    x_price21_locked = fields.Boolean(
        string='Price 21 Locked', compute='_compute_x_price21_locked',
        help='True when Price 21 is read-only for the current user '
             '(order confirmed and user lacks the Edit permission).',
    )

    @api.depends('state')
    def _compute_x_price21_locked(self):
        can_edit = self.env.user.has_group(
            'precious_metals_suite.group_price21_edit_locked')
        for order in self:
            order.x_price21_locked = (
                order.state in ('sale', 'done') and not can_edit
            )


    @api.depends('order_line.product_id.x_metal_type', 'order_line.product_id.type')
    def _compute_metal_type(self):
        for order in self:
            # Ignore service lines — only count actual metal products (gold/silver)
            types = {
                l.product_id.x_metal_type
                for l in order.order_line
                if l.product_id
                and l.product_id.x_metal_type in ('gold', 'silver')
                and l.product_id.type != 'service'
            }
            if not types:
                order.x_metal_type = False
            elif len(types) == 1:
                order.x_metal_type = types.pop().capitalize()
            else:
                order.x_metal_type = METAL_MIXED

    @api.depends(
        'order_line.product_id.x_karat', 'order_line.product_id.x_gold_weight',
        'order_line.product_uom_qty', 'order_line.product_id.weight_21',
    )
    def _compute_weight_21(self):
        for order in self:
            total = Decimal('0')
            for line in order.order_line:
                if not (line.product_id and line.product_id.x_karat
                        and line.product_id.x_gold_weight and line.product_uom_qty):
                    continue
                karat = line.product_id.x_karat
                w = Decimal(str(line.product_id.x_gold_weight))
                q = Decimal(str(line.product_uom_qty))
                if isinstance(karat, str) and karat.lower() == 'silver':
                    total += w * q
                else:
                    try:
                        total += w * (Decimal(str(karat)) / Decimal('875')) * q
                    except (ValueError, TypeError, ArithmeticError):
                        pass
            order.x_weight_21 = float(total)

    @api.onchange('x_price_21')
    def _onchange_price_21(self):
        if self.x_price_21:
            for line in self.order_line:
                line._compute_price_unit_from_gold()

    def _prepare_invoice(self):
        vals = super()._prepare_invoice()
        vals['x_price_21'] = self.x_price_21
        return vals

    @api.constrains('order_line')
    def _check_metal_type_combination(self):
        for order in self:
            _check_mixed_metals({
                l.product_id.x_metal_type for l in order.order_line
                if l.product_id and l.product_id.x_metal_type
            }, 'sale order')

    @api.constrains('x_price_21')
    def _check_price_21_positive(self):
        for order in self:
            if order.x_price_21 and order.x_price_21 < 0:
                raise ValidationError(_(
                    'Price 21 cannot be negative.\nOrder: %s'
                ) % order.name)


# ─────────────────────────────────────────────────────────────────────────────
# Sale Order Line
# ─────────────────────────────────────────────────────────────────────────────
class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    x_metal_type = fields.Selection(related='product_id.x_metal_type',
        string='Metal Type', readonly=True, store=True)
    x_karat = fields.Char(related='product_id.x_karat',
        string='Karat', readonly=True, store=True)
    x_gold_weight = fields.Float(related='product_id.x_gold_weight',
        string='Weight', readonly=True, store=True)
    weight_21 = fields.Float(related='product_id.weight_21',
        string='Weight21', readonly=True, store=True)
    tweight_21 = fields.Float(
        string='Tweight21', compute='_compute_tweight_21', store=True,
        help='Total Weight21 (Quantity × Weight21)',
    )
    price_unit_display = fields.Float(
        string='Unit Price (Display)', compute='_compute_price_unit_display',
        digits=(16, 2),
    )

    @api.depends('price_unit')
    def _compute_price_unit_display(self):
        for line in self:
            line.price_unit_display = round(line.price_unit, 2)

    @api.depends('product_uom_qty', 'weight_21')
    def _compute_tweight_21(self):
        for line in self:
            if line.product_uom_qty and line.weight_21:
                line.tweight_21 = float(
                    Decimal(str(line.product_uom_qty)) * Decimal(str(line.weight_21))
                )
            else:
                line.tweight_21 = 0.0

    def _compute_price_unit_from_gold(self):
        for line in self:
            if not (line.order_id.x_price_21 and line.product_id
                    and line.product_id.x_karat and line.product_id.x_gold_weight):
                continue
            try:
                p21 = Decimal(str(line.order_id.x_price_21))
                k   = line.product_id.x_karat
                w   = Decimal(str(line.product_id.x_gold_weight))
                if isinstance(k, str) and k.lower() == 'silver':
                    line.price_unit = float(w * p21)
                else:
                    line.price_unit = float(w * (Decimal(str(k)) / Decimal('875')) * p21)
            except (ValueError, TypeError, ArithmeticError) as e:
                _logger.error("SaleOrderLine price error: %s", e)

    @api.depends('product_uom_qty', 'price_unit', 'discount', 'tax_ids', 'order_id.currency_id')
    def _compute_amount(self):
        """
        🔴 FIX 2 — All cr.execute() raw SQL removed.
        Values assigned via ORM fields only so Odoo's cache and computed
        field chain remain consistent.
        """
        for line in self:
            if not (line.product_id
                    and line.product_id.x_metal_type in ('gold', 'silver')
                    and line.order_id and line.order_id.x_price_21):
                super(SaleOrderLine, line)._compute_amount()
                continue
            try:
                sub = Decimal(str(line.price_unit)) * Decimal(str(line.product_uom_qty))
                if line.discount:
                    sub *= Decimal('1') - Decimal(str(line.discount)) / Decimal('100')
                fs = round_half_up(sub, 2)
                if line.tax_ids:
                    t = line.tax_ids.compute_all(fs, line.order_id.currency_id, 1,
                        product=line.product_id, partner=line.order_id.partner_shipping_id)
                    line.price_tax      = sum(x.get('amount', 0.0) for x in t.get('taxes', []))
                    line.price_total    = t['total_included']
                    line.price_subtotal = fs
                else:
                    line.price_tax = 0.0
                    line.price_subtotal = fs
                    line.price_total    = fs
            except (ValueError, TypeError, ArithmeticError) as e:
                _logger.error("SaleOrderLine _compute_amount: %s", e)
                super(SaleOrderLine, line)._compute_amount()

    # ── 🟠 FIX 3 — Merged two @api.onchange('product_id') into one ──────────
    @api.onchange('product_id')
    def _onchange_product_id_gold(self):
        """Price update + metal-type validation — merged from two duplicate decorators."""
        if not self.product_id or not self.order_id:
            return
        # Price
        if self.order_id.x_price_21:
            self._compute_price_unit_from_gold()
        # Validation
        current = self.product_id.x_metal_type
        others  = {l.product_id.x_metal_type for l in self.order_id.order_line
                   if l.product_id and l.product_id.x_metal_type and l.id != self.id}
        if current == 'gold' and 'silver' in others:
            raise ValidationError("Cannot add gold when silver products exist in the sale order.")
        if current == 'silver' and 'gold' in others:
            raise ValidationError("Cannot add silver when gold products exist in the sale order.")

    @api.onchange('product_uom_qty')
    def _onchange_quantity_gold_pricing(self):
        if self.product_id and self.order_id and self.order_id.x_price_21:
            self._compute_price_unit_from_gold()


# ─────────────────────────────────────────────────────────────────────────────
# Purchase Order
# ─────────────────────────────────────────────────────────────────────────────
class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    x_price_21 = fields.Float(
        string='Price 21', digits='Product Price',
        help='Price for 21 karat per gram',
        tracking=True,
    )
    x_weight_21 = fields.Float(
        string='Weight21', compute='_compute_weight_21', store=True,
    )
    x_metal_type = fields.Char(
        string='Metal Type', compute='_compute_metal_type', store=True,
        help='Gold / Silver / Mixed — derived from order lines',
    )

    @api.depends('order_line.product_id.x_metal_type', 'order_line.product_id.type')
    def _compute_metal_type(self):
        for order in self:
            # Ignore service lines — only count actual metal products (gold/silver)
            types = {
                l.product_id.x_metal_type
                for l in order.order_line
                if l.product_id
                and l.product_id.x_metal_type in ('gold', 'silver')
                and l.product_id.type != 'service'
            }
            if not types:
                order.x_metal_type = False
            elif len(types) == 1:
                order.x_metal_type = types.pop().capitalize()
            else:
                order.x_metal_type = METAL_MIXED

    @api.depends(
        'order_line.product_id.x_karat', 'order_line.product_id.x_gold_weight',
        'order_line.product_qty', 'order_line.product_id.weight_21',
    )
    def _compute_weight_21(self):
        for order in self:
            total = Decimal('0')
            for line in order.order_line:
                if not (line.product_id and line.product_id.x_karat
                        and line.product_id.x_gold_weight and line.product_qty):
                    continue
                karat = line.product_id.x_karat
                w = Decimal(str(line.product_id.x_gold_weight))
                q = Decimal(str(line.product_qty))
                if isinstance(karat, str) and karat.lower() == 'silver':
                    total += w * q
                else:
                    try:
                        total += w * (Decimal(str(karat)) / Decimal('875')) * q
                    except (ValueError, TypeError, ArithmeticError):
                        pass
            order.x_weight_21 = float(total)

    @api.onchange('x_price_21')
    def _onchange_price_21(self):
        if self.x_price_21:
            for line in self.order_line:
                line._compute_price_unit_from_gold()

    def _prepare_invoice(self):
        vals = super()._prepare_invoice()
        vals['x_price_21'] = self.x_price_21
        return vals

    @api.constrains('order_line')
    def _check_metal_type_combination(self):
        for order in self:
            _check_mixed_metals({
                l.product_id.x_metal_type for l in order.order_line
                if l.product_id and l.product_id.x_metal_type
            }, 'purchase order')

    @api.constrains('x_price_21')
    def _check_price_21_positive(self):
        for order in self:
            if order.x_price_21 and order.x_price_21 < 0:
                raise ValidationError(_(
                    'Price 21 cannot be negative.\nOrder: %s'
                ) % order.name)

    x_price21_locked = fields.Boolean(
        string='Price 21 Locked', compute='_compute_x_price21_locked',
        help='True when Price 21 is read-only for the current user '
             '(order confirmed and user lacks the Edit permission).',
    )

    @api.depends('state')
    def _compute_x_price21_locked(self):
        can_edit = self.env.user.has_group(
            'precious_metals_suite.group_price21_edit_locked')
        for order in self:
            order.x_price21_locked = (
                order.state in ('purchase', 'done') and not can_edit
            )

    # -----------------------------------------------------------------
    # Lock x_price_21 after confirmation unless the user holds the
    # dedicated "Edit Price 21 After Confirm/Post" permission.
    # -----------------------------------------------------------------
    def write(self, vals):
        recompute_orders = self.browse()
        if 'x_price_21' in vals:
            for order in self:
                if order.x_price_21 == vals['x_price_21']:
                    continue
                if (order.state in ('purchase', 'done')
                        and not self.env.user.has_group(
                            'precious_metals_suite.group_price21_edit_locked')):
                    raise UserError(_(
                        'Price 21 cannot be modified after the purchase order '
                        'has been confirmed.\n'
                        'Order: %s\n'
                        'Only users with the "Edit Price 21 After Confirm/Post" '
                        'permission can do this.'
                    ) % order.name)
                recompute_orders |= order
        res = super().write(vals)
        if recompute_orders:
            # Re-derive unit prices and totals from scratch, exactly as if
            # Price 21 had just been entered on a fresh purchase order.
            for order in recompute_orders:
                for line in order.order_line:
                    line._compute_price_unit_from_gold()
        return res


# ─────────────────────────────────────────────────────────────────────────────
# Purchase Order Line
# ─────────────────────────────────────────────────────────────────────────────
class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    x_metal_type = fields.Selection(related='product_id.x_metal_type',
        string='Metal Type', readonly=True, store=True)
    x_karat = fields.Char(related='product_id.x_karat',
        string='Karat', readonly=True, store=True)
    x_gold_weight = fields.Float(related='product_id.x_gold_weight',
        string='Weight', readonly=True, store=True)
    weight_21 = fields.Float(related='product_id.weight_21',
        string='Weight21', readonly=True, store=True)
    tweight_21 = fields.Float(
        string='Tweight21', compute='_compute_tweight_21', store=True,
    )
    x_gold_price_calculated = fields.Boolean(
        string='Gold Price Calculated', default=False,
        help='Price was set by gold pricing — protected from purchase history override',
    )
    price_unit_display = fields.Float(
        string='Unit Price (Display)', compute='_compute_price_unit_display',
        digits=(16, 2),
    )

    @api.depends('price_unit')
    def _compute_price_unit_display(self):
        for line in self:
            line.price_unit_display = round(line.price_unit, 2)

    @api.depends('product_qty', 'weight_21')
    def _compute_tweight_21(self):
        for line in self:
            if line.product_qty and line.weight_21:
                line.tweight_21 = float(
                    Decimal(str(line.product_qty)) * Decimal(str(line.weight_21))
                )
            else:
                line.tweight_21 = 0.0

    def _compute_price_unit_from_gold(self):
        for line in self:
            try:
                if not (line.order_id and line.order_id.x_price_21
                        and line.product_id and line.product_id.x_karat
                        and line.product_id.x_gold_weight
                        and line.product_id.x_metal_type in ('gold', 'silver')):
                    continue
                p21 = Decimal(str(line.order_id.x_price_21))
                k   = line.product_id.x_karat
                w   = Decimal(str(line.product_id.x_gold_weight))
                if p21 <= 0 or w <= 0:
                    continue
                if isinstance(k, str) and k.lower() == 'silver':
                    price = w * p21
                else:
                    kv = Decimal(str(k))
                    if kv <= 0:
                        continue
                    price = w * (kv / Decimal('875')) * p21
                if price > 0:
                    line.price_unit = float(price)
                    line.x_gold_price_calculated = True
            except Exception as e:
                _logger.error("PurchaseOrderLine price error: %s", e)

    @api.depends('product_qty', 'price_unit', 'discount', 'tax_ids', 'order_id.currency_id')
    def _compute_amount(self):
        """🔴 FIX 2 — No cr.execute(). ORM assignment only."""
        for line in self:
            if not (line.product_id
                    and line.product_id.x_metal_type in ('gold', 'silver')
                    and line.order_id and line.order_id.x_price_21
                    and line.x_gold_price_calculated):
                super(PurchaseOrderLine, line)._compute_amount()
                continue
            try:
                sub = Decimal(str(line.price_unit)) * Decimal(str(line.product_qty))
                if line.discount:
                    sub *= Decimal('1') - Decimal(str(line.discount)) / Decimal('100')
                fs = round_half_up(sub, 2)
                if line.tax_ids:
                    t = line.tax_ids.compute_all(fs, line.order_id.currency_id, 1,
                        product=line.product_id, partner=line.order_id.partner_id)
                    line.price_tax      = sum(x.get('amount', 0.0) for x in t.get('taxes', []))
                    line.price_total    = t['total_included']
                    line.price_subtotal = fs
                else:
                    line.price_tax = 0.0
                    line.price_subtotal = fs
                    line.price_total    = fs
            except (ValueError, TypeError, ArithmeticError) as e:
                _logger.error("PurchaseOrderLine _compute_amount: %s", e)
                super(PurchaseOrderLine, line)._compute_amount()

    # ── 🟠 FIX 3 — Merged duplicate onchange ────────────────────────────────
    @api.onchange('product_id')
    def _onchange_product_id_gold(self):
        """Price update + metal-type validation — merged."""
        if not self.product_id or not self.order_id:
            return
        if (self.order_id.x_price_21
                and self.product_id.x_metal_type in ('gold', 'silver')):
            self._compute_price_unit_from_gold()
        current = self.product_id.x_metal_type
        others  = {l.product_id.x_metal_type for l in self.order_id.order_line
                   if l.product_id and l.product_id.x_metal_type and l.id != self.id}
        if current == 'gold' and 'silver' in others:
            raise ValidationError("Cannot add gold when silver products exist in the purchase order.")
        if current == 'silver' and 'gold' in others:
            raise ValidationError("Cannot add silver when gold products exist in the purchase order.")

    @api.onchange('product_qty')
    def _onchange_quantity_gold_pricing(self):
        if (self.product_id and self.order_id and self.order_id.x_price_21
                and self.product_id.x_metal_type in ('gold', 'silver')):
            self._compute_price_unit_from_gold()

    def write(self, vals):
        """
        Protect gold-calculated price_unit from purchase history override.
        🔴 FIX 2 — removed cr.execute(); uses direct ORM field assignment.
        """
        gold_prices = {
            line.id: line.price_unit
            for line in self
            if (line.product_id
                and line.product_id.x_metal_type in ('gold', 'silver')
                and line.x_gold_price_calculated)
        }
        result = super().write(vals)
        for line in self:
            if (line.id in gold_prices
                    and line.x_gold_price_calculated
                    and line.price_unit != gold_prices[line.id]):
                _logger.info("Restoring gold price for PO line %s: %s",
                             line.id, gold_prices[line.id])
                # Use _write to bypass onchange/compute triggers that would
                # re-fetch from pricelist
                line._write({'price_unit': gold_prices[line.id]})
        return result

    def _onchange_quantity(self):
        """Prevent purchase history from resetting gold prices."""
        gold_prices = {
            line.id: line.price_unit
            for line in self
            if (line.product_id
                and line.product_id.x_metal_type in ('gold', 'silver')
                and line.x_gold_price_calculated)
        }
        result = super()._onchange_quantity()
        for line in self:
            if line.id in gold_prices:
                line.price_unit = gold_prices[line.id]
        return result

    def _get_stock_move_price_unit(self):
        if (self.product_id
                and self.product_id.x_metal_type in ('gold', 'silver')
                and self.x_gold_price_calculated):
            return self.price_unit
        return super()._get_stock_move_price_unit()


# ─────────────────────────────────────────────────────────────────────────────
# Account Move (Invoice / Bill)
# ─────────────────────────────────────────────────────────────────────────────
class AccountMove(models.Model):
    _inherit = 'account.move'

    x_price_21 = fields.Float(
        string='Price 21', digits='Product Price',
        help='Price for 21 karat per gram',
        tracking=True,
    )
    x_weight_21 = fields.Float(
        string='Weight21', compute='_compute_weight_21', store=True,
    )
    x_metal_type = fields.Char(
        string='Metal Type', compute='_compute_metal_type', store=True,
        help='Gold / Silver / Mixed — derived from invoice lines',
    )

    @api.depends('invoice_line_ids.product_id.x_metal_type', 'invoice_line_ids.product_id.type')
    def _compute_metal_type(self):
        for move in self:
            # Ignore service lines — only count actual metal products (gold/silver)
            types = {
                l.product_id.x_metal_type
                for l in move.invoice_line_ids
                if l.product_id
                and l.product_id.x_metal_type in ('gold', 'silver')
                and l.product_id.type != 'service'
            }
            if not types:
                move.x_metal_type = False
            elif len(types) == 1:
                move.x_metal_type = types.pop().capitalize()
            else:
                move.x_metal_type = METAL_MIXED

    @api.depends(
        'invoice_line_ids.product_id.x_karat',
        'invoice_line_ids.product_id.x_gold_weight',
        'invoice_line_ids.quantity',
        'invoice_line_ids.product_id.weight_21',
    )
    def _compute_weight_21(self):
        for invoice in self:
            total = Decimal('0')
            for line in invoice.invoice_line_ids:
                if not (line.product_id and line.product_id.x_karat
                        and line.product_id.x_gold_weight and line.quantity):
                    continue
                karat = line.product_id.x_karat
                w = Decimal(str(line.product_id.x_gold_weight))
                q = Decimal(str(line.quantity))
                if isinstance(karat, str) and karat.lower() == 'silver':
                    total += w * q
                else:
                    try:
                        total += w * (Decimal(str(karat)) / Decimal('875')) * q
                    except (ValueError, TypeError, ArithmeticError):
                        pass
            invoice.x_weight_21 = float(total)

    @api.onchange('x_price_21')
    def _onchange_price_21(self):
        if self.x_price_21 and self.move_type in (
                'out_invoice', 'out_refund', 'in_invoice', 'in_refund'):
            for line in self.invoice_line_ids:
                line._compute_price_unit_from_gold()

    @api.constrains('invoice_line_ids')
    def _check_metal_type_combination(self):
        for invoice in self:
            if invoice.move_type not in (
                    'out_invoice', 'out_refund', 'in_invoice', 'in_refund'):
                continue
            _check_mixed_metals({
                l.product_id.x_metal_type for l in invoice.invoice_line_ids
                if l.product_id and l.product_id.x_metal_type
            }, 'invoice')

    @api.constrains('x_price_21')
    def _check_price_21_positive(self):
        for invoice in self:
            if invoice.x_price_21 and invoice.x_price_21 < 0:
                raise ValidationError(_(
                    'Price 21 cannot be negative.\nInvoice: %s'
                ) % invoice.name)

    x_price21_locked = fields.Boolean(
        string='Price 21 Locked', compute='_compute_x_price21_locked',
        help='True when Price 21 is read-only for the current user '
             '(invoice posted and user lacks the Edit permission).',
    )

    @api.depends('state')
    def _compute_x_price21_locked(self):
        can_edit = self.env.user.has_group(
            'precious_metals_suite.group_price21_edit_locked')
        for invoice in self:
            invoice.x_price21_locked = (
                invoice.state == 'posted' and not can_edit
            )

    # -----------------------------------------------------------------
    # Lock x_price_21 after posting unless the user holds the
    # dedicated "Edit Price 21 After Confirm/Post" permission.
    # -----------------------------------------------------------------
    def write(self, vals):
        recompute_invoices = self.browse()
        if 'x_price_21' in vals:
            for invoice in self:
                if invoice.x_price_21 == vals['x_price_21']:
                    continue
                if (invoice.state == 'posted'
                        and not self.env.user.has_group(
                            'precious_metals_suite.group_price21_edit_locked')):
                    raise UserError(_(
                        'Price 21 cannot be modified after the invoice has '
                        'been posted.\n'
                        'Invoice: %s\n'
                        'Only users with the "Edit Price 21 After Confirm/Post" '
                        'permission can do this.'
                    ) % invoice.name)
                recompute_invoices |= invoice
        res = super().write(vals)
        if recompute_invoices:
            # Re-derive unit prices and totals from scratch, exactly as if
            # Price 21 had just been entered on a fresh invoice.
            #
            # NOTE: setting line.price_unit here calls Odoo's real
            # account.move.line.write() under the hood (field assignment on
            # a stored field outside onchange triggers an immediate write).
            # In Odoo 19, that write() already wraps itself in
            # self.move_id._sync_dynamic_lines(...), which rebuilds the tax
            # lines AND the receivable/payable ("Amount Due") line to match
            # the new totals — there is no separate method to call for that
            # (the old _recompute_dynamic_lines() from earlier versions was
            # removed in 19).
            for invoice in recompute_invoices:
                for line in invoice.invoice_line_ids:
                    line._compute_price_unit_from_gold()
        return res


# ─────────────────────────────────────────────────────────────────────────────
# Account Move Line (Invoice Line)
# ─────────────────────────────────────────────────────────────────────────────
class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    x_metal_type = fields.Selection(related='product_id.x_metal_type',
        string='Metal Type', readonly=True, store=False)
    x_karat = fields.Char(related='product_id.x_karat',
        string='Karat', readonly=True, store=False)
    x_gold_weight = fields.Float(related='product_id.x_gold_weight',
        string='Weight', readonly=True, store=False)
    weight_21 = fields.Float(related='product_id.weight_21',
        string='Weight21', readonly=True, store=True)
    tweight_21 = fields.Float(
        string='Tweight21', compute='_compute_tweight_21', store=True,
    )
    price_unit_display = fields.Float(
        string='Unit Price (Display)', compute='_compute_price_unit_display',
        digits=(16, 2),
    )

    @api.depends('price_unit')
    def _compute_price_unit_display(self):
        for line in self:
            line.price_unit_display = round(line.price_unit, 2)

    @api.depends('quantity', 'weight_21')
    def _compute_tweight_21(self):
        for line in self:
            if line.quantity and line.weight_21:
                line.tweight_21 = float(
                    Decimal(str(line.quantity)) * Decimal(str(line.weight_21))
                )
            else:
                line.tweight_21 = 0.0

    def _compute_price_unit_from_gold(self):
        INVOICE_TYPES = ('out_invoice', 'out_refund', 'in_invoice', 'in_refund')
        for line in self:
            if not (line.move_id.x_price_21 and line.product_id
                    and line.product_id.x_karat and line.product_id.x_gold_weight
                    and line.move_id.move_type in INVOICE_TYPES):
                continue
            try:
                p21 = Decimal(str(line.move_id.x_price_21))
                k   = line.product_id.x_karat
                w   = Decimal(str(line.product_id.x_gold_weight))
                if isinstance(k, str) and k.lower() == 'silver':
                    line.price_unit = float(w * p21)
                else:
                    line.price_unit = float(w * (Decimal(str(k)) / Decimal('875')) * p21)
            except (ValueError, TypeError, ArithmeticError) as e:
                _logger.error("AccountMoveLine price error: %s", e)

    @api.depends('quantity', 'price_unit', 'discount', 'tax_ids', 'move_id.currency_id')
    def _compute_amount(self):
        """🔴 FIX 2 — No cr.execute(). ORM assignment only."""
        for line in self:
            if not (line.product_id
                    and line.product_id.x_metal_type in ('gold', 'silver')
                    and line.move_id and line.move_id.x_price_21):
                super(AccountMoveLine, line)._compute_amount()
                continue
            try:
                sub = Decimal(str(line.price_unit)) * Decimal(str(line.quantity))
                if line.discount:
                    sub *= Decimal('1') - Decimal(str(line.discount)) / Decimal('100')
                fs = round_half_up(sub, 2)
                if line.tax_ids:
                    t = line.tax_ids.compute_all(fs, line.move_id.currency_id, 1,
                        product=line.product_id, partner=line.move_id.partner_id)
                    line.price_tax      = sum(x.get('amount', 0.0) for x in t.get('taxes', []))
                    line.price_total    = t['total_included']
                    line.price_subtotal = fs
                else:
                    line.price_tax = 0.0
                    line.price_subtotal = fs
                    line.price_total    = fs
            except (ValueError, TypeError, ArithmeticError) as e:
                _logger.error("AccountMoveLine _compute_amount: %s", e)
                super(AccountMoveLine, line)._compute_amount()

    # ── 🟠 FIX 3 — Merged duplicate onchange ────────────────────────────────
    @api.onchange('product_id')
    def _onchange_product_id_gold(self):
        """Price update + metal-type validation — merged."""
        INVOICE_TYPES = ('out_invoice', 'out_refund', 'in_invoice', 'in_refund')
        if not self.product_id or not self.move_id:
            return
        if self.move_id.move_type not in INVOICE_TYPES:
            return
        if self.move_id.x_price_21:
            self._compute_price_unit_from_gold()
        current = self.product_id.x_metal_type
        others  = {l.product_id.x_metal_type for l in self.move_id.invoice_line_ids
                   if l.product_id and l.product_id.x_metal_type and l.id != self.id}
        if current == 'gold' and 'silver' in others:
            raise ValidationError("Cannot add gold when silver products exist in the invoice.")
        if current == 'silver' and 'gold' in others:
            raise ValidationError("Cannot add silver when gold products exist in the invoice.")

    @api.onchange('quantity')
    def _onchange_quantity_gold_pricing(self):
        INVOICE_TYPES = ('out_invoice', 'out_refund', 'in_invoice', 'in_refund')
        if (self.product_id and self.move_id and self.move_id.x_price_21
                and self.move_id.move_type in INVOICE_TYPES):
            self._compute_price_unit_from_gold()


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
def _normalize_karat_vals(vals):
    """Auto-correct x_karat in vals dict based on x_metal_type.
    Ensures silver always gets KARAT_SILVER regardless of onchange timing."""
    mtype = vals.get('x_metal_type')
    if mtype == 'silver':
        vals['x_karat'] = KARAT_SILVER
    elif mtype == 'other':
        vals.setdefault('x_karat', KARAT_ZERO)


# ─────────────────────────────────────────────────────────────────────────────
# Product Template
# ─────────────────────────────────────────────────────────────────────────────
class ProductTemplate(models.Model):
    _inherit = 'product.template'

    x_metal_type = fields.Selection([
        ('gold', METAL_GOLD), ('silver', METAL_SILVER), ('other', 'Other'),
    ], string='Metal Type', default='other',
       help='Type of metal: Gold, Silver, or Other')

    x_karat = fields.Char(
        string='Karat',
        help='Numeric karat (875, 750, 999.9 …) or "Silver" for silver',
        default='875',
    )
    x_gold_weight = fields.Float(
        string='Weight', digits='Stock Weight', default=0.0,
        help='Weight in grams',
    )
    weight_21_precise = fields.Char(
        string='Weight21 Precise', compute='_compute_weight_21_precise', store=True,
        help='Weight in 21 karat equivalent stored as string for full precision',
    )
    weight_21 = fields.Float(
        string='Weight21', compute='_compute_weight_21', store=True,
    )

    @api.onchange('x_metal_type')
    def _onchange_metal_type(self):
        if self.x_metal_type == 'silver':
            self.x_karat = KARAT_SILVER
        elif self.x_metal_type == 'other':
            self.x_karat = '0'
        elif self.x_metal_type == 'gold':
            if not self.x_karat or self.x_karat in (KARAT_SILVER, KARAT_ZERO):
                self.x_karat = '875'

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            _normalize_karat_vals(vals)
        return super().create(vals_list)

    def write(self, vals):
        _normalize_karat_vals(vals)
        return super().write(vals)

    @api.depends('x_karat', 'x_gold_weight')
    def _compute_weight_21_precise(self):
        for p in self:
            if not (p.x_karat and p.x_gold_weight):
                p.weight_21_precise = '0'
                continue
            try:
                if isinstance(p.x_karat, str) and p.x_karat.lower() == 'silver':
                    p.weight_21_precise = str(Decimal(str(p.x_gold_weight)))
                else:
                    kv = Decimal(str(p.x_karat))
                    gw = Decimal(str(p.x_gold_weight))
                    p.weight_21_precise = str(gw * (kv / Decimal('875'))) if kv > 0 else '0'
            except (ValueError, TypeError, ArithmeticError):
                p.weight_21_precise = '0'

    @api.depends('weight_21_precise')
    def _compute_weight_21(self):
        for p in self:
            try:
                p.weight_21 = float(Decimal(p.weight_21_precise)) if p.weight_21_precise else 0.0
            except (ValueError, TypeError):
                p.weight_21 = 0.0

    @api.constrains('x_karat', 'x_gold_weight', 'x_metal_type')
    def _check_gold_fields(self):
        for r in self:
            if r.type == 'service' or not r.x_metal_type:
                continue
            if r.x_metal_type in ('gold', 'silver'):
                karat_val = (r.x_karat or '').strip()
                if not karat_val:
                    raise ValidationError("Karat is required for metal products.")
                if r.x_gold_weight <= 0:
                    raise ValidationError("Weight must be > 0 for metal products.")
                if r.x_metal_type == 'gold':
                    try:
                        if float(karat_val) <= 0:
                            raise ValidationError("Karat must be > 0 for gold products.")
                    except ValueError:
                        raise ValidationError("Karat must be numeric for gold products.")
                elif r.x_metal_type == 'silver' and karat_val.lower() != 'silver':
                    raise ValidationError("Karat must be 'Silver' for silver products.")


# ─────────────────────────────────────────────────────────────────────────────
# Product Product (Variant)
# ─────────────────────────────────────────────────────────────────────────────
class ProductProduct(models.Model):
    _inherit = 'product.product'

    x_metal_type = fields.Selection(related='product_tmpl_id.x_metal_type',
        string='Metal Type', store=True, readonly=False)
    x_karat = fields.Char(related='product_tmpl_id.x_karat',
        string='Karat', store=True, readonly=False)
    x_gold_weight = fields.Float(related='product_tmpl_id.x_gold_weight',
        string='Weight', store=True, readonly=False)
    weight_21_precise = fields.Char(related='product_tmpl_id.weight_21_precise',
        string='Weight21 Precise', store=True, readonly=True)
    weight_21 = fields.Float(related='product_tmpl_id.weight_21',
        string='Weight21', store=True, readonly=True)