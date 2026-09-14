"""
[2] Product Ledger — كشف حساب تفصيلي لمنتج واحد
    يُظهر كل حركة بالتاريخ والوقت والمصدر مع رصيد متراكم
"""
import io
import json
import xlsxwriter
import base64
from odoo import models, fields, api
from odoo.exceptions import ValidationError
from datetime import datetime


class ProductLedgerWizard(models.TransientModel):
    _name = 'product.ledger.wizard'
    _description = 'Product Movement Ledger'

    datetime_from = fields.Datetime(
        string='From', required=True,
        default=lambda self: datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0),
    )
    datetime_to = fields.Datetime(
        string='To', required=True,
        default=lambda self: datetime.now().replace(hour=23, minute=59, second=59, microsecond=0),
    )
    product_id = fields.Many2one(
        'product.template', string='Product', required=True,
        domain=[('x_metal_type', '!=', False)],
    )
    warehouse_ids = fields.Many2many('stock.warehouse', string='Warehouses')
    location_ids  = fields.Many2many('stock.location', string='Locations',
        domain=[('usage','=','internal')])
    report_data_json = fields.Text(default='{}')

    @api.constrains('datetime_from', 'datetime_to')
    def _check_dates(self):
        for rec in self:
            if rec.datetime_from > rec.datetime_to:
                raise ValidationError('From must be before To!')

    @api.model
    def _get_filename_label(self):
        """Channel/Location label for filenames — 'FINTECH', 'DM-STOCK', or 'All'."""
        if hasattr(self, 'division_ids') and self.division_ids:
            return '_'.join(d.name for d in self.division_ids[:3]).replace(' ', '-')
        if hasattr(self, 'location_ids') and self.location_ids:
            return '_'.join(l.name for l in self.location_ids[:3]).replace(' ', '-')
        if hasattr(self, 'warehouse_ids') and self.warehouse_ids:
            return '_'.join(w.name for w in self.warehouse_ids[:3]).replace(' ', '-')
        return 'All'

    def _get_export_filename(self, report_name, ext):
        """ReportName_LabelOrAll_YYYYMMDD_HHMM.ext"""
        from datetime import datetime as _dt
        label    = self._get_filename_label()
        date_str = _dt.now().strftime('%Y%m%d_%H%M')
        return f"{report_name}_{label}_{date_str}.{ext}"


    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        try:
            config = self.env['precious.metal.report.config'].get_config()
            if config:
                defaults = config.get_ledger_defaults()
                res.update({k: v for k, v in defaults.items() if v or v == False})
        except Exception:
            pass  # never block the wizard from opening
        return res

    def action_show_report(self):
        """Open report as HTML in browser (Show Report button)."""
        data = self._get_report_data()
        self.sudo().write({'report_data_json': json.dumps(data, ensure_ascii=False)})
        return self.env.ref(
            'precious_metals_suite.action_report_product_ledger'
        ).report_action(self)

    def action_save_pdf(self):
        """Download report as PDF file."""
        import json as _json
        data = self._get_report_data()
        self.sudo().write({'report_data_json': _json.dumps(data, ensure_ascii=False)})
        pdf_name = self._get_export_filename('ProductLedger', 'pdf')
        return self.env.ref('precious_metals_suite.action_report_product_ledger_pdf').report_action(self, data={'pdf_filename': pdf_name})

    def action_export_excel(self):
        data = self._get_report_data()
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})

        title_fmt  = workbook.add_format({'bold': True, 'font_size': 13, 'font_color': '#8B6914'})
        sub_fmt    = workbook.add_format({'italic': True, 'font_color': '#888'})
        hdr_fmt    = workbook.add_format({'bold': True, 'bg_color': '#8B6914', 'font_color': 'white',
                                          'border': 1, 'align': 'center', 'text_wrap': True})
        str_fmt    = workbook.add_format({'border': 1})
        in_qty_fmt = workbook.add_format({'border': 1, 'align': 'center', 'bg_color': '#e8f5e9', 'num_format': '#,##0'})
        in_w21_fmt = workbook.add_format({'border': 1, 'align': 'center', 'bg_color': '#e8f5e9', 'num_format': '#,##0.000'})
        out_qty_fmt= workbook.add_format({'border': 1, 'align': 'center', 'bg_color': '#fce4ec', 'num_format': '#,##0'})
        out_w21_fmt= workbook.add_format({'border': 1, 'align': 'center', 'bg_color': '#fce4ec', 'num_format': '#,##0.000'})
        bal_qty_fmt= workbook.add_format({'bold': True, 'border': 1, 'align': 'center', 'bg_color': '#fff3e0', 'num_format': '#,##0'})
        bal_w21_fmt= workbook.add_format({'bold': True, 'border': 1, 'align': 'center', 'bg_color': '#fff3e0', 'num_format': '#,##0.000'})
        num_fmt    = workbook.add_format({'border': 1, 'align': 'center', 'num_format': '#,##0'})
        dt_fmt     = workbook.add_format({'border': 1, 'num_format': 'yyyy-mm-dd hh:mm'})
        adj_fmt    = workbook.add_format({'border': 1, 'align': 'center', 'bg_color': '#fff9c4', 'num_format': '#,##0'})
        adj_w21_fmt= workbook.add_format({'border': 1, 'align': 'center', 'bg_color': '#fff9c4', 'num_format': '#,##0.000'})
        footer_fmt = workbook.add_format({'italic': True, 'font_color': '#aaa', 'font_size': 8})

        ws = workbook.add_worksheet('Ledger')
        ws.set_column(0, 0, 18)   # Date
        ws.set_column(1, 1, 14)   # Type
        ws.set_column(2, 2, 25)   # Reference
        ws.set_column(3, 3, 20)   # Partner
        ws.set_column(4, 4, 10)   # IN Qty
        ws.set_column(5, 5, 12)   # IN W21
        ws.set_column(6, 6, 10)   # OUT Qty
        ws.set_column(7, 7, 12)   # OUT W21
        ws.set_column(8, 8, 12)   # Balance Qty
        ws.set_column(9, 9, 14)   # Balance W21

        ws.merge_range('A1:J1', f"Product Ledger — {data['product_name']}", title_fmt)
        ws.merge_range('A2:J2',
            f"From: {data['datetime_from']}  →  To: {data['datetime_to']}  |  "
            f"Opening Balance: {data['opening_qty']:,} pcs  |  W21: {data['opening_w21']:,.3f}g",
            sub_fmt)

        headers = ['Date & Time', 'Move Type', 'Reference', 'Partner/Source',
                   'IN (Qty)', 'IN (W21)', 'OUT (Qty)', 'OUT (W21)',
                   'Balance (Qty)', 'Balance W21']
        for i, h in enumerate(headers):
            ws.write(2, i, h, hdr_fmt)

        row_idx = 3
        # Opening Balance row
        ob_fmt = workbook.add_format({'bold': True, 'bg_color': '#e8eaf6', 'border': 1,
                                       'align': 'center', 'font_color': '#1a237e'})
        ob_qty_fmt = workbook.add_format({'bold': True, 'bg_color': '#c5cae9', 'border': 1,
                                           'align': 'center', 'font_color': '#1a237e', 'num_format': '#,##0'})
        ob_w21_fmt = workbook.add_format({'bold': True, 'bg_color': '#c5cae9', 'border': 1,
                                           'align': 'center', 'font_color': '#1a237e', 'num_format': '#,##0.000'})
        ws.write(row_idx, 0, '—', ob_fmt)
        ws.write(row_idx, 1, 'Opening Balance', ob_fmt)
        ws.write(row_idx, 2, '—', ob_fmt)
        ws.write(row_idx, 3, '—', ob_fmt)
        ws.write(row_idx, 4, '—', ob_fmt)
        ws.write(row_idx, 5, '—', ob_fmt)
        ws.write(row_idx, 6, '—', ob_fmt)
        ws.write(row_idx, 7, '—', ob_fmt)
        ws.write_number(row_idx, 8, data['opening_qty'], ob_qty_fmt)
        ws.write_number(row_idx, 9, data['opening_w21'], ob_w21_fmt)
        row_idx += 1

        for line in data['lines']:
            mt = line['move_type']
            is_in  = line['qty_in'] > 0
            is_adj = mt == 'Adjustment'

            q_in_fmt  = adj_fmt     if is_adj else (in_qty_fmt  if is_in else num_fmt)
            w_in_fmt  = adj_w21_fmt if is_adj else (in_w21_fmt  if is_in else workbook.add_format({'border':1,'align':'center','num_format':'#,##0.000'}))
            q_out_fmt = adj_fmt     if is_adj else (out_qty_fmt if not is_in else num_fmt)
            w_out_fmt = adj_w21_fmt if is_adj else (out_w21_fmt if not is_in else workbook.add_format({'border':1,'align':'center','num_format':'#,##0.000'}))

            ws.write(row_idx, 0, line['date'], dt_fmt)
            ws.write(row_idx, 1, mt, adj_fmt if is_adj else (in_qty_fmt if is_in else out_qty_fmt))
            ws.write(row_idx, 2, line['reference'], str_fmt)
            ws.write(row_idx, 3, line['partner'], str_fmt)
            ws.write_number(row_idx, 4, line['qty_in'],  q_in_fmt)
            ws.write_number(row_idx, 5, line['w21_in'],  w_in_fmt)
            ws.write_number(row_idx, 6, line['qty_out'], q_out_fmt)
            ws.write_number(row_idx, 7, line['w21_out'], w_out_fmt)
            ws.write_number(row_idx, 8, line['balance_qty'], bal_qty_fmt)
            ws.write_number(row_idx, 9, line['balance_w21'], bal_w21_fmt)
            row_idx += 1

        # Summary row
        row_idx += 1
        ws.write(row_idx, 0, 'CLOSING BALANCE', hdr_fmt)
        ws.write_number(row_idx, 8, data['closing_qty'], bal_qty_fmt)
        ws.write_number(row_idx, 9, data['closing_w21'], bal_w21_fmt)
        row_idx += 2
        ws.merge_range(row_idx, 0, row_idx, 9,
            f"Printed by: {data['printed_by']}  |  {data['printed_at']}", footer_fmt)

        workbook.close(); output.seek(0)
        xlsx_data = base64.b64encode(output.read()).decode()
        attachment = self.env['ir.attachment'].create({
            'name': self._get_export_filename('ProductLedger', 'xlsx'),
            'type': 'binary', 'datas': xlsx_data,
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        })
        return {'type': 'ir.actions.act_url',
                'url': f'/web/content/{attachment.id}?download=true', 'target': 'self'}

    # ── Core ───────────────────────────────────────────────────────────────
    def _get_report_data(self):
        self.ensure_one()
        tmpl = self.product_id
        prod_ids = tmpl.product_variant_ids.ids

        # Locations — use view_location_id to capture ALL warehouse sub-locations
        if self.location_ids:
            loc_ids = self.location_ids.ids
        else:
            warehouses = self.warehouse_ids or self.env['stock.warehouse'].search([])
            all_locs = self.env['stock.location']
            for wh in warehouses:
                wh_root_id = wh.view_location_id.id if wh.view_location_id else wh.lot_stock_id.id
                locs = self.env['stock.location'].search([
                    ('id', 'child_of', wh_root_id),
                    ('usage', '=', 'internal'),
                ])
                all_locs |= locs
            loc_ids = all_locs.ids

        # W21 ratio
        metal_w = tmpl.x_gold_weight
        gold_k  = tmpl.x_karat
        mtype   = tmpl.x_metal_type
        try:
            gold_k_float = float(gold_k) if gold_k and gold_k not in ('Silver', '0', '') else 0.0
        except (ValueError, TypeError):
            gold_k_float = 0.0
        if mtype == 'gold' and gold_k_float and metal_w:
            w21u = (metal_w * gold_k_float) / 875.0
        elif mtype == 'silver' and metal_w:
            w21u = metal_w
        else:
            w21u = 0.0

        dt_from = str(self.datetime_from)
        dt_to   = str(self.datetime_to)

        # Opening balance (before datetime_from)
        Move = self.env['stock.move']
        in_d  = Move.read_group([('product_id','in',prod_ids),('location_dest_id','in',loc_ids),
            ('state','=','done'),('date','<',dt_from)], ['product_uom_qty:sum'], [])
        out_d = Move.read_group([('product_id','in',prod_ids),('location_id','in',loc_ids),
            ('state','=','done'),('date','<',dt_from)], ['product_uom_qty:sum'], [])
        opening_qty = (in_d[0]['product_uom_qty'] if in_d and in_d[0]['product_uom_qty'] else 0.0) \
                    - (out_d[0]['product_uom_qty'] if out_d and out_d[0]['product_uom_qty'] else 0.0)
        opening_w21 = opening_qty * w21u

        # All moves in period
        moves = Move.search([
            ('product_id', 'in', prod_ids),
            ('state', '=', 'done'),
            ('date', '>=', dt_from),
            ('date', '<=', dt_to),
        ], order='date asc, id asc')

        lines = []
        balance_qty = opening_qty
        balance_w21 = opening_w21

        for mv in moves:
            dest_in_loc = mv.location_dest_id.id in loc_ids
            src_in_loc  = mv.location_id.id in loc_ids
            if not dest_in_loc and not src_in_loc:
                continue

            qty = mv.product_uom_qty
            if dest_in_loc and not src_in_loc:
                qty_in, qty_out = qty, 0.0
                balance_qty += qty
            elif src_in_loc and not dest_in_loc:
                qty_in, qty_out = 0.0, qty
                balance_qty -= qty
            else:
                continue  # internal move between tracked locs

            balance_w21 = balance_qty * w21u

            # Move type label
            src_usage  = mv.location_id.usage
            dest_usage = mv.location_dest_id.usage
            if src_usage == 'supplier':
                mt = 'Purchase'
            elif dest_usage == 'customer':
                mt = 'Sale'
            elif src_usage == 'production':
                mt = 'Manufacturing'
            elif src_usage == 'inventory' or dest_usage == 'inventory':
                mt = 'Adjustment'
            elif src_usage == 'internal' and dest_usage == 'internal':
                mt = 'Transfer'
            else:
                mt = 'Other'

            ref = mv.reference or mv.origin or ''
            partner = ''
            if mv.picking_id and mv.picking_id.partner_id:
                partner = mv.picking_id.partner_id.name or ''

            lines.append({
                'date':        mv.date.strftime('%Y-%m-%d %H:%M') if mv.date else '',
                'move_type':   mt,
                'reference':   ref,
                'partner':     partner,
                'qty_in':      int(round(qty_in)),
                'qty_out':     int(round(qty_out)),
                'w21_in':      round(qty_in  * w21u, 3),
                'w21_out':     round(qty_out * w21u, 3),
                'balance_qty': int(round(balance_qty)),
                'balance_w21': round(balance_w21, 3),
            })

        return {
            'product_name':  tmpl.name,
            'brand':         tmpl.precious_metal_brand_id.name or '',
            'x_metal_type':  (mtype or '').upper(),
            'karat_display': tmpl.karat_display or '',
            'datetime_from': dt_from,
            'datetime_to':   dt_to,
            'opening_qty':   int(round(opening_qty)),
            'opening_w21':   round(opening_w21, 3),
            'closing_qty':   int(round(balance_qty)),
            'closing_w21':   round(balance_w21, 3),
            'lines':         lines,
            'printed_by':    self.env.user.name,
            'printed_at':    datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        }
