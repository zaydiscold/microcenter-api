# Testing

Run `pytest` from the repository root after `pip install -e '.[api,dev]'`.
The test suite performs no live network operations and needs no browser installation.
Build validation: `python -m build`.

Live scans must be explicitly requested, sequential and paced. Use `--checkpoint` so a block or interruption preserves completed pages. Do not mark an incomplete or duplicate-truncated scan complete. Full catalog scans capture changing inventory over time; include count drift warnings and observation windows.


Native store regression coverage includes distinct store cache keys and true/false stock controls, exact SKU identity, invalid title/flags/prices, catalog/native price disagreement, candidate pagination, rejected misleading price sorts, store-link preservation, interruption after a rate-limit response and resume without duplicate completed observations. The HTTP product route also exercises the real client with a synthetic native transport and no global catalog call.

Release 0.2.0 local validation:55 tests passed; wheel and sdist built. An installed wheel was exercised in a separate environment with no Playwright package: cached real native data returned store195, product660548, price10.99, stockTrue, quantitynull and browser_usedFalse. That wheel smoke reused previously observed data and made no live upstream requests. Live upstream evidence is documented separately in docs/api-map.md.

## Actor adapter validation (0.3.0)

With `pip install -e ".[actor,api,dev]"`, 73 tests pass locally, including three real SDK local PPE budget simulations with fake retailer responses and no paid cloud calls. Without the optional Actor SDK, those three tests are skipped. Local real-data SDK execution and Linux Docker execution were also exercised separately. Source review covers billing limits, duplicate candidate IDs, retained-dataset restart refusal, invalid inputs and completeness semantics. Cloud-origin access and actual account pricing are not established by these tests.
