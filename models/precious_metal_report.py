from odoo import models


class PreciousMetalReport(models.AbstractModel):
    _name = 'report.precious_metals_suite.report_precious_metal_template'
    _description = 'Precious Metal PDF Report Renderer'

    def _get_report_values(self, docids, data=None):
        import json
        wizards = self.env['precious.metal.report.wizard'].browse(docids)
        report_records = []
        for wiz in wizards:
            d = wiz._get_report_data()
            report_records.append(d)

        company = self.env.company
        logo_b64 = company.logo.decode('utf-8') if company.logo else ''
        return {
            'doc_ids':        docids,
            'doc_model':      'precious.metal.report.wizard',
            'docs':           wizards,
            'data':           data or {},
            'report_records': report_records,
            'company_name':   company.name,
            'company_logo':   logo_b64,
        }
