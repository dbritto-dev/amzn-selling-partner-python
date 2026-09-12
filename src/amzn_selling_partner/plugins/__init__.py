"""API-specific knowledge on top of the generic runtime.

``amazon_spapi`` provides the preconfigured ``SellingPartner`` clients (regions,
LWA auth with Restricted Data Tokens, document and notification helpers). The
spec-derived parts (rate limits, pagination, naming) are baked into the
generated ``resources``/``models`` packages by ``codegen/``.
"""
