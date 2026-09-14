# -*- coding: utf-8 -*-
"""
Precious Metal Suite — Product Extension
Adds Brand, karat_display, karat (numeric) to product.template.
gold_pricing.py already defines: x_metal_type, x_karat, x_gold_weight, weight_21
"""
from odoo import models, fields, api, _
from .const import KARAT_SILVER, KARAT_ZERO

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    precious_metal_brand_id = fields.Many2one(
        'precious.metal.brand', string='Brand', tracking=True)

    karat_display = fields.Char(
        string='Karat Display',
        compute='_compute_pm_karat_display',
        inverse='_inverse_pm_karat_display',
        store=True, tracking=True,
        help='Human-readable karat (e.g. 875, 750, SILVER, OTHER)',
    )

    karat = fields.Float(
        string='Karat (numeric)',
        digits=(16, 4),
        compute='_compute_pm_karat_numeric',
        store=True,
    )

    @api.depends('x_metal_type', 'x_karat')
    def _compute_pm_karat_display(self):
        for rec in self:
            mtype = rec.x_metal_type
            karat = rec.x_karat or ''
            if mtype == 'gold':
                rec.karat_display = karat if karat not in (KARAT_ZERO, '', KARAT_SILVER) else '0'
            elif mtype == 'silver':
                rec.karat_display = KARAT_SILVER
            elif mtype == 'other':
                rec.karat_display = 'OTHER'
            else:
                rec.karat_display = ''

    def _inverse_pm_karat_display(self):
        for rec in self:
            if rec.x_metal_type == 'gold':
                rec.x_karat = rec.karat_display or '0'

    @api.depends('x_metal_type', 'x_karat')
    def _compute_pm_karat_numeric(self):
        for rec in self:
            mtype = rec.x_metal_type
            karat_str = rec.x_karat or '0'
            if mtype == 'gold':
                try:
                    rec.karat = float(karat_str)
                except (ValueError, TypeError):
                    rec.karat = 0.0
            elif mtype == 'silver':
                rec.karat = 999.9
            else:
                rec.karat = 0.0
