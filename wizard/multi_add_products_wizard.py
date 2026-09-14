# -*- coding: utf-8 -*-
"""
Multi-Add Products Wizard

On-hand quantities are computed EXPLICITLY in Python from stock.quant,
scoped strictly to the sale order's warehouse locations. We deliberately do
NOT rely on product.template.qty_available + a 'warehouse' context key
passed from the view, because that context is not guaranteed to reach the
read of an embedded list inside a many2many field widget — which was the
root cause of on-hand numbers showing an all-warehouses aggregate instead
of the selected warehouse only.
"""
from odoo import models, fields, api


class MultiAddProductsWizardLine(models.TransientModel):
    _name = 'sale.multi.add.products.wizard.line'
    _description = 'Add Multiple Products Wizard Line'

    wizard_id = fields.Many2one(
        'sale.multi.add.products.wizard',
        required=True,
        ondelete='cascade',
    )
    product_tmpl_id = fields.Many2one(
        'product.template', string='Product', required=True,
    )
    name = fields.Char(related='product_tmpl_id.name', string='Product', readonly=True)
    x_metal_type = fields.Selection(related='product_tmpl_id.x_metal_type', string='Type', readonly=True)
    karat_display = fields.Char(related='product_tmpl_id.karat_display', string='Karat', readonly=True)
    x_gold_weight = fields.Float(related='product_tmpl_id.x_gold_weight', string='Weight (g)', readonly=True)
    on_hand_qty = fields.Float(
        string='Available (Warehouse)',
        readonly=True,
        help="Free-to-sell quantity (on hand minus reserved), computed "
             "explicitly for the sale order's warehouse only.",
    )
    to_add = fields.Boolean(string='Add')


class MultiAddProductsWizard(models.TransientModel):
    _name        = 'sale.multi.add.products.wizard'
    _description = 'Add Multiple Products to Sale Order'

    order_id = fields.Many2one(
        'sale.order',
        string='Sale Order',
        required=True,
        readonly=True,
    )
    warehouse_id = fields.Many2one(
        'stock.warehouse',
        string='Warehouse',
        readonly=True,
        help='On-hand quantities shown below are scoped to this warehouse.',
    )
    line_ids = fields.One2many(
        'sale.multi.add.products.wizard.line',
        'wizard_id',
        string='Products',
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        # اجلب الأوردر من الـ context
        order_id = self.env.context.get('default_order_id') or self.env.context.get('active_id')
        if not order_id:
            return res

        order = self.env['sale.order'].browse(order_id).exists()
        if not order:
            return res

        res['order_id'] = order.id

        # الـ warehouse بتاع الأوردر نفسه - لو مش متحدد نرجع لأول warehouse بتاع الشركة
        warehouse = order.warehouse_id
        if not warehouse:
            warehouse = self.env['stock.warehouse'].search(
                [('company_id', '=', order.company_id.id)], limit=1
            )
        res['warehouse_id'] = warehouse.id

        product_tmpls = self.env['product.template'].search([
            ('type', '!=', 'service'),
            ('x_metal_type', '!=', False),
        ])
        on_hand_map = self._get_on_hand_map(product_tmpls, warehouse)

        res['line_ids'] = [
            (0, 0, {
                'product_tmpl_id': tmpl.id,
                'on_hand_qty': on_hand_map.get(tmpl.id, 0.0),
            })
            for tmpl in product_tmpls
        ]
        return res

    @api.model
    def _get_on_hand_map(self, product_tmpls, warehouse):
        """Sum stock.quant.quantity per product.template, restricted strictly
        to internal locations under `warehouse`. Returns {tmpl_id: qty}.
        Computed explicitly (no context tricks) so it can never silently
        fall back to an all-warehouses aggregate.
        """
        result = {tid: 0.0 for tid in product_tmpls.ids}
        if not warehouse or not product_tmpls:
            return result

        variants = product_tmpls.mapped('product_variant_ids')
        if not variants:
            return result

        wh_root = warehouse.view_location_id or warehouse.lot_stock_id
        if not wh_root:
            return result

        location_ids = self.env['stock.location'].search([
            ('id', 'child_of', wh_root.id),
            ('usage', '=', 'internal'),
        ]).ids
        if not location_ids:
            return result

        quant_groups = self.env['stock.quant'].read_group(
            [
                ('product_id', 'in', variants.ids),
                ('location_id', 'in', location_ids),
            ],
            ['quantity:sum', 'reserved_quantity:sum'],
            ['product_id'],
        )
        qty_by_variant = {}
        for g in quant_groups:
            if not g.get('product_id'):
                continue
            on_hand = g.get('quantity', 0.0) or 0.0
            reserved = g.get('reserved_quantity', 0.0) or 0.0
            qty_by_variant[g['product_id'][0]] = on_hand - reserved

        for tmpl in product_tmpls:
            result[tmpl.id] = sum(
                qty_by_variant.get(v.id, 0.0) for v in tmpl.product_variant_ids
            )
        return result

    def action_add_products(self):
        self.ensure_one()
        order = self.order_id

        for line in self.line_ids.filtered('to_add'):
            tmpl = line.product_tmpl_id
            # اختار أول variant
            variant = tmpl.product_variant_ids[:1]
            if not variant:
                continue
            # ابحث لو الـ product موجود بالفعل في الأوردر
            existing_line = order.order_line.filtered(
                lambda l: l.product_id.id == variant.id
            )
            if existing_line:
                # زود الـ qty بـ 1
                existing_line[:1].product_uom_qty += 1
            else:
                # ضيف line جديدة
                self.env['sale.order.line'].create({
                    'order_id': order.id,
                    'product_id': variant.id,
                    'product_uom_qty': 1,
                })

        # ارجع للأوردر
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'res_id': order.id,
            'view_mode': 'form',
            'target': 'current',
        }