# -*- coding: utf-8 -*-
from odoo import api, models, fields

PM_ALLOW_BACKORDER_KEY = 'precious_metals_suite.allow_backorder'


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # NOTE: intentionally NOT using config_parameter=... here.
    # Odoo's built-in config_parameter handling for Boolean fields DELETES
    # the ir.config_parameter row when the value is False, instead of
    # storing the string 'False'. That makes "unchecked" indistinguishable
    # from "never set", so any get_param(key, default) call always falls
    # back to the default the moment the box is unchecked. We manage the
    # parameter explicitly instead, so False is always persisted.
    pm_allow_backorder = fields.Boolean(
        string='Allow Backorders on Incomplete Transfers',
        default=True,
        help='',
    )

    def set_values(self):
        super().set_values()
        self.env['ir.config_parameter'].sudo().set_param(
            PM_ALLOW_BACKORDER_KEY,
            'True' if self.pm_allow_backorder else 'False',
        )

    @api.model
    def get_values(self):
        res = super().get_values()
        param = self.env['ir.config_parameter'].sudo().get_param(
            PM_ALLOW_BACKORDER_KEY, 'True'
        )
        res['pm_allow_backorder'] = param in ('True', 'true', '1')
        return res