# Contributing

Install with `pip install -e '.[api,dev]'`, run `pytest`, and build with `python -m build`.
Tests must use synthetic HTML fixtures or fake transports; do not introduce automated live scraping into CI. Do not commit cookies, tokens, customer data, browser profiles, or local scan/cache files. Keep the default direct JSON client, explicit storefront opt-in, public read-only endpoint allowlists, exact-SKU identity checks, visible block/rate-limit errors, and sequential pacing intact.

For markup bugs, provide a small synthetic fixture reproducing the structure without account data. Distinguish verified live behavior, fixture-only behavior and routes discovered in source but not exercised. Do not claim a stock count is exact when the site displays `25+`.
