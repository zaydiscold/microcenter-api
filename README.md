i just really wanted 3d printing filament man

# Micro Center API & CLI

Unofficial JSON API client, Python SDK and CLI for Micro Center's catalog, store availability and current prices. **Default operations use ordinary HTTP: no browser, login, cookies, API keys or HTML parsing.** Not affiliated with Micro Center.

## Install

```sh
pip install 'microcenter-api-cli[api] @ git+https://github.com/zaydiscold/microcenter-api.git'
microcenter search filament --rpp 200
microcenter product 660548 --store 195
microcenter inventory 518159 --stores 195 185
microcenter serve
# http://127.0.0.1:8766/docs and /openapi.json
```

Python 3.10+. From a checkout: `pip install -e '.[api,dev]'`.

## Two actual JSON backends

| Purpose | Endpoint | Verified data |
|---|---|---|
| Catalog discovery | GET `https://core.dxpapi.com/api/v1/core/` | Product IDs, names, catalog prices, images, category and facets; up to 200 products per call |
| Store product lookup | POST `https://www.microcenter.com/assets/ajax/getProductAttributes.aspx?storeid=195` | Exact SKU, current price, original price, discount, **store-specific in-stock flag**, eligibility and specs |

The native product endpoint works with these normal AJAX request headers and form fields:

```sh
curl 'https://www.microcenter.com/assets/ajax/getProductAttributes.aspx?storeid=195' \
  -H 'Accept: application/json' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -H 'X-Requested-With: XMLHttpRequest' \
  --data 'type=product&product_id=660548'
```

No cookies, Authorization header, browser session, Cloudflare clearance or private key are supplied. Changing only `storeid` from `195` (Santa Clara) to `185` (Miami) changed this product's `in_stock` from `True` to `False` in direct HTTP verification. The public preference cookie `storeSelected` was tested separately and also worked, but the client does not need or send it.

**Stock is a boolean, not a unit count.** The native JSON endpoint does not return the `6` or `25+` shown in storefront HTML. The client leaves `stock.quantity` null and sets `quantity_provided: false`. `can_pickup`/`can_ship` are eligibility flags and must not be mistaken for in-stock status.

Native prices take precedence over catalog prices. The starter pack `692941` returned $31.96 and original price $49.99 from the native API, while the Discovery catalog returned $36.99. This proves a real pricing-source discrepancy; the tested pack had the same native price in the tested stores, so no cross-store price difference is claimed. Store ID is part of every native request and cache key.

## Scan a store, then search locally

```sh
# All global filament/resin candidates: 749 at the initial observation.
microcenter --output catalog.json scan --category 754 --checkpoint scan-catalog.json

# Verify every candidate through the native JSON endpoint for Santa Clara.
microcenter --output santa-clara.json scan --store 195 --category 754 --checkpoint scan-santa-clara.json

# Resume by repeating the same command after an interruption.
# Include unavailable entries in output when desired:
microcenter --output all-statuses.json scan --store 195 --category 754 --include-out-of-stock --checkpoint scan-all-statuses.json

# Local operations make zero network requests.
microcenter filter santa-clara.json --query matte --sale --max-price 16
microcenter --format csv --output silk.csv filter santa-clara.json --query silk --sale
microcenter --output colors.html gallery santa-clara.json --images catalog.json
```

Global discovery is batched; **native stock verification is one request per product**. Three tested batch parameter shapes returned no products, so the toolkit does not pretend they work. Defaults are one request every **4–5 seconds**, sequentially. A full 749-candidate verification takes roughly an hour at that pace; narrow by category/query for everyday use. `--delay` and `--jitter` configure modest pacing; delays below one second are clamped. Pacing is shared across processes using the same cache directory.

Parsed observations have a 5-minute disk cache with original timestamps. `--cache-ttl 0` requests fresh observations. A 403/challenge or 429 stops without automatic retries; 429 surfaces `Retry-After`. No identity rotation or challenge solving. Do not use separate cache directories to defeat pacing.

Store scan checkpoints use a small atomic manifest and one observation file per product in the adjacent `.items` directory. Each result is written once rather than repeatedly rewriting the entire growing inventory. Keep the manifest, `.items` directory and `.catalog.json` together to resume. The final `--output` JSON is self-contained. A scan is complete only after every unique catalog candidate has been verified. It is an observation window, not a transactional stock snapshot.

