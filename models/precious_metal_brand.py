from odoo import models, fields


class PreciousMetalBrand(models.Model):
    _name = 'precious.metal.brand'
    _description = 'Precious Metal Brand'
    _order = 'name'

    name = fields.Char(string='Brand Name', required=True)
    active = fields.Boolean(default=True)
    notes = fields.Text(string='Notes')

    _sql_constraints = [
        ('name_uniq', 'unique(name)', 'Brand name must be unique!')
    ]
