# -*- coding: utf-8 -*-
"""
stock.picking.batch — Availability Guard
=========================================
`picking_ids` on stock.picking.batch is a One2many via `batch_id` on
stock.picking. So adding a picking to a batch is always done via:

    picking.write({'batch_id': batch_id})

NOT via batch.write({'picking_ids': ...}).

Therefore the ONLY correct interception point is stock.picking.write
when 'batch_id' is being set.

Rule:
  picking.state == 'assigned'  → allow  (fully reserved)
  picking.state != 'assigned'  → block  (raise UserError)
"""

from odoo import models, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)

_STATE_LABEL = {
    'assigned':  'Available',
    'confirmed': 'Not Available',
    'waiting':   'Waiting for another move',
    'draft':     'Draft',
    'done':      'Done',
    'cancel':    'Cancelled',
}


class StockPickingBatchGuard(models.Model):
    _inherit = 'stock.picking'

    def write(self, vals):
        """
        Block assignment of non-available pickings to a batch.
        Intercepted when 'batch_id' is being set on one or more pickings.
        """
        if 'batch_id' not in vals or not vals['batch_id']:
            return super().write(vals)

        # Separate fully-reserved from not-ready
        blocked = self.filtered(lambda p: p.state != 'assigned')
        allowed = self - blocked

        if blocked:
            # Build a readable list of what was blocked
            lines = '\n'.join(
                '• %s  (%s)' % (
                    p.name,
                    _STATE_LABEL.get(p.state, p.state),
                )
                for p in blocked
            )
            _logger.info(
                'PM Batch Guard: blocked %d picking(s) from batch %s:\n%s',
                len(blocked), vals['batch_id'], lines,
            )

            if not allowed:
                # All pickings are unavailable → hard block
                raise UserError(_(
                    'Cannot add to batch — none of the selected transfers '
                    'are fully available:\n\n%s\n\n'
                    'Only transfers with Product Availability = Available '
                    '(all products fully reserved) can be added to a batch.'
                ) % lines)

            # Some are available, some are not — add only the available ones
            # and warn about the rest
            result = super(StockPickingBatchGuard, allowed).write(vals)

            # Write without batch_id for the blocked ones (keep them out)
            other_vals = {k: v for k, v in vals.items() if k != 'batch_id'}
            if other_vals:
                super(StockPickingBatchGuard, blocked).write(other_vals)

            # Post warning on the batch chatter
            batch = self.env['stock.picking.batch'].browse(vals['batch_id'])
            if batch.exists():
                batch._pm_post_skip_warning(blocked)

            return result

        return super().write(vals)


class StockPickingBatchChatter(models.Model):
    _inherit = 'stock.picking.batch'

    def _pm_post_skip_warning(self, blocked_pickings):
        """Post a chatter note on the batch listing excluded transfers."""
        self.ensure_one()
        rows = ''.join(
            '<tr>'
            '<td style="padding:3px 10px;"><b>%s</b></td>'
            '<td style="padding:3px 10px;color:#c0392b;">%s</td>'
            '</tr>' % (
                p.name,
                _STATE_LABEL.get(p.state, p.state),
            )
            for p in blocked_pickings
        )
        table = (
            '<table style="border-collapse:collapse;font-size:13px;">'
            '<thead><tr>'
            '<th style="padding:3px 10px;text-align:left;">Transfer</th>'
            '<th style="padding:3px 10px;text-align:left;">Availability</th>'
            '</tr></thead><tbody>%s</tbody></table>'
        ) % rows

        from markupsafe import Markup
        body = Markup(
            '<p style="margin:0 0 6px 0;">'
            '<b>%d transfer(s) excluded from batch</b><br/>'
            'Only fully reserved transfers (Product Availability = Available) '
            'can be added to a batch. The following were skipped:'
            '</p>%s'
        ) % (len(blocked_pickings), Markup(table))

        self.message_post(body=body)
