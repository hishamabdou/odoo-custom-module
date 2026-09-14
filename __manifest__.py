# -*- coding: utf-8 -*-
{
    'name': 'Precious Metals Suite',
    'version': '19.0.2.88.0',
    'category': 'Inventory',
    'summary': 'Gold & Silver — Pricing, Inventory, Serial Management, Reports',
    'description': """
Precious Metals Suite
=====================
مديول متكامل يجمع:

1. Gold Pricing (تسعير الذهب والفضة)
   - حساب الأسعار تلقائياً بناءً على العيار والوزن
   - دعم أوامر البيع والشراء والفواتير
   - معادلة: ذهب = وزن × (عيار/875) × سعر 21 | فضة = وزن × سعر الفضة

2. Precious Metals Inventory (مخزون المعادن الثمينة)
   - تقارير حركة المخزون (PDF)
   - تقرير الرصيد الحالي (QTY ON HAND)
   - دفتر الأستاذ للمنتج (Product Ledger)
   - سجل التسويات (Adjustment Log)
   - تنبيهات الحد الأدنى للمخزون
   - مقارنة الفترات
   - العلامات التجارية (Brands)

    """,
    'author': 'Hisham Yehia',
    'website': '',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'product',
        'stock',
        'stock_picking_batch',
        'sale_management',
        'sale_stock',
        'purchase',
        'account',
        'mail',
        'sales_team',
    ],
    'data': [
        # Security — Groups must load BEFORE access rules CSV
        'security/precious_metals_groups.xml',
        'security/ir.model.access.csv',

        # Data
        'data/precious_metal_brand_data.xml',
        'data/cron_data.xml',

        # Views — Gold Pricing (Sale, Purchase, Invoice)
        'views/gold_pricing_views.xml',
        'views/sale_order_list_view.xml',
        'views/stock_picking_list_view.xml',
        'views/stock_quant_views.xml',
        'views/purchase_order_views.xml',
        'views/res_config_settings_views.xml',

        # Views — Product
        'views/product_template_views.xml',
        'views/precious_metal_brand_views.xml',


        # Views — Sale Order
        'views/sale_order_views.xml',

        # Wizards
        'wizard/precious_metal_report_wizard_views.xml',
        'wizard/qty_on_hand_wizard_views.xml',
        'wizard/extra_wizard_views.xml',
        'wizard/multi_add_products_wizard_views.xml',
        'wizard/pm_unlock_reason_wizard_views.xml',

        # Reports
        'report/delivery_slip_extension.xml',
        'report/precious_metal_report_templates.xml',
        'report/qty_on_hand_report_template.xml',
        'report/extra_report_templates.xml',


        # Settings
        'views/precious_metal_report_config_views.xml',

        # Menus (last — after all actions are defined)
        'views/menu_views.xml',

    ],
    'assets': {
        'web.assets_backend': [
            'precious_metals_suite/static/description/style.css',
            'precious_metals_suite/static/src/css/sale_order_list.css',
            'precious_metals_suite/static/src/js/sale_order_list.js',
        ],
    },
    'demo': [],
    'installable': True,
    'application': True,
    'auto_install': False,
}
