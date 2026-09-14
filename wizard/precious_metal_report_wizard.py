import io
import json
import xlsxwriter
import base64
from odoo import models, fields, api
from odoo.exceptions import ValidationError
from datetime import datetime, date


class PreciousMetalReportWizard(models.TransientModel):
    _name = 'precious.metal.report.wizard'
    _description = 'Precious Metal Inventory Report Wizard'

    # ── [1] DATETIME instead of DATE for precise period control ───────────
    datetime_from = fields.Datetime(
        string='From (Date & Time)', required=True,
        default=lambda self: datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0),
    )
    datetime_to = fields.Datetime(
        string='To (Date & Time)', required=True,
        default=lambda self: datetime.now().replace(hour=23, minute=59, second=59, microsecond=0),
    )
    x_metal_type = fields.Selection(
        selection=[('all','All Metals'),('gold','GOLD Only'),('silver','SILVER Only'),('other','OTHER Only')],
        string='Metal Type', default='all', required=True)
    warehouse_ids = fields.Many2many('stock.warehouse', string='Warehouses')
    location_ids  = fields.Many2many('stock.location', string='Locations',
        domain=[('usage','=','internal')])
    brand_ids    = fields.Many2many('precious.metal.brand', string='Brands')
    product_ids  = fields.Many2many('product.template', string='Products',
        domain=[('x_metal_type','!=',False)])
    only_with_moves = fields.Boolean(string='Show Only Products with Movements', default=True)
    report_data_json = fields.Text(string='Report Data JSON', default='{}')

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
                res.update(config.get_pm_defaults())
        except Exception:
            pass
        return res

    def action_open_settings(self):
        """Open the report config settings (from inside the wizard)."""
        config = self.env['precious.metal.report.config'].get_config()
        return {
            'type':      'ir.actions.act_window',
            'name':      'Report Settings',
            'res_model': 'precious.metal.report.config',
            'res_id':    config.id,
            'view_mode': 'form',
            'view_id':   self.env.ref(
                'precious_metals_suite.view_precious_metal_report_config_form').id,
            'target':    'new',
        }

    @api.constrains('datetime_from', 'datetime_to')
    def _check_dates(self):
        for rec in self:
            if rec.datetime_from > rec.datetime_to:
                raise ValidationError('Date From must be before Date To!')

    # ── Actions ────────────────────────────────────────────────────────────
    def action_show_report(self):
        """Open report as HTML in browser (Show Report button)."""
        data = self._get_report_data()
        self.sudo().write({'report_data_json': json.dumps(data, ensure_ascii=False)})
        return self.env.ref(
            'precious_metals_suite.action_report_precious_metal'
        ).report_action(self)

    def action_save_pdf(self):
        """Download report as PDF file."""
        import json as _json
        data = self._get_report_data()
        self.sudo().write({'report_data_json': _json.dumps(data, ensure_ascii=False)})
        pdf_name = self._get_export_filename('PreciousMetals', 'pdf')
        return self.env.ref('precious_metals_suite.action_report_precious_metal_pdf').report_action(self, data={'pdf_filename': pdf_name})

    def action_view_report(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Precious Metals Report',
            'res_model': 'precious.metal.report.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'view_id': self.env.ref(
                'precious_metals_suite.view_precious_metal_report_result_form').id,
            'target': 'current',
        }

    def action_export_excel(self):
        data = self._get_report_data()
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})

        title_fmt   = workbook.add_format({'bold': True, 'font_size': 13, 'font_color': '#8B6914'})
        sub_fmt     = workbook.add_format({'italic': True, 'font_color': '#888888'})
        header_fmt  = workbook.add_format({'bold': True, 'bg_color': '#8B6914', 'font_color': 'white',
                                           'border': 1, 'align': 'center', 'valign': 'vcenter', 'text_wrap': True})
        sub_hdr_fmt = workbook.add_format({'bold': True, 'bg_color': '#a07830', 'font_color': 'white',
                                           'border': 1, 'align': 'center'})
        str_fmt        = workbook.add_format({'border': 1, 'valign': 'vcenter'})
        data_fmt       = workbook.add_format({'border': 1, 'align': 'center', 'num_format': '#,##0'})
        total_fmt      = workbook.add_format({'bold': True, 'bg_color': '#f5e6c8', 'border': 1, 'align': 'center', 'num_format': '#,##0'})
        green_fmt      = workbook.add_format({'bg_color': '#e8f5e9', 'border': 1, 'align': 'center', 'num_format': '#,##0'})
        red_fmt        = workbook.add_format({'bg_color': '#fce4ec', 'border': 1, 'align': 'center', 'num_format': '#,##0'})
        orange_fmt     = workbook.add_format({'bold': True, 'bg_color': '#fff3e0', 'border': 1, 'align': 'center', 'num_format': '#,##0'})
        w21_fmt        = workbook.add_format({'border': 1, 'align': 'center', 'num_format': '#,##0.000'})
        w21_green_fmt  = workbook.add_format({'bg_color': '#e8f5e9', 'border': 1, 'align': 'center', 'num_format': '#,##0.000'})
        w21_red_fmt    = workbook.add_format({'bg_color': '#fce4ec', 'border': 1, 'align': 'center', 'num_format': '#,##0.000'})
        w21_orange_fmt = workbook.add_format({'bold': True, 'bg_color': '#fff3e0', 'border': 1, 'align': 'center', 'num_format': '#,##0.000'})
        w21_total_fmt  = workbook.add_format({'bold': True, 'bg_color': '#f5e6c8', 'border': 1, 'align': 'center', 'num_format': '#,##0.000'})
        footer_fmt     = workbook.add_format({'italic': True, 'font_color': '#aaaaaa', 'font_size': 8})

        for wh in data['warehouses']:
            for section in wh.get('sections', []):
                rows = section.get('rows', [])
                if not rows:
                    continue
                sheet_name = f"{wh['warehouse_name'][:15]}-{section['location_name'][:14]}"[:31]
                ws = workbook.add_worksheet(sheet_name)
                ws.set_landscape()
                ws.fit_to_pages(1, 0)

                ws.merge_range('A1:X1',
                    f"Precious Metals | {wh['warehouse_name']} | {section['location_name']}", title_fmt)
                ws.merge_range('A2:X2',
                    f"From: {data['datetime_from']}  →  To: {data['datetime_to']}  |  Metal: {data['x_metal_type'].upper()}"
                    + ("  |  Movements only" if data.get('only_with_moves') else ""), sub_fmt)

                cols = [
                    ('Product',1,18),('Brand',1,9),('Type',1,6),('Karat',1,6),
                    ('Opening Balance',2,None),('Purchases',2,None),('Manufacturing',2,None),
                    ('Transfers-in',2,None),('Adj IN (+)',2,None),('Total IN',2,None),
                    ('Sales',2,None),('Transfers-out',2,None),('Adj OUT (-)',2,None),
                    ('Total OUT',2,None),('Closing Balance',2,None),
                ]
                col = 0
                for label, span, width in cols:
                    if span == 1:
                        ws.merge_range(2, col, 3, col, label, header_fmt)
                        ws.set_column(col, col, width or 10); col += 1
                    else:
                        ws.merge_range(2, col, 2, col+1, label, header_fmt)
                        ws.write(3, col, 'Qty', sub_hdr_fmt)
                        ws.write(3, col+1, 'W21', sub_hdr_fmt)
                        ws.set_column(col, col, 6); ws.set_column(col+1, col+1, 9); col += 2

                row_idx = 4
                for r in rows:
                    c = 0
                    ws.write(row_idx, c, r['product'],      str_fmt);   c += 1
                    ws.write(row_idx, c, r['brand'],         str_fmt);   c += 1
                    ws.write(row_idx, c, r['x_metal_type'],    str_fmt);   c += 1
                    ws.write(row_idx, c, r['karat_display'], str_fmt);   c += 1
                    ws.write_number(row_idx, c, r['opening_qty_raw'],      data_fmt);      c += 1
                    ws.write_number(row_idx, c, r['opening_w21_raw'],      w21_fmt);       c += 1
                    ws.write_number(row_idx, c, r['purchase_qty_raw'],     data_fmt);      c += 1
                    ws.write_number(row_idx, c, r['purchase_w21_raw'],     w21_fmt);       c += 1
                    ws.write_number(row_idx, c, r['mfg_qty_raw'],          data_fmt);      c += 1
                    ws.write_number(row_idx, c, r['mfg_w21_raw'],          w21_fmt);       c += 1
                    ws.write_number(row_idx, c, r['transfer_in_qty_raw'],  data_fmt);      c += 1
                    ws.write_number(row_idx, c, r['transfer_in_w21_raw'],  w21_fmt);       c += 1
                    ws.write_number(row_idx, c, r['adj_in_qty_raw'],       green_fmt);     c += 1
                    ws.write_number(row_idx, c, r['adj_in_w21_raw'],       w21_green_fmt); c += 1
                    ws.write_number(row_idx, c, r['total_in_qty_raw'],     green_fmt);     c += 1
                    ws.write_number(row_idx, c, r['total_in_w21_raw'],     w21_green_fmt); c += 1
                    ws.write_number(row_idx, c, r['sale_qty_raw'],         data_fmt);      c += 1
                    ws.write_number(row_idx, c, r['sale_w21_raw'],         w21_fmt);       c += 1
                    ws.write_number(row_idx, c, r['transfer_out_qty_raw'], data_fmt);      c += 1
                    ws.write_number(row_idx, c, r['transfer_out_w21_raw'], w21_fmt);       c += 1
                    ws.write_number(row_idx, c, r['adj_out_qty_raw'],      red_fmt);       c += 1
                    ws.write_number(row_idx, c, r['adj_out_w21_raw'],      w21_red_fmt);   c += 1
                    ws.write_number(row_idx, c, r['total_out_qty_raw'],    red_fmt);       c += 1
                    ws.write_number(row_idx, c, r['total_out_w21_raw'],    w21_red_fmt);   c += 1
                    ws.write_number(row_idx, c, r['closing_qty_raw'],      orange_fmt);    c += 1
                    ws.write_number(row_idx, c, r['closing_w21_raw'],      w21_orange_fmt)
                    row_idx += 1

                t = section['total']
                ws.merge_range(row_idx, 0, row_idx, 3, 'TOTAL', total_fmt)
                excel_keys = [
                    ('opening_qty_raw',total_fmt),      ('opening_w21_raw',w21_total_fmt),
                    ('purchase_qty_raw',total_fmt),     ('purchase_w21_raw',w21_total_fmt),
                    ('mfg_qty_raw',total_fmt),          ('mfg_w21_raw',w21_total_fmt),
                    ('transfer_in_qty_raw',total_fmt),  ('transfer_in_w21_raw',w21_total_fmt),
                    ('adj_in_qty_raw',total_fmt),       ('adj_in_w21_raw',w21_total_fmt),
                    ('total_in_qty_raw',total_fmt),     ('total_in_w21_raw',w21_total_fmt),
                    ('sale_qty_raw',total_fmt),         ('sale_w21_raw',w21_total_fmt),
                    ('transfer_out_qty_raw',total_fmt), ('transfer_out_w21_raw',w21_total_fmt),
                    ('adj_out_qty_raw',total_fmt),      ('adj_out_w21_raw',w21_total_fmt),
                    ('total_out_qty_raw',total_fmt),    ('total_out_w21_raw',w21_total_fmt),
                    ('closing_qty_raw',total_fmt),      ('closing_w21_raw',w21_total_fmt),
                ]
                for i, (key, fmt) in enumerate(excel_keys):
                    ws.write_number(row_idx, 4 + i, t.get(key, 0.0), fmt)
                row_idx += 2
                # [5] Footer: printed by / time
                ws.merge_range(row_idx, 0, row_idx, 23,
                    f"Printed by: {self.env.user.name}  |  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                    footer_fmt)

        workbook.close(); output.seek(0)
        xlsx_data = base64.b64encode(output.read()).decode()
        attachment = self.env['ir.attachment'].create({
            'name': self._get_export_filename('PreciousMetals', 'xlsx'),
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
        product_tmpls = product_tmpls.sorted(key=lambda t: (
            (t.precious_metal_brand_id.name or 'zzzzz').lower(),
            -(float(t.x_karat) if t.x_metal_type == 'gold' and t.x_karat and t.x_karat not in ('Silver','0','') else (999.9 if t.x_metal_type == 'silver' else 0.0)),
            -(t.x_gold_weight or 0.0),
        ))
        warehouses = self.warehouse_ids or self.env['stock.warehouse'].search([])

        # [5] capture print info
        printed_by = self.env.user.name
        printed_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # Build warehouse sections
        wh_sections = [self._compute_warehouse_data(wh, product_tmpls) for wh in warehouses]

        # If user selected specific locations, also include any that are
        # outside all warehouse hierarchies as a standalone "Other Locations" group
        if self.location_ids:
            all_wh_loc_ids = set()
            for wh in warehouses:
                wh_root_id = wh.view_location_id.id if wh.view_location_id else wh.lot_stock_id.id
                wh_locs = self.env['stock.location'].search([
                    ('id', 'child_of', wh_root_id),
                    ('usage', '=', 'internal'),
                ]).ids
                all_wh_loc_ids.update(wh_locs)

            orphan_locs = self.location_ids.filtered(
                lambda l: l.id not in all_wh_loc_ids
            )
            if orphan_locs:
                orphan_sections = []
                for loc in orphan_locs:
                    section = self._compute_section(loc, [loc.id], product_tmpls)
                    if section['rows']:
                        orphan_sections.append(section)
                if orphan_sections:
                    wh_sections.append({
                        'warehouse_name': 'Other Locations',
                        'sections': orphan_sections,
                    })

        return {
            'datetime_from':   str(self.datetime_from),
            'datetime_to':     str(self.datetime_to),
            'x_metal_type':      self.x_metal_type,
            'only_with_moves': self.only_with_moves,
            'printed_by':      printed_by,
            'printed_at':      printed_at,
            'warehouses': wh_sections,
        }

    def _compute_warehouse_data(self, warehouse, product_tmpls):
        if self.location_ids:
            # User selected specific locations — show only those inside this warehouse
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
            # Each selected location = one section
            sections = []
            for loc in locations_to_report:
                section = self._compute_section(loc, [loc.id], product_tmpls)
                if section['rows']:
                    sections.append(section)
        else:
            # No filter — show top-level internal locations under warehouse
            wh_root_id = warehouse.view_location_id.id if warehouse.view_location_id else warehouse.lot_stock_id.id
            top_locs = self.env['stock.location'].search([
                ('location_id', 'child_of', wh_root_id),
                ('usage', '=', 'internal'),
            ])
            sections = []
            for loc in top_locs:
                # Include this location and all its children
                child_locs = self.env['stock.location'].search([
                    ('id', 'child_of', loc.id), ('usage', '=', 'internal'),
                ])
                loc_ids = child_locs.ids or [loc.id]
                section = self._compute_section(loc, loc_ids, product_tmpls)
                if section['rows']:
                    sections.append(section)
        return {'warehouse_name': warehouse.name, 'sections': sections}

    def _compute_section(self, location, loc_ids, product_tmpls):
        rows = []
        acc = {k: 0.0 for k in [
            'opening_qty','opening_w21','purchase_qty','purchase_w21',
            'mfg_qty','mfg_w21','transfer_in_qty','transfer_in_w21',
            'adj_in_qty','adj_in_w21',
            'total_in_qty','total_in_w21','sale_qty','sale_w21',
            'transfer_out_qty','transfer_out_w21','adj_out_qty','adj_out_w21',
            'pts_total_qty','pts_total_w21',
            'mfg_vendor_total_qty','mfg_vendor_total_w21',
            'total_out_qty','total_out_w21','closing_qty','closing_w21',
            'opening_qty_raw','opening_w21_raw','purchase_qty_raw','purchase_w21_raw',
            'mfg_qty_raw','mfg_w21_raw','transfer_in_qty_raw','transfer_in_w21_raw',
            'adj_in_qty_raw','adj_in_w21_raw',
            'total_in_qty_raw','total_in_w21_raw','sale_qty_raw','sale_w21_raw',
            'transfer_out_qty_raw','transfer_out_w21_raw','adj_out_qty_raw','adj_out_w21_raw',
            'pts_total_qty_raw','pts_total_w21_raw',
            'mfg_vendor_total_qty_raw','mfg_vendor_total_w21_raw',
            'total_out_qty_raw','total_out_w21_raw','closing_qty_raw','closing_w21_raw',
        ]}

        # Pre-fetch mfg qty & W21 maps for ALL products at once (avoids N+1 DB calls)
        all_prod_ids = [p for tmpl in product_tmpls for p in tmpl.product_variant_ids.ids]
        mfg_qty_map  = self._get_mfg_qty_by_location(all_prod_ids, self.datetime_from, self.datetime_to, loc_ids)
        mfg_w21_map  = self._get_metal_mfg_w21(all_prod_ids, self.datetime_from, self.datetime_to, loc_ids)

        # Cache mfg picking exclusions + move IDs ONCE for the whole section
        _mfg_excl_list = self._get_mfg_picking_exclusions()
        _mfg_move_ids  = self._get_mfg_move_ids()

        # Pre-fetch vendor breakdown for Manufacturing column
        mfg_vendor_map = self._get_mfg_qty_by_vendor(all_prod_ids, self.datetime_from, self.datetime_to, loc_ids)
        mfg_vendor_w21_map = self._get_mfg_w21_by_vendor(all_prod_ids, self.datetime_from, self.datetime_to, loc_ids)
        pts_vendor_map = self._get_pts_qty_by_vendor(all_prod_ids, self.datetime_from, self.datetime_to, loc_ids)

        for tmpl in product_tmpls:
            prod_ids = tmpl.product_variant_ids.ids
            if not prod_ids:
                continue

            opening_qty    = self._get_stock_before(prod_ids, loc_ids, self.datetime_from)
            purchase_qty   = self._get_move_qty(prod_ids, loc_ids, 'in',  'supplier')
            # Use pre-fetched mfg qty map (location-aware, avoids extra DB calls)
            mfg_qty        = sum(mfg_qty_map.get(pid, 0.0) for pid in prod_ids)
            transfer_in_qty= self._get_transfer_in_qty(prod_ids, loc_ids, _mfg_excl_list, _mfg_move_ids)
            adj_in_qty     = self._get_move_qty(prod_ids, loc_ids, 'in',  'inventory')
            adj_out_qty    = self._get_move_qty(prod_ids, loc_ids, 'out', 'inventory')
            sale_qty       = self._get_sale_order_qty(prod_ids, loc_ids)
            transfer_out_qty = self._get_transfer_out_qty(prod_ids, loc_ids, _mfg_excl_list, _mfg_move_ids)

            # W21 from metal.manufacturing (precise, from stored total_w21 per output line)
            mfg_w21_precise = sum(mfg_w21_map.get(pid, 0.0) for pid in prod_ids)

            # Compute PTS qty early so total_out and closing include it
            _pts_vendor_raw = {}
            for _vid, _vname in pts_vendor_map.get('_vendors', {}).items():
                _vqty = sum(pts_vendor_map.get(_vid, {}).get(pid, 0.0) for pid in prod_ids)
                if _vqty:
                    _pts_vendor_raw[_vname] = _vqty
            pts_total_qty_early = sum(_pts_vendor_raw.values())

            total_in  = purchase_qty + mfg_qty + transfer_in_qty + adj_in_qty
            total_out = sale_qty + transfer_out_qty + adj_out_qty + pts_total_qty_early
            closing   = opening_qty + total_in - total_out

            if self.only_with_moves:
                has_moves = (purchase_qty + mfg_qty + transfer_in_qty + adj_in_qty +
                             adj_out_qty + sale_qty + transfer_out_qty + pts_total_qty_early) > 0
                has_closing = abs(closing) > 0.0001
                if not has_moves and not has_closing:
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
            # w21u = وزن W21 لقطعة واحدة، نضرب في عدد القطع (qty)
            def wr(qty): return qty * w21u if w21u else 0.0
            def qd(q):   return round(q, 3)
            def wd(qty): return round(wr(qty), 4)

            # Use precise mfg_w21 from metal.manufacturing if available
            mfg_w21_display = round(mfg_w21_precise, 4) if mfg_w21_precise else wd(mfg_qty)
            mfg_w21_raw     = mfg_w21_precise if mfg_w21_precise else wr(mfg_qty)

            # Per-vendor manufacturing breakdown
            vendor_mfg = {}
            vendor_mfg_w21 = {}
            for vid, vname in mfg_vendor_map.get('_vendors', {}).items():
                vqty = sum(mfg_vendor_map.get(vid, {}).get(pid, 0.0) for pid in prod_ids)
                vw21 = sum(mfg_vendor_w21_map.get(vid, {}).get(pid, 0.0) for pid in prod_ids)
                if vqty or vw21:
                    vendor_mfg[vname] = round(vqty, 3)
                    vendor_mfg_w21[vname] = round(vw21, 4)

            # Per-vendor manufacturing totals
            mfg_vendor_total_qty = sum(vendor_mfg.values())
            mfg_vendor_total_w21 = sum(vendor_mfg_w21.values())

            # Per-vendor product-to-scrap breakdown (OUT side) — reuse early-computed values
            vendor_pts = {}
            vendor_pts_w21 = {}
            for _vname, _vqty in _pts_vendor_raw.items():
                vendor_pts[_vname] = round(_vqty, 3)
                vendor_pts_w21[_vname] = round(_vqty * w21u, 4) if w21u else 0.0
            pts_total_qty = pts_total_qty_early
            pts_total_w21 = wr(pts_total_qty)

            # Total OUT = sales + transfers + adj + PTS
            total_out_w21_precise = wr(sale_qty) + wr(transfer_out_qty) + wr(adj_out_qty) + pts_total_w21
            closing_w21_precise   = (wr(opening_qty) + wr(purchase_qty) + mfg_w21_raw
                                     + wr(transfer_in_qty) + wr(adj_in_qty)
                                     - wr(sale_qty) - wr(transfer_out_qty) - wr(adj_out_qty) - pts_total_w21)

            row = {
                'product': tmpl.name, 'brand': tmpl.precious_metal_brand_id.name or '',
                'x_metal_type': (tmpl.x_metal_type or '').upper(), 'karat_display': tmpl.karat_display or '',
                'vendor_mfg':             vendor_mfg,             'vendor_mfg_w21':             vendor_mfg_w21,
                'vendor_pts':             vendor_pts,             'vendor_pts_w21':             vendor_pts_w21,
                'mfg_vendor_total_qty':   round(mfg_vendor_total_qty, 3),
                'mfg_vendor_total_w21':   round(mfg_vendor_total_w21, 4),
                'pts_total_qty':          round(pts_total_qty, 3),
                'pts_total_w21':          round(pts_total_w21, 4),
                'opening_qty':      qd(opening_qty),      'opening_w21':      wd(opening_qty),
                'purchase_qty':     qd(purchase_qty),     'purchase_w21':     wd(purchase_qty),
                'mfg_qty':          qd(mfg_qty),          'mfg_w21':          mfg_w21_display,
                'transfer_in_qty':  qd(transfer_in_qty),  'transfer_in_w21':  wd(transfer_in_qty),
                'adj_in_qty':       qd(adj_in_qty),       'adj_in_w21':       wd(adj_in_qty),
                'total_in_qty':     qd(total_in),         'total_in_w21':     round(wr(purchase_qty) + mfg_w21_raw + wr(transfer_in_qty) + wr(adj_in_qty), 4),
                'sale_qty':         qd(sale_qty),         'sale_w21':         wd(sale_qty),
                'transfer_out_qty': qd(transfer_out_qty), 'transfer_out_w21': wd(transfer_out_qty),
                'adj_out_qty':      qd(adj_out_qty),      'adj_out_w21':      wd(adj_out_qty),
                'total_out_qty':    qd(total_out),        'total_out_w21':    round(total_out_w21_precise, 4),  # total_out already includes pts_total_qty_early
                'closing_qty':      qd(closing),          'closing_w21':      round(closing_w21_precise, 4),
                'opening_qty_raw':          opening_qty,          'opening_w21_raw':          wr(opening_qty),
                'purchase_qty_raw':         purchase_qty,         'purchase_w21_raw':         wr(purchase_qty),
                'mfg_qty_raw':              mfg_qty,              'mfg_w21_raw':              mfg_w21_raw,
                'transfer_in_qty_raw':      transfer_in_qty,      'transfer_in_w21_raw':      wr(transfer_in_qty),
                'adj_in_qty_raw':           adj_in_qty,           'adj_in_w21_raw':           wr(adj_in_qty),
                'total_in_qty_raw':         total_in,             'total_in_w21_raw':         wr(purchase_qty) + mfg_w21_raw + wr(transfer_in_qty) + wr(adj_in_qty),
                'sale_qty_raw':             sale_qty,             'sale_w21_raw':             wr(sale_qty),
                'transfer_out_qty_raw':     transfer_out_qty,     'transfer_out_w21_raw':     wr(transfer_out_qty),
                'adj_out_qty_raw':          adj_out_qty,          'adj_out_w21_raw':          wr(adj_out_qty),
                'pts_total_qty_raw':        pts_total_qty,        'pts_total_w21_raw':        pts_total_w21,
                'mfg_vendor_total_qty_raw': mfg_vendor_total_qty, 'mfg_vendor_total_w21_raw': mfg_vendor_total_w21,
                'total_out_qty_raw':        total_out,            'total_out_w21_raw':        total_out_w21_precise,
                'closing_qty_raw':          closing,              'closing_w21_raw':          closing_w21_precise,
            }
            rows.append(row)
            for k in acc:
                acc[k] += row.get(k, 0.0)

        total = {}
        for k, v in acc.items():
            total[k] = v if k.endswith('_raw') else round(v, 4)

        return {'location_name': location.complete_name, 'rows': rows, 'total': total}

    # ── Stock helpers (now use DATETIME) ───────────────────────────────────

    def _get_sale_order_qty(self, product_ids, loc_ids):
        """
        Sales column = outgoing moves that are linked to a Sale Order line.
        These are deliveries tied to confirmed sale orders (have sale_line_id set).
        This correctly captures: Custody→Customer AND direct Stock→Customer deliveries
        that originated from a sale order.
        """
        dt_from = str(self.datetime_from)
        dt_to   = str(self.datetime_to)
        domain = [
            ('product_id',    'in', product_ids),
            ('location_id',   'in', loc_ids),
            ('state',         '=',  'done'),
            ('date',          '>=', dt_from),
            ('date',          '<=', dt_to),
            ('sale_line_id',  '!=', False),   # ← linked to a Sale Order line
        ]
        result = self.env['stock.move'].read_group(domain, ['product_uom_qty:sum'], [])
        return result[0]['product_uom_qty'] if result and result[0]['product_uom_qty'] else 0.0

    def _get_mfg_picking_exclusions(self, cached=None):
        """
        Return picking IDs for ALL metal_manufacturing / PTS / scrap-purchase workflows.
        These must NEVER appear in Transfer-IN or Transfer-OUT.

        Uses exact field names confirmed from metal_manufacturing module source:
          metal.manufacturing  : scrap_picking_id, output_picking_id, distribution_picking_ids
          metal.product.to.scrap : out_picking_id, in_picking_id
          metal.scrap.purchase   : picking_id
          metal.vendor.scrap.transfer : picking_id
        Fallback layers: sequence_code, name prefix, origin prefix.
        """
        if cached is not None:
            return list(cached) if cached else [-1]

        excluded_ids = set()

        # ── 1. metal.manufacturing: scrap + output + ALL distribution pickings ─
        MetalMfg = self.env.get('metal.manufacturing')
        if MetalMfg is not None:
            sessions = MetalMfg.search([('state', 'in', ['confirmed', 'done'])])
            for s in sessions:
                if s.scrap_picking_id:
                    excluded_ids.add(s.scrap_picking_id.id)
                if s.output_picking_id:
                    excluded_ids.add(s.output_picking_id.id)
                excluded_ids.update(s.distribution_picking_ids.ids)

        # ── 2. metal.product.to.scrap: out_picking_id + in_picking_id ────────
        MetalPts = self.env.get('metal.product.to.scrap')
        if MetalPts is not None:
            pts_ops = MetalPts.search([('state', '=', 'done')])
            for op in pts_ops:
                if op.out_picking_id:
                    excluded_ids.add(op.out_picking_id.id)
                if op.in_picking_id:
                    excluded_ids.add(op.in_picking_id.id)

        # ── 3. metal.scrap.purchase: picking_id ──────────────────────────────
        MetalSpo = self.env.get('metal.scrap.purchase')
        if MetalSpo is not None:
            spo_ops = MetalSpo.search([('state', '=', 'done')])
            for op in spo_ops:
                if op.picking_id:
                    excluded_ids.add(op.picking_id.id)

        # ── 4. metal.vendor.scrap.transfer: picking_id ───────────────────────
        MetalVst = self.env.get('metal.vendor.scrap.transfer')
        if MetalVst is not None:
            vst_ops = MetalVst.search([('state', '=', 'done')])
            for op in vst_ops:
                if op.picking_id:
                    excluded_ids.add(op.picking_id.id)

        # ── 5. Fallback: sequence_code ────────────────────────────────────────
        mfg_pick_types = self.env['stock.picking.type'].search([
            ('sequence_code', 'in', ['MM-SC', 'MM-OUT', 'PTS-OUT', 'PTS-IN', 'SPO-IN']),
        ])
        if mfg_pick_types:
            picks = self.env['stock.picking'].search([
                ('picking_type_id', 'in', mfg_pick_types.ids),
                ('state', '=', 'done'),
            ])
            excluded_ids.update(picks.ids)

        # ── 6. Fallback: name prefix ──────────────────────────────────────────
        for prefix in ['MM-OUT/', 'MM-SC/', 'PTS-OUT/', 'PTS-IN/', 'SPO-IN/']:
            picks = self.env['stock.picking'].search([
                ('name', 'like', prefix), ('state', '=', 'done'),
            ])
            excluded_ids.update(picks.ids)

        # ── 7. Fallback: origin starts with WH/MO/ (catches distribution pickings) ─
        picks = self.env['stock.picking'].search([
            ('origin', 'like', 'WH/MO/'), ('state', '=', 'done'),
        ])
        excluded_ids.update(picks.ids)

        return list(excluded_ids) if excluded_ids else [-1]

    def _get_mfg_move_ids(self):
        """
        Return ALL stock.move IDs for metal_manufacturing / PTS / scrap-purchase workflows.
        This is the move-level exclusion guard — completely independent of picking names.
        Uses exact field names from metal_manufacturing module source code.
        """
        move_ids = set()

        # metal.manufacturing: scrap_picking_id + output_picking_id + distribution_picking_ids
        MetalMfg = self.env.get('metal.manufacturing')
        if MetalMfg is not None:
            sessions = MetalMfg.search([('state', 'in', ['confirmed', 'done'])])
            for s in sessions:
                if s.scrap_picking_id:
                    move_ids.update(s.scrap_picking_id.move_ids.ids)
                if s.output_picking_id:
                    move_ids.update(s.output_picking_id.move_ids.ids)
                for dp in s.distribution_picking_ids:
                    move_ids.update(dp.move_ids.ids)

        # metal.product.to.scrap: out_picking_id + in_picking_id
        MetalPts = self.env.get('metal.product.to.scrap')
        if MetalPts is not None:
            pts_ops = MetalPts.search([('state', '=', 'done')])
            for op in pts_ops:
                if op.out_picking_id:
                    move_ids.update(op.out_picking_id.move_ids.ids)
                if op.in_picking_id:
                    move_ids.update(op.in_picking_id.move_ids.ids)

        # metal.scrap.purchase: picking_id
        MetalSpo = self.env.get('metal.scrap.purchase')
        if MetalSpo is not None:
            spo_ops = MetalSpo.search([('state', '=', 'done')])
            for op in spo_ops:
                if op.picking_id:
                    move_ids.update(op.picking_id.move_ids.ids)

        # metal.vendor.scrap.transfer: picking_id
        MetalVst = self.env.get('metal.vendor.scrap.transfer')
        if MetalVst is not None:
            vst_ops = MetalVst.search([('state', '=', 'done')])
            for op in vst_ops:
                if op.picking_id:
                    move_ids.update(op.picking_id.move_ids.ids)

        return list(move_ids) if move_ids else [-1]

    def _get_transfer_in_qty(self, product_ids, loc_ids, mfg_excl_list=None, mfg_move_ids=None):
        """
        Transfers-IN = incoming moves from OTHER internal locations.
        Excludes metal_manufacturing moves via TWO independent guards:
          1. picking_id not in mfg picking exclusion list
          2. id not in mfg move exclusion list (catches distribution pickings
             with generic names like WH/INT/ that evade the picking guard)
        """
        dt_from = str(self.datetime_from)
        dt_to   = str(self.datetime_to)

        mfg_picks = mfg_excl_list if mfg_excl_list is not None else self._get_mfg_picking_exclusions()
        if not mfg_picks:
            mfg_picks = [-1]

        mfg_moves = mfg_move_ids if mfg_move_ids is not None else self._get_mfg_move_ids()
        if not mfg_moves:
            mfg_moves = [-1]

        domain = [
            ('product_id',            'in',     product_ids),
            ('location_dest_id',      'in',     loc_ids),
            ('state',                 '=',      'done'),
            ('date',                  '>=',     dt_from),
            ('date',                  '<=',     dt_to),
            ('location_id',           'not in', loc_ids),
            ('picking_id',            'not in', mfg_picks),   # guard 1: by picking
            ('id',                    'not in', mfg_moves),   # guard 2: by move ID
            ('location_id.usage',     '!=',     'inventory'),
            ('location_id.usage',     'not in', ['production', 'supplier']),
        ]
        result = self.env['stock.move'].read_group(domain, ['product_uom_qty:sum'], [])
        return result[0]['product_uom_qty'] if result and result[0]['product_uom_qty'] else 0.0

    def _get_transfer_out_qty(self, product_ids, loc_ids, mfg_excl_list=None, mfg_move_ids=None):
        """
        Transfers-OUT = outgoing moves NOT linked to a Sale Order and going outside this location.
        Excludes metal_manufacturing moves via TWO independent guards:
          1. picking_id not in mfg picking exclusion list
          2. id not in mfg move exclusion list
        """
        dt_from = str(self.datetime_from)
        dt_to   = str(self.datetime_to)

        mfg_picks = mfg_excl_list if mfg_excl_list is not None else self._get_mfg_picking_exclusions()
        if not mfg_picks:
            mfg_picks = [-1]

        mfg_moves = mfg_move_ids if mfg_move_ids is not None else self._get_mfg_move_ids()
        if not mfg_moves:
            mfg_moves = [-1]

        domain = [
            ('product_id',             'in',     product_ids),
            ('location_id',            'in',     loc_ids),
            ('state',                  '=',      'done'),
            ('date',                   '>=',     dt_from),
            ('date',                   '<=',     dt_to),
            ('sale_line_id',           '=',      False),
            ('location_dest_id',       'not in', loc_ids),
            ('picking_id',             'not in', mfg_picks),   # guard 1: by picking
            ('id',                     'not in', mfg_moves),   # guard 2: by move ID
            ('location_dest_id.usage', 'not in', ['inventory', 'production']),
        ]
        result = self.env['stock.move'].read_group(domain, ['product_uom_qty:sum'], [])
        return result[0]['product_uom_qty'] if result and result[0]['product_uom_qty'] else 0.0

    def _get_stock_before(self, product_ids, loc_ids, datetime_from):
        """Opening balance = all done moves strictly BEFORE datetime_from."""
        dt_str = str(datetime_from)
        Move = self.env['stock.move']
        in_d  = Move.read_group([
            ('product_id','in',product_ids), ('location_dest_id','in',loc_ids),
            ('state','=','done'), ('date','<',dt_str)], ['product_uom_qty:sum'], [])
        out_d = Move.read_group([
            ('product_id','in',product_ids), ('location_id','in',loc_ids),
            ('state','=','done'), ('date','<',dt_str)], ['product_uom_qty:sum'], [])
        qty_in  = in_d[0]['product_uom_qty']  if in_d  and in_d[0]['product_uom_qty']  else 0.0
        qty_out = out_d[0]['product_uom_qty'] if out_d and out_d[0]['product_uom_qty'] else 0.0
        return qty_in - qty_out

    def _get_mfg_qty_by_location(self, product_ids, datetime_from, datetime_to, loc_ids):
        """
        Build a map of {product_id: qty} for manufacturing moves that arrived
        at the specified loc_ids during the report period.

        Strategy:
        1. If metal.manufacturing is installed: look at stock moves that are
           linked to manufacturing pickings (MM-OUT/, PTS-IN/, SPO-IN/ etc.)
           and whose destination is in loc_ids.
        2. Fallback: standard stock.move with location_id.usage = 'production'.
        """
        dt_from = str(datetime_from)
        dt_to   = str(datetime_to)

        # Identify manufacturing-related picking name prefixes
        mfg_prefixes = ['MM-OUT/', 'MM-SC/', 'PTS-OUT/', 'PTS-IN/', 'SPO-IN/']
        origin_prefixes = ['MFG/', 'WH/MO/']

        picking_ids = set()
        for prefix in mfg_prefixes:
            picks = self.env['stock.picking'].search([
                ('name', 'like', prefix), ('state', '=', 'done'),
            ])
            picking_ids.update(picks.ids)
        for prefix in origin_prefixes:
            picks = self.env['stock.picking'].search([
                ('origin', 'like', prefix), ('state', '=', 'done'),
            ])
            picking_ids.update(picks.ids)

        if not picking_ids:
            # Fallback: treat production-origin moves as mfg
            domain = [
                ('product_id', 'in', product_ids),
                ('location_dest_id', 'in', loc_ids),
                ('location_id.usage', '=', 'production'),
                ('state', '=', 'done'),
                ('date', '>=', dt_from),
                ('date', '<=', dt_to),
            ]
            result_rows = self.env['stock.move'].read_group(
                domain, ['product_id', 'product_uom_qty:sum'], ['product_id'])
            return {r['product_id'][0]: r['product_uom_qty'] for r in result_rows if r['product_uom_qty']}

        # Use identified manufacturing picking moves arriving at loc_ids
        domain = [
            ('product_id', 'in', product_ids),
            ('location_dest_id', 'in', loc_ids),
            ('picking_id', 'in', list(picking_ids)),
            ('state', '=', 'done'),
            ('date', '>=', dt_from),
            ('date', '<=', dt_to),
        ]
        result_rows = self.env['stock.move'].read_group(
            domain, ['product_id', 'product_uom_qty:sum'], ['product_id'])
        return {r['product_id'][0]: r['product_uom_qty'] for r in result_rows if r['product_uom_qty']}

    def _get_metal_mfg_qty(self, product_ids, datetime_from, datetime_to, loc_ids=None):
        """
        Manufacturing qty filtered by destination location.
        Uses stock moves from manufacturing pickings that arrived at loc_ids.
        Falls back to production-usage moves if metal_manufacturing not installed.
        """
        if not loc_ids:
            return 0.0
        qty_map = self._get_mfg_qty_by_location(product_ids, datetime_from, datetime_to, loc_ids)
        return sum(qty_map.get(pid, 0.0) for pid in product_ids)

    def _get_metal_mfg_w21(self, product_ids, datetime_from, datetime_to, loc_ids=None):
        """
        Manufacturing W21 filtered by destination location.
        First tries metal.manufacturing output lines matched against stock moves
        arriving at loc_ids. Falls back to qty * w21_per_unit if needed.
        Returns dict: {product_id: total_w21}.
        """
        if not loc_ids:
            return {}

        # Get per-product qty that actually arrived at this location
        qty_map = self._get_mfg_qty_by_location(product_ids, datetime_from, datetime_to, loc_ids)
        if not qty_map:
            return {}

        MetalMfg = self.env.get('metal.manufacturing')
        if MetalMfg is None:
            return {}

        dt_from = str(datetime_from)
        dt_to   = str(datetime_to)

        # Build total output qty & w21 per product from metal.manufacturing sessions
        session_qty_map = {}   # {product_id: total_qty_across_all_sessions}
        session_w21_map = {}   # {product_id: total_w21_across_all_sessions}

        sessions = MetalMfg.search([
            ('state', 'in', ['confirmed', 'done']),
            ('date',  '>=', dt_from),
            ('date',  '<=', dt_to),
        ])
        for session in sessions:
            for line in session.output_line_ids:
                if line.product_id and line.product_id.id in product_ids:
                    pid = line.product_id.id
                    session_qty_map[pid] = session_qty_map.get(pid, 0.0) + (line.qty or 0.0)
                    session_w21_map[pid] = session_w21_map.get(pid, 0.0) + (line.total_w21 or 0.0)

        # Prorate W21 by the fraction of qty that reached this location
        result = {}
        for pid, loc_qty in qty_map.items():
            if pid not in product_ids:
                continue
            total_session_qty = session_qty_map.get(pid, 0.0)
            total_session_w21 = session_w21_map.get(pid, 0.0)
            if total_session_qty and total_session_w21:
                # W21 proportional to qty fraction
                result[pid] = (loc_qty / total_session_qty) * total_session_w21
            else:
                # No session data — W21 will fall back to unit calculation in _compute_section
                result[pid] = 0.0
        return result


    def _get_mfg_qty_by_vendor(self, product_ids, datetime_from, datetime_to, loc_ids):
        """
        Returns {vendor_id: {product_id: qty}, '_vendors': {vendor_id: vendor_name}}
        for manufacturing output moves arriving at loc_ids in the period.
        Used to split the Manufacturing column per Vendor/Merchant.
        """
        if not loc_ids:
            return {}
        dt_from = str(datetime_from)
        dt_to   = str(datetime_to)

        MetalMfg = self.env.get('metal.manufacturing')
        if MetalMfg is None:
            return {}

        result = {'_vendors': {}}
        sessions = MetalMfg.search([
            ('state', 'in', ['confirmed', 'done']),
            ('date', '>=', dt_from),
            ('date', '<=', dt_to),
        ])

        # Get picking IDs for these sessions
        for session in sessions:
            vendor = session.vendor_id
            vid = vendor.id if vendor else 0
            vname = vendor.name if vendor else '(No Vendor)'
            result['_vendors'][vid] = vname

            if vid not in result:
                result[vid] = {}

            # Use output picking moves arriving at loc_ids
            if session.output_picking_id and session.output_picking_id.state == 'done':
                for move in session.output_picking_id.move_ids:
                    if (move.product_id.id in product_ids
                            and move.location_dest_id.id in loc_ids
                            and move.state == 'done'):
                        pid = move.product_id.id
                        result[vid][pid] = result[vid].get(pid, 0.0) + move.product_uom_qty

            # Also check distribution pickings
            for dp in session.distribution_picking_ids:
                if dp.state == 'done':
                    for move in dp.move_ids:
                        if (move.product_id.id in product_ids
                                and move.location_dest_id.id in loc_ids
                                and move.state == 'done'):
                            pid = move.product_id.id
                            result[vid][pid] = result[vid].get(pid, 0.0) + move.product_uom_qty

        return result

    def _get_mfg_w21_by_vendor(self, product_ids, datetime_from, datetime_to, loc_ids):
        """
        Returns {vendor_id: {product_id: w21}, '_vendors': {vendor_id: vendor_name}}
        Manufacturing W21 per vendor, prorated by location qty fraction.
        """
        if not loc_ids:
            return {}
        dt_from = str(datetime_from)
        dt_to   = str(datetime_to)

        MetalMfg = self.env.get('metal.manufacturing')
        if MetalMfg is None:
            return {}

        result = {'_vendors': {}}
        sessions = MetalMfg.search([
            ('state', 'in', ['confirmed', 'done']),
            ('date', '>=', dt_from),
            ('date', '<=', dt_to),
        ])

        for session in sessions:
            vendor = session.vendor_id
            vid = vendor.id if vendor else 0
            vname = vendor.name if vendor else '(No Vendor)'
            result['_vendors'][vid] = vname

            if vid not in result:
                result[vid] = {}

            # Get W21 from output lines
            for line in session.output_line_ids:
                if line.product_id and line.product_id.id in product_ids:
                    pid = line.product_id.id
                    # Check if this product arrived at loc_ids via output/distribution pickings
                    loc_qty = 0.0
                    if session.output_picking_id and session.output_picking_id.state == 'done':
                        for move in session.output_picking_id.move_ids:
                            if move.product_id.id == pid and move.location_dest_id.id in loc_ids:
                                loc_qty += move.product_uom_qty
                    for dp in session.distribution_picking_ids:
                        if dp.state == 'done':
                            for move in dp.move_ids:
                                if move.product_id.id == pid and move.location_dest_id.id in loc_ids:
                                    loc_qty += move.product_uom_qty
                    if loc_qty and line.qty:
                        w21_fraction = (loc_qty / line.qty) * (line.total_w21 or 0.0)
                        result[vid][pid] = result[vid].get(pid, 0.0) + w21_fraction

        return result

    def _get_pts_qty_by_vendor(self, product_ids, datetime_from, datetime_to, loc_ids=None):
        """
        Returns {vendor_id: {product_id: qty_sent}, '_vendors': {vendor_id: vendor_name}}
        Product-to-Scrap OUT side (products sent to scrap), split per Vendor/Merchant.

        Filters:
        - state = 'done'
        - date (datetime) within [datetime_from, datetime_to]
        - out_location_id must be in loc_ids (so each location shows only its own PTS)
        """
        dt_from = str(datetime_from)
        dt_to   = str(datetime_to)

        MetalPts = self.env.get('metal.product.to.scrap')
        if MetalPts is None:
            return {}

        domain = [
            ('state', '=', 'done'),
            ('date',  '>=', dt_from),
            ('date',  '<=', dt_to),
        ]
        # KEY FIX: filter by out_location_id — PTS only shows in the location products left from
        if loc_ids:
            domain.append(('out_location_id', 'in', loc_ids))

        result = {'_vendors': {}}
        ops = MetalPts.search(domain)

        for op in ops:
            vendor = op.vendor_id
            vid   = vendor.id if vendor else 0
            vname = vendor.name if vendor else '(No Vendor)'
            result['_vendors'][vid] = vname

            if vid not in result:
                result[vid] = {}

            for line in op.product_line_ids:
                if line.product_id and line.product_id.id in product_ids:
                    pid = line.product_id.id
                    result[vid][pid] = result[vid].get(pid, 0.0) + (line.qty or 0.0)

        return result

    def _get_move_qty(self, product_ids, loc_ids, direction, usage):
        """Sum of done moves in the report period (datetime_from → datetime_to)."""
        dt_from = str(self.datetime_from)
        dt_to   = str(self.datetime_to)
        loc_field = 'location_dest_id' if direction == 'in' else 'location_id'
        domain = [
            ('product_id', 'in', product_ids),
            (loc_field, 'in', loc_ids),
            ('state', '=', 'done'),
            ('date', '>=', dt_from),
            ('date', '<=', dt_to),
        ]
        if usage == 'internal_out':
            domain += [('location_dest_id.usage','=','internal'),
                       ('location_dest_id','not in',loc_ids)]
        elif direction == 'in':
            domain.append(('location_id.usage', '=', usage))
        else:
            domain.append(('location_dest_id.usage', '=', usage))
        result = self.env['stock.move'].read_group(domain, ['product_uom_qty:sum'], [])
        return result[0]['product_uom_qty'] if result and result[0]['product_uom_qty'] else 0.0
