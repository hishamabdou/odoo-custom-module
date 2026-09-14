import json
from odoo import models


class ProductLedgerReport(models.AbstractModel):
    _name = 'report.precious_metals_suite.report_product_ledger_template'
    _description = 'Product Ledger PDF Renderer'

    def _get_report_values(self, docids, data=None):
        wizards = self.env['product.ledger.wizard'].browse(docids)
        records = []
        for wiz in wizards:
            d = wiz._get_report_data()
            records.append(d)
        company = self.env.company
        logo_b64 = company.logo.decode('utf-8') if company.logo else ''
        return {'doc_ids': docids, 'doc_model': 'product.ledger.wizard',
                'docs': wizards, 'report_records': records,
                'company_name': company.name, 'company_logo': logo_b64}


class AdjustmentLogReport(models.AbstractModel):
    _name = 'report.precious_metals_suite.report_adjustment_log_template'
    _description = 'Adjustment Log PDF Renderer'

    def _get_report_values(self, docids, data=None):
        wizards = self.env['adjustment.log.wizard'].browse(docids)
        records = []
        for wiz in wizards:
            d = wiz._get_report_data()
            records.append(d)
        company = self.env.company
        logo_b64 = company.logo.decode('utf-8') if company.logo else ''
        return {'doc_ids': docids, 'doc_model': 'adjustment.log.wizard',
                'docs': wizards, 'report_records': records,
                'company_name': company.name, 'company_logo': logo_b64}


class ComparisonReport(models.AbstractModel):
    _name = 'report.precious_metals_suite.report_comparison_template'
    _description = 'Comparison Report PDF Renderer'

    def _get_report_values(self, docids, data=None):
        wizards = self.env['comparison.report.wizard'].browse(docids)
        records = []
        for wiz in wizards:
            d = wiz._get_report_data()
            records.append(d)
        company = self.env.company
        logo_b64 = company.logo.decode('utf-8') if company.logo else ''
        return {'doc_ids': docids, 'doc_model': 'comparison.report.wizard',
                'docs': wizards, 'report_records': records,
                'company_name': company.name, 'company_logo': logo_b64}
