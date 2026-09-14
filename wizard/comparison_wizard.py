"""
[6] Comparison Report — مقارنة فترتين جنباً إلى جنب
"""
import io
import json
import xlsxwriter
import base64
from odoo import models, fields, api
from odoo.exceptions import ValidationError
from datetime import datetime


class ComparisonWizard(models.TransientModel):
    _name = 'comparison.report.wizard'
    _description = 'Period Comparison Report'

    # Period A
    period_a_from = fields.Datetime(string='Period A — From', required=True,
        default=lambda self: datetime.now().replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0))
    period_a_to   = fields.Datetime(string='Period A — To', required=True,
        default=lambda self: datetime.now().replace(month=6, day=30, hour=23, minute=59, second=59, microsecond=0))
    period_a_label = fields.Char(string='Label A', default='Period A')

    # Period B
    period_b_from = fields.Datetime(string='Period B — From', required=True,
        default=lambda self: datetime.now().replace(month=7, day=1, hour=0, minute=0, second=0, microsecond=0))
    period_b_to   = fields.Datetime(string='Period B — To', required=True,
        default=lambda self: datetime.now().replace(hour=23, minute=59, second=59, microsecond=0))
    period_b_label = fields.Char(string='Label B', default='Period B')

    x_metal_type = fields.Selection(
        selection=[('all','All Metals'),('gold','GOLD Only'),('silver','SILVER Only'),('other','OTHER Only')],
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
                defaults = config.get_cmp_defaults()
                res.update({k: v for k, v in defaults.items() if v or v == False})
        except Exception:
            pass  # never block the wizard from opening
        return res

    @api.constrains('period_a_from','period_a_to','period_b_from','period_b_to')
    def _check_dates(self):
        for rec in self:
            if rec.period_a_from >= rec.period_a_to:
                raise ValidationError('Period A: From must be before To!')
            if rec.period_b_from >= rec.period_b_to:
                raise ValidationError('Period B: From must be before To!')

    def action_show_report(self):
        """Open report as HTML in browser (Show Report button)."""
        data = self._get_report_data()
        self.sudo().write({'report_data_json': json.dumps(data, ensure_ascii=False)})
        return self.env.ref(
            'precious_metals_suite.action_report_comparison'
        ).report_action(self)

    def action_save_pdf(self):
        """Download report as PDF file."""
        import json as _json
        data = self._get_report_data()
        self.sudo().write({'report_data_json': _json.dumps(data, ensure_ascii=False)})
        pdf_name = self._get_export_filename('Comparison', 'pdf')
        return self.env.ref('precious_metals_suite.action_report_comparison_pdf').report_action(self, data={'pdf_filename': pdf_name})

    def action_export_excel(self):
        data = self._get_report_data()
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})

        title_fmt  = workbook.add_format({'bold': True, 'font_size': 13, 'font_color': '#8B6914'})
        sub_fmt    = workbook.add_format({'italic': True, 'font_color': '#888'})
        hdr_fmt    = workbook.add_format({'bold': True, 'bg_color': '#8B6914', 'font_color': 'white',
                                          'border': 1, 'align': 'center', 'text_wrap': True})
        a_hdr      = workbook.add_format({'bold': True, 'bg_color': '#1565C0', 'font_color': 'white',
                                          'border': 1, 'align': 'center'})
        b_hdr      = workbook.add_format({'bold': True, 'bg_color': '#2E7D32', 'font_color': 'white',
                                          'border': 1, 'align': 'center'})
        diff_hdr   = workbook.add_format({'bold': True, 'bg_color': '#6A1B9A', 'font_color': 'white',
                                          'border': 1, 'align': 'center'})
        str_fmt    = workbook.add_format({'border': 1})
        a_fmt      = workbook.add_format({'border': 1, 'align': 'center', 'bg_color': '#E3F2FD', 'num_format': '#,##0.000'})
        b_fmt      = workbook.add_format({'border': 1, 'align': 'center', 'bg_color': '#E8F5E9', 'num_format': '#,##0.000'})
        pos_fmt    = workbook.add_format({'border': 1, 'align': 'center', 'bg_color': '#F3E5F5', 'font_color': '#2E7D32', 'num_format': '+#,##0.000;-#,##0.000'})
        neg_fmt    = workbook.add_format({'border': 1, 'align': 'center', 'bg_color': '#F3E5F5', 'font_color': '#C62828', 'num_format': '+#,##0.000;-#,##0.000'})
        footer_fmt = workbook.add_format({'italic': True, 'font_color': '#aaa', 'font_size': 8})
        la = data['label_a']
        lb = data['label_b']

        ws = workbook.add_worksheet('Comparison')
        ws.set_column(0, 0, 22); ws.set_column(1, 1, 10); ws.set_column(2, 2, 10)
        for c in range(3, 11): ws.set_column(c, c, 13)

        ws.merge_range('A1:K1', f"Comparison Report: {la} vs {lb}", title_fmt)
        ws.merge_range('A2:K2',
            f"{la}: {data['period_a_from']} → {data['period_a_to']}   |   "
            f"{lb}: {data['period_b_from']} → {data['period_b_to']}", sub_fmt)

        # Header row 1
        ws.merge_range(2, 0, 3, 0, 'Product', hdr_fmt)
        ws.merge_range(2, 1, 3, 1, 'Type', hdr_fmt)
        ws.merge_range(2, 2, 3, 2, 'Karat', hdr_fmt)
        ws.merge_range(2, 3, 2, 4, f'{la} — Closing', a_hdr)
        ws.merge_range(2, 5, 2, 6, f'{lb} — Closing', b_hdr)
        ws.merge_range(2, 7, 2, 8, f'{la} — IN', a_hdr)
        ws.merge_range(2, 9, 2, 10, f'{lb} — IN', b_hdr)
        for c in [3,5,7,9]: ws.write(3, c, 'Qty', a_hdr if c in [3,7] else b_hdr)
        for c in [4,6,8,10]: ws.write(3, c, 'W21', a_hdr if c in [4,8] else b_hdr)

        row_idx = 4
        for row in data['rows']:
            ws.write(row_idx, 0, row['product'], str_fmt)
            ws.write(row_idx, 1, row['x_metal_type'], str_fmt)
            ws.write(row_idx, 2, row['karat_display'], str_fmt)
            ws.write_number(row_idx, 3, row['a_closing_qty'], a_fmt)
            ws.write_number(row_idx, 4, row['a_closing_w21'], a_fmt)
            ws.write_number(row_idx, 5, row['b_closing_qty'], b_fmt)
            ws.write_number(row_idx, 6, row['b_closing_w21'], b_fmt)
            ws.write_number(row_idx, 7, row['a_in_qty'], a_fmt)
            ws.write_number(row_idx, 8, row['a_in_w21'], a_fmt)
            ws.write_number(row_idx, 9, row['b_in_qty'], b_fmt)
            ws.write_number(row_idx, 10, row['b_in_w21'], b_fmt)
            row_idx += 1

        row_idx += 2
        ws.merge_range(row_idx, 0, row_idx, 10,
            f"Printed by: {data['printed_by']}  |  {data['printed_at']}", footer_fmt)

        workbook.close(); output.seek(0)
        xlsx_data = base64.b64encode(output.read()).decode()
        attachment = self.env['ir.attachment'].create({
            'name': self._get_export_filename('Comparison', 'xlsx'),
            'type': 'binary', 'datas': xlsx_data,
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        })
        return {'type': 'ir.actions.act_url',
                'url': f'/web/content/{attachment.id}?download=true', 'target': 'self'}

    def _get_report_data(self):
        self.ensure_one()
        domain = [('x_metal_type', '!=', False)]
        if self.x_metal_type != 'all':
            domain.append(('x_metal_type', '=', self.x_metal_type))
        if self.brand_ids:
            domain.append(('precious_metal_brand_id', 'in', self.brand_ids.ids))
        if self.product_ids:
            domain.append(('id', 'in', self.product_ids.ids))
        product_tmpls = self.env['product.template'].search(domain)
        product_tmpls = product_tmpls.sorted(key=lambda t: (
            (t.precious_metal_brand_id.name or 'zzzzz').lower(),
            -(float(t.x_karat) if t.x_metal_type == 'gold' and t.x_karat and t.x_karat not in ('Silver','0','') else (999.9 if t.x_metal_type == 'silver' else 0.0)),
            -(t.x_gold_weight or 0.0),
        ))

        if self.location_ids:
            # Expand to include all child internal locations of the selected locations
            loc_ids = self.env['stock.location'].search([
                ('id', 'child_of', self.location_ids.ids),
                ('usage', '=', 'internal'),
            ]).ids or self.location_ids.ids
        else:
            warehouses = self.warehouse_ids or self.env['stock.warehouse'].search([])
            loc_ids = []
            for wh in warehouses:
                locs = self.env['stock.location'].search([
                    ('id', 'child_of', wh.lot_stock_id.id), ('usage', '=', 'internal')])
                loc_ids.extend(locs.ids)

        rows = []
        for tmpl in product_tmpls:
            prod_ids = tmpl.product_variant_ids.ids
            if not prod_ids:
                continue
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
            ratio = w21u  # W21 لكل قطعة واحدة - نضرب في عدد القطع مباشرة

            def closing(dt_from, dt_to):
                Move = self.env['stock.move']
                in_d = Move.read_group([('product_id','in',prod_ids),('location_dest_id','in',loc_ids),
                    ('state','=','done'),('date','<',str(dt_to))],['product_uom_qty:sum'],[])
                out_d = Move.read_group([('product_id','in',prod_ids),('location_id','in',loc_ids),
                    ('state','=','done'),('date','<',str(dt_to))],['product_uom_qty:sum'],[])
                qi = in_d[0]['product_uom_qty']  if in_d  and in_d[0]['product_uom_qty']  else 0.0
                qo = out_d[0]['product_uom_qty'] if out_d and out_d[0]['product_uom_qty'] else 0.0
                return qi - qo

            def total_in(dt_from, dt_to):
                Move = self.env['stock.move']
                r = Move.read_group([('product_id','in',prod_ids),('location_dest_id','in',loc_ids),
                    ('state','=','done'),('date','>=',str(dt_from)),('date','<=',str(dt_to))],
                    ['product_uom_qty:sum'],[])
                return r[0]['product_uom_qty'] if r and r[0]['product_uom_qty'] else 0.0

            ac = closing(self.period_a_from, self.period_a_to)
            bc = closing(self.period_b_from, self.period_b_to)
            ai = total_in(self.period_a_from, self.period_a_to)
            bi = total_in(self.period_b_from, self.period_b_to)

            rows.append({
                'product':       tmpl.name,
                'brand':         tmpl.precious_metal_brand_id.name or '',
                'x_metal_type':    (mtype or '').upper(),
                'karat_display': tmpl.karat_display or '',
                'a_closing_qty': round(ac, 3), 'a_closing_w21': ac * ratio,
                'b_closing_qty': round(bc, 3), 'b_closing_w21': bc * ratio,
                'a_in_qty':      round(ai, 3), 'a_in_w21':      ai * ratio,
                'b_in_qty':      round(bi, 3), 'b_in_w21':      bi * ratio,
                'diff_closing_qty': round(bc - ac, 3),
                'diff_closing_w21': (bc - ac) * ratio,
            })

        return {
            'label_a':      self.period_a_label or 'Period A',
            'label_b':      self.period_b_label or 'Period B',
            'period_a_from': str(self.period_a_from),
            'period_a_to':   str(self.period_a_to),
            'period_b_from': str(self.period_b_from),
            'period_b_to':   str(self.period_b_to),
            'x_metal_type':    self.x_metal_type,
            'location_ids':  self.location_ids.ids,
            'rows':          rows,
            'printed_by':    self.env.user.name,
            'printed_at':    datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        }
