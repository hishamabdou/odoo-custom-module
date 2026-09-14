import json
from odoo import models


class QtyOnHandReport(models.AbstractModel):
    _name = 'report.precious_metals_suite.report_qty_on_hand_template'
    _description = 'QTY ON HAND PDF Report Renderer'

    def _get_report_values(self, docids, data=None):
        wizards = self.env['qty.on.hand.wizard'].browse(docids)
        report_records = []
        for wiz in wizards:
            d = wiz._get_report_data()
            report_records.append(d)
        company = self.env.company
        logo_b64 = company.logo.decode('utf-8') if company.logo else ''
        return {
            'doc_ids':        docids,
            'doc_model':      'qty.on.hand.wizard',
            'docs':           wizards,
            'report_records': report_records,
            'company_name':   company.name,
            'company_logo':   logo_b64,
        }
