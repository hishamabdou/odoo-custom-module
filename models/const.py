# -*- coding: utf-8 -*-
"""
Central constants for precious_metals_suite.
Import from here instead of hardcoding strings across the module.
"""

# ── Inventory Division Codes ────────────────────────────────────────────────
DIVISION_RETAIL  = 'RETAIL'
DIVISION_WEB     = 'WEB'
DIVISION_FINTECH = 'FINTECH'
DIVISION_CORP    = 'CORP'

# ── Metal Types ─────────────────────────────────────────────────────────────
METAL_GOLD   = 'Gold'
METAL_SILVER = 'Silver'
METAL_MIXED  = 'Mixed'

METAL_TYPES = [
    ('gold',   METAL_GOLD),
    ('silver', METAL_SILVER),
    ('other',  'Other'),
]

# ── Karat: special values ────────────────────────────────────────────────────
KARAT_SILVER = 'Silver'
KARAT_ZERO   = '0'
