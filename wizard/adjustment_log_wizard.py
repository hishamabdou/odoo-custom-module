"""
[3] Adjustment Log — سجل التعديلات اليدوية
    يُظهر كل عملية Product Quantity Updated بالتفصيل
"""
import io
import json
import xlsxwriter
import base64
from odoo import models, fields, api
from odoo.exceptions import ValidationError
from datetime import datetime


class AdjustmentLogWizard(models.TransientModel):
    _name = 'adjustment.log.wizard'
    _description = 'Inventory Adjustment Log'

    datetime_from = fields.Datetime(
        string='From', required=True,
        default=lambda self: datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0),
    )
    datetime_to = fields.Datetime(
        string='To', required=True,
        default=lambda self: datetime.now().replace(hour=23, minute=59, second=59, microsecond=0),
    )
    x_metal_type = fields.Selection(
        selection=[('all','All'),('gold','GOLD'),('silver','SILVER'),('other','OTHER')],
        string='Metal Type', default='all', required=True)
    warehouse_ids = fields.Many2many('stock.warehouse', string='Warehouses')
    location_ids  = fields.Many2many('stock.location', string='Locations',
        domain=[('usage','=','internal')])
    brand_ids     = fields.Many2many('precious.metal.brand', string='Brands')
    product_ids   = fields.Many2many('product.template', string='Products',
        domain=[('x_metal_type','!=',False)])
    report_data_json = fields.Text(default='{}')

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
                defaults = config.get_adj_defaults()
                res.update({k: v for k, v in defaults.items() if v or v == False})
        except Exception:
            pass  # never block the wizard from opening
        return res

    @api.constrains('datetime_from', 'datetime_to')
    def _check_dates(self):
        for rec in self:
            if rec.datetime_from > rec.datetime_to:
                raise ValidationError('From must be before To!')

    def action_show_report(self):
        """Open report as HTML in browser (Show Report button)."""
        data = self._get_report_data()
        self.sudo().write({'report_data_json': json.dumps(data, ensure_ascii=False)})
        return self.env.ref(
            'precious_metals_suite.action_report_adjustment_log'
        ).report_action(self)

    def action_save_pdf(self):
        """Download report as PDF file."""
        import json as _json
        data = self._get_report_data()
        self.sudo().write({'report_data_json': _json.dumps(data, ensure_ascii=False)})
        pdf_name = self._get_export_filename('AdjustmentLog', 'pdf')
        return self.env.ref('precious_metals_suite.action_report_adjustment_log_pdf').report_action(self, data={'pdf_filename': pdf_name})

    def action_export_excel(self):
        data = self._get_report_data()
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})

        title_fmt  = workbook.add_format({'bold': True, 'font_size': 13, 'font_color': '#8B6914'})
        sub_fmt    = workbook.add_format({'italic': True, 'font_color': '#888'})
        hdr_fmt    = workbook.add_format({'bold': True, 'bg_color': '#8B6914', 'font_color': 'white',
                                          'border': 1, 'align': 'center', 'text_wrap': True})
        str_fmt    = workbook.add_format({'border': 1})
        pos_fmt    = workbook.add_format({'border': 1, 'align': 'center', 'bg_color': '#e8f5e9', 'num_format': '#,##0.000'})
        neg_fmt    = workbook.add_format({'border': 1, 'align': 'center', 'bg_color': '#fce4ec', 'num_format': '#,##0.000'})
        num_fmt    = workbook.add_format({'border': 1, 'align': 'center', 'num_format': '#,##0.000'})
        dt_fmt     = workbook.add_format({'border': 1, 'num_format': 'yyyy-mm-dd hh:mm'})
        footer_fmt = workbook.add_format({'italic': True, 'font_color': '#aaa', 'font_size': 8})

        ws = workbook.add_worksheet('Adjustments')
        ws.set_column(0, 0, 18)
        ws.set_column(1, 1, 22)
        ws.set_column(2, 2, 12)
        ws.set_column(3, 3, 10)
        ws.set_column(4, 4, 10)
        ws.set_column(5, 5, 14)
        ws.set_column(6, 6, 14)
        ws.set_column(7, 7, 20)

        ws.merge_range('A1:H1', 'Inventory Adjustment Log — Precious Metals', title_fmt)
        ws.merge_range('A2:H2',
            f"From: {data['datetime_from']}  →  To: {data['datetime_to']}  |  "
            f"Total Adjustments: {len(data['lines'])}", sub_fmt)

        headers = ['Date & Time', 'Product', 'Brand', 'Type', 'Karat',
                   'Δ Qty', 'Δ W21', 'Reference / Note']
        for i, h in enumerate(headers):
            ws.write(2, i, h, hdr_fmt)

        row_idx = 3
        for line in data['lines']:
            delta = line['delta_qty']
            ws.write(row_idx, 0, line['date'], dt_fmt)
            ws.write(row_idx, 1, line['product'], str_fmt)
            ws.write(row_idx, 2, line['brand'], str_fmt)
            ws.write(row_idx, 3, line['x_metal_type'], str_fmt)
            ws.write(row_idx, 4, line['karat_display'], str_fmt)
            ws.write_number(row_idx, 5, delta, pos_fmt if delta >= 0 else neg_fmt)
            ws.write_number(row_idx, 6, line['delta_w21'], pos_fmt if delta >= 0 else neg_fmt)
            ws.write(row_idx, 7, line['reference'], str_fmt)
            row_idx += 1

        row_idx += 2
        ws.merge_range(row_idx, 0, row_idx, 7,
            f"Printed by: {data['printed_by']}  |  {data['printed_at']}", footer_fmt)

        workbook.close(); output.seek(0)
        xlsx_data = base64.b64encode(output.read()).decode()
        attachment = self.env['ir.attachment'].create({
            'name': self._get_export_filename('AdjustmentLog', 'xlsx'),
            'type': 'binary', 'datas': xlsx_data,
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        })
        return {'type': 'ir.actions.act_url',
                'url': f'/web/content/{attachment.id}?download=true', 'target': 'self'}

    def _get_report_data(self):
        self.ensure_one()
        dt_from = str(self.datetime_from)
        dt_to   = str(self.datetime_to)

        prod_domain = [('x_metal_type', '!=', False)]
        if self.x_metal_type != 'all':
            prod_domain.append(('x_metal_type', '=', self.x_metal_type))
        if self.brand_ids:
            prod_domain.append(('precious_metal_brand_id', 'in', self.brand_ids.ids))
        if self.product_ids:
            prod_domain.append(('id', 'in', self.product_ids.ids))
        product_tmpls = self.env['product.template'].search(prod_domain)
        prod_ids = product_tmpls.mapped('product_variant_ids').ids

        # Locations
        if self.location_ids:
            # Expand to include all child internal locations of the selected locations
            loc_ids = self.env['stock.location'].search([
                ('id', 'child_of', self.location_ids.ids),
                ('usage', '=', 'internal'),
            ]).ids or self.location_ids.ids
        elif self.warehouse_ids:
            loc_recs = self.env['stock.location']
            for wh in self.warehouse_ids:
                loc_recs |= self.env['stock.location'].search([
                    ('id', 'child_of', wh.lot_stock_id.id), ('usage', '=', 'internal')])
            loc_ids = loc_recs.ids
        else:
            loc_ids = self.env['stock.location'].search([('usage','=','internal')]).ids

        # Find adjustment moves: moves from/to virtual location with usage='inventory'
        move_domain = [
            ('product_id', 'in', prod_ids),
            ('state', '=', 'done'),
            ('date', '>=', dt_from),
            ('date', '<=', dt_to),
        ]
        # Adjustment = location or dest has usage='inventory'
        # + مرتبطة بالـ locations المحددة
        adj_moves = self.env['stock.move'].search(move_domain + [
            '|',
            ('location_id.usage', '=', 'inventory'),
            ('location_dest_id.usage', '=', 'inventory'),
            '|',
            ('location_dest_id', 'in', loc_ids),
            ('location_id', 'in', loc_ids),
        ], order='date asc')

        # Build tmpl lookup
        variant_to_tmpl = {}
        for tmpl in product_tmpls:
            for v in tmpl.product_variant_ids:
                variant_to_tmpl[v.id] = tmpl

        lines = []
        for mv in adj_moves:
            tmpl = variant_to_tmpl.get(mv.product_id.id)
            if not tmpl:
                continue

            # delta: positive if goes INTO stock, negative if goes OUT
            dest_is_stock = mv.location_dest_id.usage == 'internal'
            if dest_is_stock:
                delta_qty = mv.product_uom_qty
            else:
                delta_qty = -mv.product_uom_qty

            metal_w = tmpl.x_gold_weight
            gold_k  = tmpl.x_karat  # Char في gold_pricing1
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

            lines.append({
                'date':          mv.date.strftime('%Y-%m-%d %H:%M') if mv.date else '',
                'product':       tmpl.name,
                'brand':         tmpl.precious_metal_brand_id.name or '',
                'x_metal_type':    (mtype or '').upper(),
                'karat_display': tmpl.karat_display or '',
                'delta_qty':     round(delta_qty, 3),
                'delta_w21':     delta_qty * w21u,
                'reference':     mv.reference or mv.origin or '',
            })

        return {
            'datetime_from': dt_from,
            'datetime_to':   dt_to,
            'lines':         lines,
            'printed_by':    self.env.user.name,
            'printed_at':    datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        }
