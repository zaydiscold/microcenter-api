# Micro Center API & CLI

A direct JSON client for Micro Center's public Bloomreach Discovery catalog, with a separately enabled storefront adapter for local inventory. Unofficial; not affiliated with Micro Center.

**The default path uses ordinary HTTPS. No browser, cookies, API key, Cloudflare workaround, or account login.**

```sh
pip install 'microcenter-api-cli[api] @ git+https://github.com/zaydiscold/microcenter-api.git'
microcenter search filament --rpp 200
microcenter search --category 754 --rpp 200
microcenter product 660548
microcenter --output filament.json scan --category 754 --checkpoint scan-filament.json
microcenter serve
# http://127.0.0.1:8766/docs and /openapi.json
```

Python 3.10+. For a source checkout, use `pip install -e '.[api,dev]'`.

## The actual backend

`GET https://core.dxpapi.com/api/v1/core/`

Public storefront configuration exposes Discovery account `7835`. Catalog/domain `microcenter` was verified by a successful unauthenticated product search. `auth_key` is empty, matching Bloomreach's documented client-side convention. These account/catalog identifiers are not private API credentials.

```sh
curl --get 'https://core.dxpapi.com/api/v1/core/' \
  --data-urlencode 'account_id=7835' \
  --data-urlencode 'domain_key=microcenter' \
  --data-urlencode 'auth_key=' \
  --data-urlencode 'request_type=search' \
  --data-urlencode 'search_type=category' \
  --data-urlencode 'q=754' \
  --data-urlencode 'fl=pid,title,brand,price,sale_price,thumb_image,url,category_flat' \
  --data-urlencode 'rows=200' \
  --data-urlencode 'start=0' \
  --data-urlencode 'url=https://www.microcenter.com/'
```

The response includes products, total count, offset, facets and category metadata. Search uses `search_type=keyword`; category lookup uses `search_type=category` and the category ID as `q`. `fq` carries real facet expressions; `sort=pid asc` gives stable ID ordering. Exact product lookup uses `fq=pid:"660548"` and verifies the returned ID.

## Catalog data is not store inventory

This distinction is enforced in code:

| Capability | Direct JSON backend | Explicit storefront fallback |
|---|---|---|
| Keywords, categories, facets, product IDs, images | Verified | Verified |
| Catalog price | Verified | Public store-specific display |
| Santa Clara stock quantities | **Not mapped** | Verified |
| Original shelf price and sale savings | **Not provided reliably** | Verified |
| Store SKU, pickup/shipping flags, color variant links | Not verified | Available where published |
| Browser required | **No** | Yes |

The live comparison found all 647 Santa Clara listing IDs in the 749-item global filament catalog, but one starter pack's global price was $36.99 while Santa Clara displayed $31.96. Therefore direct results never pretend to be store-priced or locally in stock. Unknown stock, SKU, original price and savings stay null. `--store 195` on a direct query fails with a clear explanation, rather than silently attaching a store label to global data.

There is no proven direct JSON endpoint for local stock quantities in this release. `microcenter-api.bloomreach.co` observed in the storefront is an Engagement/analytics host, not established as the inventory API. Passing `view_id=195` produced a valid response but did not establish local inventory semantics; the toolkit does not use that guess.

## Efficient, modest collection

Default request spacing is **4–5 seconds**, sequentially, shared through SQLite across processes using the same cache directory. Parsed responses have a 5-minute local cache with original observation timestamps. `--cache-ttl 0` requests fresh data. No automatic retry on access denial or rate limiting; a 429 surfaces `Retry-After` and stops. No proxy rotation, private-key discovery, challenge solving, or account access.

A complete 749-item filament/resin catalog took **four direct JSON requests**, about **473 KB** total. The separate 647-item store verification used seven HTML responses totaling about **7.2 MB**. Those datasets have different scopes; this is a measured payload comparison, not a promise of equivalent store stock.

Scans checkpoint after each successful page, validate unique IDs against the advertised total, and resume when the same command is repeated. A short/clamped page or repeated page cannot become a successful complete scan. The direct backend has a documented maximum `start` offset of 10,000; broad scans above that limit are refused with instructions to partition by category. The client does not claim an entire chain-wide inventory dump from one paginated query.

