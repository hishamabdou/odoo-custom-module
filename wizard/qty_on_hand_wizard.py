import io
import json
import xlsxwriter
import base64
from odoo import models, fields, api
from odoo.exceptions import ValidationError
from datetime import date


class QtyOnHandWizard(models.TransientModel):
    _name = 'qty.on.hand.wizard'
    _description = 'Precious Metals QTY ON HAND Report'

    as_of_date = fields.Date(
        string='As of Date',
        required=True,
        default=fields.Date.today,
        help='Show closing stock as of this date (end of day)',
    )
    x_metal_type = fields.Selection(
        selection=[('all','All Metals'),('gold','GOLD Only'),('silver','SILVER Only'),('other','OTHER Only')],
        string='Metal Type', default='all', required=True,
    )
    warehouse_ids = fields.Many2many('stock.warehouse', string='Warehouses',
        help='Leave empty = all warehouses')
    location_ids  = fields.Many2many('stock.location', string='Locations',
        domain=[('usage','=','internal')],
        help='Leave empty = all locations in selected warehouses')
    brand_ids     = fields.Many2many('precious.metal.brand', string='Brands',
        help='Leave empty = all brands')
    product_ids   = fields.Many2many('product.template', string='Products',
        domain=[('x_metal_type','!=',False)])
    hide_zero     = fields.Boolean(string='Hide Zero Balances', default=True)
    report_data_json = fields.Text(default='{}')

    # ── Actions ────────────────────────────────────────────────────────────
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
                defaults = config.get_qoh_defaults()
                res.update({k: v for k, v in defaults.items() if v or v == False})
        except Exception:
            pass  # never block the wizard from opening
        return res

    def action_show_report(self):
        """Open report as HTML in browser (Show Report button)."""
        data = self._get_report_data()
        self.sudo().write({'report_data_json': json.dumps(data, ensure_ascii=False)})
        return self.env.ref(
            'precious_metals_suite.action_report_qty_on_hand'
        ).report_action(self)

    def action_save_pdf(self):
        """Download report as PDF file."""
        import json as _json
        data = self._get_report_data()
        self.sudo().write({'report_data_json': _json.dumps(data, ensure_ascii=False)})
        pdf_name = self._get_export_filename('QtyOnHand', 'pdf')
        return self.env.ref('precious_metals_suite.action_report_qty_on_hand_pdf').report_action(self, data={'pdf_filename': pdf_name})

    def action_export_excel(self):
        data = self._get_report_data()
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})

        # ── Formats ───────────────────────────────────────────────────────
        title_fmt  = workbook.add_format({'bold': True, 'font_size': 14, 'font_color': '#8B6914'})
        sub_fmt    = workbook.add_format({'italic': True, 'font_color': '#888888', 'font_size': 10})
        hdr_fmt    = workbook.add_format({'bold': True, 'bg_color': '#8B6914', 'font_color': 'white',
                                          'border': 1, 'align': 'center', 'valign': 'vcenter', 'text_wrap': True})
        brand_fmt  = workbook.add_format({'bold': True, 'bg_color': '#f5e6c8', 'border': 1,
                                          'align': 'center', 'valign': 'vcenter', 'font_size': 11})
        str_fmt    = workbook.add_format({'border': 1, 'valign': 'vcenter'})
        qty_fmt    = workbook.add_format({'border': 1, 'align': 'center', 'num_format': '#,##0'})
        w21_fmt    = workbook.add_format({'border': 1, 'align': 'center', 'num_format': '#,##0.000'})
        tot_qty    = workbook.add_format({'bold': True, 'bg_color': '#fff3e0', 'border': 1,
                                          'align': 'center', 'num_format': '#,##0'})
        tot_w21    = workbook.add_format({'bold': True, 'bg_color': '#fff3e0', 'border': 1,
                                          'align': 'center', 'num_format': '#,##0.000'})
        grand_qty  = workbook.add_format({'bold': True, 'bg_color': '#8B6914', 'font_color': 'white',
                                          'border': 1, 'align': 'center', 'num_format': '#,##0'})
        grand_w21  = workbook.add_format({'bold': True, 'bg_color': '#8B6914', 'font_color': 'white',
                                          'border': 1, 'align': 'center', 'num_format': '#,##0.000'})

        for wh in data['warehouses']:
            for section in wh.get('sections', []):
                brands = section.get('brands', {})
                if not brands:
                    continue
                sheet_name = f"OnHand-{wh['warehouse_name'][:10]}-{section['location_name'][:12]}"[:31]
                ws = workbook.add_worksheet(sheet_name)
                ws.set_portrait()

                ws.merge_range('A1:F1', 'QTY ON HAND — Precious Metals', title_fmt)
                ws.merge_range('A2:F2',
                    f"As of: {data['as_of_date']}  |  Metal: {data['x_metal_type'].upper()}"
                    f"  |  Warehouse: {wh['warehouse_name']}  |  Location: {section['location_name']}",
                    sub_fmt)

                ws.set_column(0, 0, 28)  # Brand
                ws.set_column(1, 1, 22)  # Product
                ws.set_column(2, 2,  8)  # Type
                ws.set_column(3, 3,  8)  # Karat
                ws.set_column(4, 4, 12)  # Closing Qty
                ws.set_column(5, 5, 14)  # Closing W21

                # Header
                ws.write(2, 0, 'Brand',        hdr_fmt)
                ws.write(2, 1, 'Product',       hdr_fmt)
                ws.write(2, 2, 'Type',          hdr_fmt)
                ws.write(2, 3, 'Karat',         hdr_fmt)
                ws.write(2, 4, 'Closing QTY',   hdr_fmt)
                ws.write(2, 5, 'Closing W21',   hdr_fmt)

                row_idx = 3
                grand_qty_sum = 0.0
                grand_w21_sum = 0.0

                for brand_name, brand_data in brands.items():
                    rows = brand_data['rows']
                    # Brand header row (merged)
                    ws.merge_range(row_idx, 0, row_idx, 5, f' {brand_name}', brand_fmt)
                    row_idx += 1

                    for r in rows:
                        ws.write(row_idx, 0, '',              str_fmt)
                        ws.write(row_idx, 1, r['product'],    str_fmt)
                        ws.write(row_idx, 2, r['x_metal_type'], str_fmt)
                        ws.write(row_idx, 3, r['karat_display'], str_fmt)
                        ws.write_number(row_idx, 4, r['closing_qty_raw'], qty_fmt)
                        ws.write_number(row_idx, 5, r['closing_w21_raw'], w21_fmt)
                        row_idx += 1

                    # Brand subtotal
                    bqty = brand_data['total_qty_raw']
                    bw21 = brand_data['total_w21_raw']
                    ws.merge_range(row_idx, 0, row_idx, 3, f'Total — {brand_name}', tot_qty)
                    ws.write_number(row_idx, 4, bqty, tot_qty)
                    ws.write_number(row_idx, 5, bw21, tot_w21)
                    grand_qty_sum += bqty
                    grand_w21_sum += bw21
                    row_idx += 1

                # Grand total
                ws.merge_range(row_idx, 0, row_idx, 3, 'GRAND TOTAL', grand_qty)
                ws.write_number(row_idx, 4, grand_qty_sum, grand_qty)
                ws.write_number(row_idx, 5, grand_w21_sum, grand_w21)

        workbook.close(); output.seek(0)
        xlsx_data = base64.b64encode(output.read()).decode()
        attachment = self.env['ir.attachment'].create({
            'name': self._get_export_filename('QtyOnHand', 'xlsx'),
            'type': 'binary', 'datas': xlsx_data,
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        })
        return {'type': 'ir.actions.act_url',
                'url': f'/web/content/{attachment.id}?download=true', 'target': 'self'}

    # ── Core Data ──────────────────────────────────────────────────────────
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
        # Sort: Brand A→Z, then Karat DESC (high first), then Weight DESC
        product_tmpls = product_tmpls.sorted(key=lambda t: (
            (t.precious_metal_brand_id.name or 'zzzzz').lower(),
            -(float(t.x_karat) if t.x_metal_type == 'gold' and t.x_karat and t.x_karat not in ('Silver','0','') else (999.9 if t.x_metal_type == 'silver' else 0.0)),
            -(t.x_gold_weight or 0.0),
        ))
        warehouses = self.warehouse_ids or self.env['stock.warehouse'].search([])

        from datetime import datetime as _dt
        return {
            'as_of_date':  str(self.as_of_date),
            'x_metal_type':  self.x_metal_type,
            'hide_zero':   self.hide_zero,
            'printed_by':  self.env.user.name,
            'printed_at':  _dt.now().strftime('%Y-%m-%d %H:%M:%S'),
            'warehouses':  [self._compute_warehouse_data(wh, product_tmpls) for wh in warehouses],
        }

    def _compute_warehouse_data(self, warehouse, product_tmpls):
        if self.location_ids:
            # Use view_location_id (root of warehouse) to find ALL internal locations,
            # not just lot_stock_id which only covers the default stock location
            wh_root_id = warehouse.view_location_id.id if warehouse.view_location_id else warehouse.lot_stock_id.id
            all_wh_loc_ids = self.env['stock.location'].search([
                ('id', 'child_of', wh_root_id),
                ('usage', '=', 'internal'),
            ]).ids
            locations_to_report = self.location_ids.filtered(
                lambda l: l.id in all_wh_loc_ids
            )
            if not locations_to_report:
                return {'warehouse_name': warehouse.name, 'sections': []}
            sections = []
            for loc in locations_to_report:
                loc_ids = [loc.id]
                section = self._compute_section(loc, loc_ids, product_tmpls)
                if section['brands']:
                    sections.append(section)
        else:
            wh_root_id = warehouse.view_location_id.id if warehouse.view_location_id else warehouse.lot_stock_id.id
            top_locs = self.env['stock.location'].search([
                ('location_id', 'child_of', wh_root_id),
                ('usage', '=', 'internal'),
            ])
            sections = []
            for loc in top_locs:
                child_locs = self.env['stock.location'].search([
                    ('id', 'child_of', loc.id), ('usage', '=', 'internal'),
                ])
                loc_ids = child_locs.ids or [loc.id]
                section = self._compute_section(loc, loc_ids, product_tmpls)
                if section['brands']:
                    sections.append(section)
        return {'warehouse_name': warehouse.name, 'sections': sections}

    def _compute_section(self, location, loc_ids, product_tmpls):
        """
        Returns brands dict:
        {
          brand_name: {
            rows: [{product, x_metal_type, karat_display, closing_qty, closing_qty_raw,
                     closing_w21, closing_w21_raw}],
            total_qty_raw: float,
            total_w21_raw: float,
            total_qty:     float,   # display
            total_w21:     float,   # display
          }
        }
        """
        # As-of date means: all moves up to end of as_of_date
        as_of_str = str(self.as_of_date) + ' 23:59:59'
        Move = self.env['stock.move']

        brands = {}   # ordered by brand

        for tmpl in product_tmpls:
            prod_ids = tmpl.product_variant_ids.ids
            if not prod_ids:
                continue

            # Closing = all moves IN to location minus all moves OUT before end of as_of_date
            in_d  = Move.read_group([
                ('product_id', 'in', prod_ids),
                ('location_dest_id', 'in', loc_ids),
                ('state', '=', 'done'),
                ('date', '<=', as_of_str),
            ], ['product_uom_qty:sum'], [])
            out_d = Move.read_group([
                ('product_id', 'in', prod_ids),
                ('location_id', 'in', loc_ids),
                ('state', '=', 'done'),
                ('date', '<=', as_of_str),
            ], ['product_uom_qty:sum'], [])

            qty_in  = in_d[0]['product_uom_qty']  if in_d  and in_d[0]['product_uom_qty']  else 0.0
            qty_out = out_d[0]['product_uom_qty'] if out_d and out_d[0]['product_uom_qty'] else 0.0
            closing_qty = qty_in - qty_out

            if self.hide_zero and abs(closing_qty) < 0.0001:
                continue

            # W21 ratio
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
            # w21u = W21 لقطعة واحدة، نضرب في عدد القطع مباشرة
            closing_w21_raw = closing_qty * w21u if w21u else 0.0
            closing_qty_d   = int(closing_qty * 1000) / 1000.0
            closing_w21_d   = int(closing_w21_raw * 1000) / 1000.0

            brand_name = tmpl.precious_metal_brand_id.name or '— No Brand —'

            if brand_name not in brands:
                brands[brand_name] = {
                    'rows': [],
                    'total_qty_raw': 0.0,
                    'total_w21_raw': 0.0,
                    'total_qty': 0.0,
                    'total_w21': 0.0,
                }

            brands[brand_name]['rows'].append({
                'product':         tmpl.name,
                'x_metal_type':      mtype.upper(),
                'karat_display':   tmpl.karat_display or '',
                'closing_qty':     closing_qty_d,
                'closing_w21':     closing_w21_d,
                'closing_qty_raw': closing_qty,
                'closing_w21_raw': closing_w21_raw,
            })
            brands[brand_name]['total_qty_raw'] += closing_qty
            brands[brand_name]['total_w21_raw'] += closing_w21_raw

        # Build display totals
        for b in brands.values():
            b['total_qty'] = int(b['total_qty_raw'] * 1000) / 1000.0
            b['total_w21'] = int(b['total_w21_raw'] * 1000) / 1000.0

        # Grand totals for this section
        grand_qty_raw = sum(b['total_qty_raw'] for b in brands.values())
        grand_w21_raw = sum(b['total_w21_raw'] for b in brands.values())

        return {
            'location_name': location.complete_name,
            'brands': brands,
            'grand_qty_raw': grand_qty_raw,
            'grand_w21_raw': grand_w21_raw,
            'grand_qty': int(grand_qty_raw * 1000) / 1000.0,
            'grand_w21': int(grand_w21_raw * 1000) / 1000.0,
        }
