# -*- coding: utf-8 -*-
from . import const  # Central constants — import before any other model

# ── Gold Pricing Models ────────────────────────────────────────────────────
from . import gold_pricing          # ProductTemplate, SaleOrder/Line, Purchase, Account

# ── Precious Metals Inventory Models ──────────────────────────────────────
from . import precious_metal_brand
from . import product_extension     # precious_metals fields added on top of gold_pricing
from . import precious_metal_report
from . import qty_on_hand_report
from . import extra_reports
from . import precious_metal_report_config

# ── Sale / Stock Extensions ────────────────────────────────────────────────
from . import sale_order_extension  # extends sale.order with PM fields (gold, weight, etc.)
from . import stock_picking_extension
from . import product_free_stock    # free_stock_qty = qty_available - reserved (location-based)
from . import stock_picking_batch_extension  # batch availability guard
from . import res_config_settings   # Settings toggle: allow/disallow backorders