```sh
microcenter --output filament.json scan --category 754 --checkpoint scan-filament.json
microcenter --format csv --output silk.csv filter filament.json --query silk
microcenter filter filament.json --query matte --max-price 16
```

Local filtering makes zero network requests. Direct catalog data cannot establish `--sale`: it has no trustworthy original-price field. Use a store-verified snapshot for sale filtering. Listing prices are per item, not automatically per kilogram; sample coils and 500 g spools are identified in their names.

## Optional store verification

```sh
pip install 'microcenter-api-cli[storefront] @ git+https://github.com/zaydiscold/microcenter-api.git'
playwright install chromium
microcenter --storefront search 'matte PLA' --store 195
microcenter --storefront inventory 518159 --stores 195 101 029
microcenter --storefront product 'https://www.microcenter.com/product/660548/inland-175mm-pla-3d-printer-filament-1kg-(22-lbs)-cardboard-spool-matte-denim' --store 195
microcenter --storefront --output local-filament.json scan --store 195 --category 754 --checkpoint scan-local-filament.json
microcenter filter local-filament.json --query matte --sale --max-price 16
microcenter --output colors.html gallery local-filament.json --images filament.json
```

The offline photo gallery can use `--images` to take image URLs from a direct catalog snapshot, joined by exact product ID. This keeps store prices and stock from the verified local snapshot while using the public CDN images returned by Discovery. The `productimages.microcenter.com` host returned 403 in the verification environment; the corresponding Discovery rackcdn image returned 200.

The storefront adapter uses a separate anonymous Chromium context and a public HTML fragment endpoint. It is explicitly a browser-backed scraper, not the direct API. Default Chromium launch requires Playwright's browser installation; `--headed` opens a visible window if a normal session needs inspection. Access denial stops the collector.

Advanced: `--storefront --cdp-url http://127.0.0.1:9222` attaches through a minimal loopback-only CDP transport and creates its own context, without enumerating user tabs or copying login cookies. It closes only its context. Default direct mode ignores browser transport settings because it never creates a browser.

`stores` returns a labeled store-ID directory snapshot (31 physical stores plus `029` shipping). For refreshed nearby-store data, keyword suggestions, exact-SKU comparisons or native color variant links, explicitly select `--storefront`. Store SKU and product ID differ: Denim is SKU `518159`, product ID `660548`. Stock `25+` is a lower bound; a shipping lead time is not a quantity.

## Python SDK

```python
from microcenter_api import Client, StorefrontClient

with Client() as catalog:
    products = catalog.search('matte PLA', rpp=200)
    item = catalog.product('660548')

# Explicit opt-in, requires the storefront extra and Chromium.
with StorefrontClient() as storefront:
    stock = storefront.inventory('518159', stores=['195', '101'])
```

Clients belong to the creating thread. The optional FastAPI service serializes work on one browser/client worker automatically. The HTTP service binds to `127.0.0.1`; it is not deployed publicly by default. `/health` checks process health, not upstream availability. Routes: `/stores`, `/categories`, `/search`, `/product`, `/inventory`, `/compare`, `/suggest`, `/nearby`. Unsupported store-specific direct calls return 422 with an explanation; the service never launches a browser as a hidden fallback. Input errors return 422, upstream access denials 503, upstream rate limits 429, other upstream/parser failures 502. `/docs` and `/openapi.json` describe the current request interface. Run `microcenter --storefront serve` only if you want the optional browser adapter behind the same routes.

## Development and evidence

```sh
pip install -e '.[api,dev]'
pytest
python -m build
```

CI uses synthetic data and fake transports, never live scraping. See [API discovery evidence](docs/api-map.md), [testing](TESTING.md), and [contributing](CONTRIBUTING.md). The full Santa Clara all-category scan was stopped incomplete; no complete 16,895-item capture is claimed. The filament-only store scan and direct global filament scan completed and were compared by exact product ID.

No account, cart mutation, checkout, reservation, coupon redemption, text sending or payment API is exposed. Public data and access policies may change. MIT covers original code only; vendor names, images and product data remain their owners' content. Complete vendor scripts and customer/browser state are not redistributed.