The direct discovery backend has a maximum `start` offset of 10,000. Broad scans exceeding that limit are refused; partition by category rather than accepting a truncated catalog. No complete all-category Santa Clara capture is claimed from the initial prototype.

## Search pagination and identity

```sh
microcenter search --category 754 --store 195 --rpp 10
microcenter search 'RTX 5070' --store 101 --rpp 5
microcenter product 660548 --store 195
microcenter compare 518159 330472 --store 195
```

A store search first gets a global candidate page, then looks up each candidate through native JSON. Filtering that page to in-stock items does not establish a total for the entire store. The response therefore carries `candidate_total_results`, `candidate_returned`, a local `returned`, and `total_results: null`. Offsets/pages refer to global candidates. Store-scoped price sorting is rejected because sorting stale catalog candidates cannot establish global native-price order. Use a complete store scan and offline filtering/sorting for local totals and prices. Store searches take one native request per candidate; large page sizes can be slow.

Product IDs and store SKUs differ: Denim is product `660548`, SKU `518159`. SKU inventory verifies the returned `short_sku`, so fuzzy search cannot substitute another product. `not_listed` means no exact match was established, not a zero-stock result. An explicit false native flag means out of stock at that selected store.

Catalog-only data has no trustworthy original-price field. `filter --sale` refuses a catalog-only snapshot rather than claiming no products are discounted. Prices are per listed item, before tax, not automatically per kg; watch 500 g rolls and sample coils.

## Python SDK and JSON API

```python
from microcenter_api import Client

with Client() as client:
    catalog = client.search('matte PLA', rpp=200)
    denim = client.product('660548', store='195')
    stock = client.inventory('518159', stores=['195', '185'])
```

`microcenter serve` binds to loopback. Routes: `/health`, `/stores`, `/categories`, `/search`, `/product`, `/inventory`, `/compare`, `/suggest`, `/nearby`; interactive docs at `/docs`, schema at `/openapi.json`. Product example: `/product?url=660548&store=195`. Inventory store lists use repeated `stores` query parameters. Scans run through the CLI, not long web requests. Upstream work is serialized. `/health` checks process health, not upstream access.

Input errors return 422, upstream access denial 503, rate limiting 429 and other upstream/parser errors 502. Default autocomplete and nearby-store provider endpoints are not yet mapped; those calls explain the limitation rather than opening a browser.

`stores` is a labeled directory snapshot: 31 physical stores plus shipping (`029`). `categories` returns global discovery facets, not local availability. Category facet enumeration is not claimed exhaustive.

## Optional legacy HTML adapter

`StorefrontClient` and `--storefront` remain explicit options for storefront-only fields, including displayed unit counts and native variant links. They are **not required for store availability or pricing**.

```sh
pip install 'microcenter-api-cli[storefront] @ git+https://github.com/zaydiscold/microcenter-api.git'
playwright install chromium
microcenter --storefront search 'matte PLA' --store 195
```

This adapter parses HTML in a separate anonymous browser context and stops on denial. Advanced loopback CDP mode creates only its own context without enumerating user tabs or copying cookies. The default JSON paths never invoke it.

## Development and evidence

```sh
pip install -e '.[api,dev]'
pytest
python -m build
```

CI uses synthetic fixtures and fake transports, not live scraping. [Discovery evidence and request contracts](docs/api-map.md), [testing](TESTING.md), [contributing](CONTRIBUTING.md).

No cart mutation, checkout, reservation, coupon redemption, SMS, account records or payment API is exposed. Original code is MIT licensed; vendor names/images/product data remain their owners' content. Private keys, browser profiles, cookies, complete vendor bundles and local inventory snapshots are not redistributed.

## Research and endpoint coverage

- [Verified contracts and reproducible evidence](docs/api-map.md), with the [machine-readable endpoint contracts](docs/endpoints.json)
- [Every observed native product field](docs/native-fields.md) and [machine-readable field map](docs/native-fields.json)
- [Source-discovered route inventory with confidence labels](docs/endpoint-surfaces.json)
- [Existing API/MCP services and open-source clients](docs/related-projects.md), with [pinned source records](docs/research-sources.json)

## Apify Actor

A bounded, streaming Actor adapter is included for store-aware search, category scans and exact product lookups. Its schemas, Docker build and local SDK/container execution are tested. Cloud-origin access and marketplace publication require separate validation; no paid listing is claimed. See [Apify setup, billing behavior and launch status](docs/apify.md) and [the proposed Actor listing](.actor/README.md).
