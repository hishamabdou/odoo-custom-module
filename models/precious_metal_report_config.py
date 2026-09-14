# -*- coding: utf-8 -*-
import calendar
from datetime import datetime
from odoo import models, fields, api


class PreciousMetalReportConfig(models.Model):
    """
    Singleton — Default settings for ALL Precious Metals reports.
    Stored as a single record; get_config() creates it on first use.
    """
    _name        = 'precious.metal.report.config'
    _description = 'Precious Metals — Report Default Settings'

    @api.model
    def get_config(self):
        config = self.search([], limit=1, order='id asc')
        if not config:
            config = self.sudo().create({})
        return config

    def _resolve_period(self, period_type, time_from, time_to, custom_from=None, custom_to=None):
        now = datetime.now()
        def t(dt, hm):
            try: h, m = int(hm[:2]), int(hm[3:5])
            except Exception: h, m = 0, 0
            return dt.replace(hour=h, minute=m, second=0, microsecond=0)
        tf = time_from or '00:00'
        tt = time_to   or '23:59'
        if period_type == 'current_month':
            return t(now.replace(day=1), tf), t(now, tt)
        elif period_type == 'current_day':
            return t(now, tf), t(now, tt)
        elif period_type == 'last_month':
            y, m = (now.year-1, 12) if now.month==1 else (now.year, now.month-1)
            ld = calendar.monthrange(y, m)[1]
            return t(now.replace(year=y, month=m, day=1), tf), t(now.replace(year=y, month=m, day=ld), tt)
        elif period_type == 'custom':
            return (custom_from or now.replace(day=1,hour=0,minute=0,second=0,microsecond=0),
                    custom_to   or now.replace(hour=23,minute=59,second=59,microsecond=0))
        return t(now.replace(day=1), '00:00'), t(now, '23:59')

    # ── 1. INVENTORY REPORT ───────────────────────────────────────────────
    pm_period_type   = fields.Selection([('current_month','Current Month'),('current_day','Today'),('last_month','Last Full Month'),('custom','Custom Dates')], default='current_month', required=True, string='Period')
    pm_time_from     = fields.Char('From (HH:MM)', default='00:00')
    pm_time_to       = fields.Char('To (HH:MM)',   default='23:59')
    pm_custom_from   = fields.Datetime('Custom From')
    pm_custom_to     = fields.Datetime('Custom To')
    pm_warehouse_ids = fields.Many2many('stock.warehouse',    'pm_cfg_pm_wh_rel',   'cfg_id','wh_id',   string='Default Warehouses')
    pm_location_ids  = fields.Many2many('stock.location',     'pm_cfg_pm_loc_rel',  'cfg_id','loc_id',  string='Default Locations',  domain=[('usage','=','internal')])
    pm_metal_type    = fields.Selection([('all','All Metals'),('gold','GOLD Only'),('silver','SILVER Only'),('other','OTHER Only')], default='all', required=True, string='Metal Type')
    pm_brand_ids     = fields.Many2many('precious.metal.brand','pm_cfg_pm_brand_rel','cfg_id','brand_id',string='Default Brands')
    pm_product_ids   = fields.Many2many('product.template',   'pm_cfg_pm_prod_rel', 'cfg_id','prod_id', string='Default Products', domain=[('x_metal_type','!=',False)])
    pm_only_with_moves = fields.Boolean('Show Only Products with Movements', default=True)

    def get_pm_defaults(self):
        df, dt = self._resolve_period(self.pm_period_type, self.pm_time_from, self.pm_time_to, self.pm_custom_from, self.pm_custom_to)
        return {'datetime_from': df, 'datetime_to': dt, 'x_metal_type': self.pm_metal_type or 'all', 'only_with_moves': self.pm_only_with_moves,
                'warehouse_ids': [(6,0,self.pm_warehouse_ids.ids)] if self.pm_warehouse_ids else [],
                'location_ids':  [(6,0,self.pm_location_ids.ids)]  if self.pm_location_ids  else [],
                'brand_ids':     [(6,0,self.pm_brand_ids.ids)]     if self.pm_brand_ids     else [],
                'product_ids':   [(6,0,self.pm_product_ids.ids)]   if self.pm_product_ids   else []}

    # ── 2. QTY ON HAND ────────────────────────────────────────────────────
    qoh_as_of_date    = fields.Date('Default "As of" Date', help='Leave empty = today')
    qoh_metal_type    = fields.Selection([('all','All Metals'),('gold','GOLD Only'),('silver','SILVER Only'),('other','OTHER Only')], default='all', required=True, string='Metal Type')
    qoh_warehouse_ids = fields.Many2many('stock.warehouse','pm_cfg_qoh_wh_rel', 'cfg_id','wh_id',  string='Default Warehouses')
    qoh_location_ids  = fields.Many2many('stock.location', 'pm_cfg_qoh_loc_rel','cfg_id','loc_id', string='Default Locations', domain=[('usage','=','internal')])

    def get_qoh_defaults(self):
        return {'as_of_date': self.qoh_as_of_date or fields.Date.today(), 'x_metal_type': self.qoh_metal_type or 'all',
                'warehouse_ids': [(6,0,self.qoh_warehouse_ids.ids)] if self.qoh_warehouse_ids else [],
                'location_ids':  [(6,0,self.qoh_location_ids.ids)]  if self.qoh_location_ids  else []}

    # ── 3. ADJUSTMENT LOG ────────────────────────────────────────────────
    adj_period_type   = fields.Selection([('current_month','Current Month'),('current_day','Today'),('last_month','Last Full Month'),('custom','Custom Dates')], default='current_month', required=True, string='Period')
    adj_time_from     = fields.Char('From (HH:MM)', default='00:00')
    adj_time_to       = fields.Char('To (HH:MM)',   default='23:59')
    adj_custom_from   = fields.Datetime('Custom From')
    adj_custom_to     = fields.Datetime('Custom To')
    adj_metal_type    = fields.Selection([('all','All Metals'),('gold','GOLD Only'),('silver','SILVER Only'),('other','OTHER Only')], default='all', required=True, string='Metal Type')
    adj_warehouse_ids = fields.Many2many('stock.warehouse','pm_cfg_adj_wh_rel', 'cfg_id','wh_id',  string='Default Warehouses')
    adj_location_ids  = fields.Many2many('stock.location', 'pm_cfg_adj_loc_rel','cfg_id','loc_id', string='Default Locations', domain=[('usage','=','internal')])

    def get_adj_defaults(self):
        df, dt = self._resolve_period(self.adj_period_type, self.adj_time_from, self.adj_time_to, self.adj_custom_from, self.adj_custom_to)
        return {'datetime_from': df, 'datetime_to': dt, 'x_metal_type': self.adj_metal_type or 'all',
                'warehouse_ids': [(6,0,self.adj_warehouse_ids.ids)] if self.adj_warehouse_ids else [],
                'location_ids':  [(6,0,self.adj_location_ids.ids)]  if self.adj_location_ids  else []}

    # ── 4. WAITING REPORT ────────────────────────────────────────────────
    wait_metal_type   = fields.Selection([('all','All'),('gold','GOLD'),('silver','SILVER'),('other','OTHER')], default='all', string='Metal Type')
    wait_karat        = fields.Selection([('all','All Karats'),('999.9','999.9'),('875','875'),('Silver','Silver')], default='all', string='Karat')
    wait_group_by     = fields.Selection([('division','By Channel'),('product','By Product'),('customer','By Customer')], default='division', string='Group By')
    wait_report_mode  = fields.Selection([('full','Full Report (Details + Summary)'),('summary','Summary Only')], default='full', required=True, string='Report Mode')
    wait_location_ids = fields.Many2many('stock.location', 'pm_cfg_wait_loc_rel', 'cfg_id', 'loc_id', string='Default Locations', domain=[('usage','=','internal')])

    def get_wait_defaults(self):
        return {'metal_type': self.wait_metal_type or 'all', 'group_by': self.wait_group_by or 'division', 'product_karat': self.wait_karat or 'all',
                'report_mode': self.wait_report_mode or 'full',
                'location_ids': [(6,0,self.wait_location_ids.ids)] if self.wait_location_ids else []}

    # ── 10. STOCK TRANSFER (Transfers) ───────────────────────────────────
    transfer_src_location_ids = fields.Many2many(
        'stock.location', 'pm_cfg_xfer_src_rel', 'cfg_id', 'loc_id',
        string='Default Source Locations',
        domain=[('usage','=','internal')],
        help='Pre-filled source locations in the Transfer Wizard',
    )
    transfer_dst_location_ids = fields.Many2many(
        'stock.location', 'pm_cfg_xfer_dst_rel', 'cfg_id', 'loc_id',
        string='Default Destination Locations',
        domain=[('usage','=','internal')],
        help='Pre-filled destination filter in the Transfer Wizard (optional)',
    )
    transfer_validate_immediately = fields.Boolean(
        string='Validate Immediately by Default',
        default=True,
        help='Default value for "Validate Immediately" toggle in Transfer Wizard',
    )

    def get_transfer_defaults(self):
        return {
            'src_location_ids': [(6,0,self.transfer_src_location_ids.ids)] if self.transfer_src_location_ids else [],
            'dst_location_ids': [(6,0,self.transfer_dst_location_ids.ids)] if self.transfer_dst_location_ids else [],
            'validate_immediately': self.transfer_validate_immediately,
        }

    # ── 11. PO DISTRIBUTION ──────────────────────────────────────────────
    po_dist_validate_immediately = fields.Boolean(
        string='Validate PO Distribution Immediately by Default',
        default=True,
        help='Default for "Validate Immediately" in PO Distribution Wizard',
    )
    po_dist_picking_type_id = fields.Many2one(
        'stock.picking.type',
        string='Default Operation Type (PO Distribution)',
        domain=[('code','=','internal')],
        help='Default internal operation type used when creating distribution transfers from PO receipts',
    )

    def get_po_dist_defaults(self):
        return {
            'validate_immediately': self.po_dist_validate_immediately,
            'picking_type_id': self.po_dist_picking_type_id.id if self.po_dist_picking_type_id else False,
        }

    # ── 5. FREE STOCK ────────────────────────────────────────────────────
    fs_metal_type    = fields.Selection([('all','All Metals'),('gold','GOLD Only'),('silver','SILVER Only'),('other','OTHER Only')], default='all', required=True, string='Metal Type')
    fs_brand_ids     = fields.Many2many('precious.metal.brand','pm_cfg_fs_brand_rel','cfg_id','brand_id', string='Default Brands')
    fs_hide_zero     = fields.Boolean('Hide Zero Stock by Default', default=True)
    fs_location_ids  = fields.Many2many('stock.location', 'pm_cfg_fs_loc_rel', 'cfg_id', 'loc_id', string='Default Locations', domain=[('usage','=','internal')])

    def get_fs_defaults(self):
        return {'x_metal_type': self.fs_metal_type or 'all', 'hide_zero': self.fs_hide_zero,
                'brand_ids':    [(6,0,self.fs_brand_ids.ids)]    if self.fs_brand_ids    else [],
                'location_ids': [(6,0,self.fs_location_ids.ids)] if self.fs_location_ids else []}

    # ── 6. PRODUCT LEDGER ────────────────────────────────────────────────
    ledger_period_type   = fields.Selection([('current_month','Current Month'),('current_day','Today'),('last_month','Last Full Month'),('custom','Custom Dates')], default='current_month', required=True, string='Period')
    ledger_time_from     = fields.Char('From (HH:MM)', default='00:00')
    ledger_time_to       = fields.Char('To (HH:MM)',   default='23:59')
    ledger_custom_from   = fields.Datetime('Custom From')
    ledger_custom_to     = fields.Datetime('Custom To')
    ledger_warehouse_ids = fields.Many2many('stock.warehouse','pm_cfg_ledger_wh_rel', 'cfg_id','wh_id',  string='Default Warehouses')
    ledger_location_ids  = fields.Many2many('stock.location', 'pm_cfg_ledger_loc_rel','cfg_id','loc_id', string='Default Locations', domain=[('usage','=','internal')])

    def get_ledger_defaults(self):
        df, dt = self._resolve_period(self.ledger_period_type, self.ledger_time_from, self.ledger_time_to, self.ledger_custom_from, self.ledger_custom_to)
        return {'datetime_from': df, 'datetime_to': dt,
                'warehouse_ids': [(6,0,self.ledger_warehouse_ids.ids)] if self.ledger_warehouse_ids else [],
                'location_ids':  [(6,0,self.ledger_location_ids.ids)]  if self.ledger_location_ids  else []}

    # ── 7. COMPARISON REPORT ─────────────────────────────────────────────
    cmp_metal_type    = fields.Selection([('all','All Metals'),('gold','GOLD Only'),('silver','SILVER Only'),('other','OTHER Only')], default='all', required=True, string='Metal Type')
    cmp_warehouse_ids = fields.Many2many('stock.warehouse','pm_cfg_cmp_wh_rel', 'cfg_id','wh_id',  string='Default Warehouses')
    cmp_location_ids  = fields.Many2many('stock.location', 'pm_cfg_cmp_loc_rel','cfg_id','loc_id', string='Default Locations', domain=[('usage','=','internal')])

    def get_cmp_defaults(self):
        return {'x_metal_type': self.cmp_metal_type or 'all',
                'warehouse_ids': [(6,0,self.cmp_warehouse_ids.ids)] if self.cmp_warehouse_ids else [],
                'location_ids':  [(6,0,self.cmp_location_ids.ids)]  if self.cmp_location_ids  else []}

    # ── 8. CUSTODY CHAIN REPORT ──────────────────────────────────────────
    custody_state_filter = fields.Selection([('all','All States'),('active','Active (not done)'),('done','Delivered Only'),('waiting','Waiting Only'),('custody','In Custody'),('custody_ready','Custody — Ready to Ship')], default='active', string='Default State Filter')
    custody_metal_type   = fields.Selection([('all','All Metals'),('gold','Gold Only'),('silver','Silver Only'),('other','Other')], default='all', string='Default Metal Type')
    custody_fulfillment  = fields.Selection([('all','All Types'),('branch_pickup','Branch Pickup Only'),('internal_delivery','Internal Delivery Only'),('external_delivery','External Delivery Only'),('storage','Storage Only')], default='all', string='Default Fulfillment Type')
    custody_group_by_1   = fields.Selection([('none','— None —'),('fulfillment_type','Fulfillment Type'),('channel','Channel'),('customer','Customer'),('state','State'),('metal_type','Metal Type'),('karat','Karat'),('responsible','Responsible')], default='fulfillment_type', string='Group By (Primary)')
    custody_group_by_2   = fields.Selection([('none','— None —'),('fulfillment_type','Fulfillment Type'),('channel','Channel'),('customer','Customer'),('state','State'),('metal_type','Metal Type'),('karat','Karat'),('responsible','Responsible')], default='channel', string='Group By (Secondary)')
    custody_show_journey = fields.Boolean('Show Journey Steps', default=True)
    custody_max_records  = fields.Integer('Max Records', default=500)

    def get_custody_defaults(self):
        return {'state_filter': self.custody_state_filter or 'active', 'metal_type_filter': self.custody_metal_type or 'all',
                'fulfillment_filter': self.custody_fulfillment or 'all', 'group_by_1': self.custody_group_by_1 or 'fulfillment_type',
                'group_by_2': self.custody_group_by_2 or 'channel', 'show_journey': self.custody_show_journey,
                'max_records': self.custody_max_records or 500,
                }

    # ── Label Settings ──────────────────────────────────────────────────────
    lbl_fulfillment_filter = fields.Selection([
        ('all',              'All Types'),
        ('branch_pickup',    'Branch Pickup'),
        ('internal_delivery','Internal Delivery'),
        ('external_delivery','External Delivery'),
    ], string='Default Delivery Type', default='all')
    lbl_state_filter = fields.Selection([
        ('all',          'All States'),
        ('active',       'Active (not done)'),
        ('done',         'Done / Delivered'),
        ('custody',      'In Custody'),
        ('waiting',      'Waiting'),
    ], string='Default State Filter', default='all')
    lbl_label_size       = fields.Selection([('a4','A4'),('a5','A5'),('a6','A6')], default='a4', string='Label Size')
    lbl_copies           = fields.Integer('Copies per Label', default=1)
    lbl_include_delivered= fields.Boolean('Include Delivered', default=False)
    lbl_show_products    = fields.Boolean('Show Products List', default=True)
    lbl_show_weight      = fields.Boolean('Show Weight (W21)', default=True)
    lbl_show_invoice     = fields.Boolean('Show Invoice Number', default=True)
    lbl_show_channel     = fields.Boolean('Show Channel', default=True)
    lbl_show_amount_due  = fields.Boolean('Show Amount Due', default=True)

    def get_lbl_defaults(self):
        return {
            'fulfillment_filter':  self.lbl_fulfillment_filter or 'all',
            'state_filter':        self.lbl_state_filter or 'all',
            'label_size':          self.lbl_label_size or 'a4',
            'copies':              self.lbl_copies or 1,
            'include_delivered':   self.lbl_include_delivered,
            'show_products':       self.lbl_show_products,
            'show_weight':         self.lbl_show_weight,
            'show_invoice':        self.lbl_show_invoice,
            'show_channel':        self.lbl_show_channel,
            'show_amount_due':     self.lbl_show_amount_due,
        }

    def action_run_stock_cron_now(self):
        """
        Manually trigger the auto-reserve cron immediately — processes ALL waiting records.
        Useful when the cron is lagging or stock just arrived and you want instant reservation.
        """
        import logging
        _logger = logging.getLogger(__name__)
        waiting_count = self.env['inventory.product.state'].search_count([
            ('state', '=', 'waiting'),
            ('is_being_processed', '=', False),
        ])
        _logger.info('[Manual Cron] Triggered by user %s — %d waiting records', self.env.user.name, waiting_count)
        self.env['inventory.product.state'].check_stock_and_update()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Auto-Reserve: Run Complete',
                'message': 'Processed %d waiting records. Check the Inventory Channel view for updates.' % waiting_count,
                'type': 'success',
                'sticky': False,
            },
        }
