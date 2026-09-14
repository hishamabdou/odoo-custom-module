# -*- coding: utf-8 -*-
"""
pm.unlock.reason.wizard — Unlock Transfer confirmation popup

Recreated after the 19.0.2.72.0 Serial/Lot cleanup migration dropped the
original model. stock_picking_extension.action_reset_to_draft() opens this
wizard; the manager must type a reason before the transfer is unlocked.
The reason is posted to the picking's chatter for an audit trail.
"""
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class PmUnlockReasonWizard(models.TransientModel):
    _name = 'pm.unlock.reason.wizard'
    _description = 'Unlock Transfer — Reason Required'

    picking_id = fields.Many2one(
        'stock.picking',
        string='Transfer',
        required=True,
        ondelete='cascade',
    )
    reason = fields.Text(
        string='Reason for Unlocking',
        help='Explain why this transfer needs to be unlocked. '
             'This will be recorded in the transfer history.',
    )

    def action_confirm_unlock(self):
        """Unlock the picking and log the reason on its chatter."""
        self.ensure_one()

        if not (self.reason and self.reason.strip()):
            raise UserError(_('Please enter a reason before unlocking.'))

        if not self.env.user.has_group('precious_metals_suite.group_manager'):
            raise UserError(_(
                'You do not have permission to unlock a transfer. '
                'Only Precious Metals Managers and Administrators can do this.'
            ))

        picking = self.picking_id
        if picking.state == 'cancel':
            raise UserError(_('Cannot unlock a cancelled transfer.'))

        picking.write({'is_locked': False})
        picking._log_lock_action(
            'Transfer Unlocked',
            'Reason: %s' % (self.reason or ''),
        )
        return {'type': 'ir.actions.act_window_close'}
