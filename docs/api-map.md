# Direct API discovery and verification

**Current status:** native store-specific JSON availability and pricing lookup is verified. See the follow-up section below for the cookie-free POST contract. Discovery-only observations remain as historical context.

Observed November 12, 2026, America/Los_Angeles. Earlier work wrapped public HTML endpoints; the default implementation was replaced after locating the actual public JSON backend.

## Reproduction

1. Inspect the public search page's `br_data` configuration. It exposes `acct_id: 7835` and loads a Discovery tracking reference for that account. Only public account/catalog identifiers were used; no visitor IDs or session cookies were copied.
2. Consult Bloomreach's first-party [Product/Category API](https://documentation.bloomreach.com/discovery/reference/product-and-category-search-api) and [request parameters](https://documentation.bloomreach.com/discovery/reference/get-products-categories). The documentation says to leave private `auth_key` empty for client-side requests.
3. Plain Python `urllib.request`, with no cookies or browser, queried `https://core.dxpapi.com/api/v1/core/`. Without a domain, the service returned HTTP 400 JSON: `Invalid Request: domain_key is required`. This established reachability, not catalog access.
4. The catalog identifier `microcenter` was a hypothesis based on the public site name. A request with that identifier returned HTTP 200 JSON and real Micro Center product IDs/URLs, establishing it empirically. The identifier is not a private credential.
5. Keyword `filament`, two rows, returned 1,106 matches across categories. Exact store-SKU keyword `518159` found product `660548` (Denim). Wildcard `fl=*` was rejected because `pid` is mandatory; `fl=pid,*` returned only `pid`, so wildcard field discovery is not supported as assumed. The client explicitly requests verified fields.
6. Category `754`, `search_type=category`, `sort=pid asc`, 200 rows per call returned 749 unique filament/resin entries in four calls. All response offsets and totals were checked. Total body bytes: 473,328. All calls used ordinary HTTP and empty `auth_key`, without an authorization header, cookies, Cloudflare clearance or a browser.
7. Compared these 749 IDs against a separately completed fresh Santa Clara HTML listing: 647 IDs, all present in the JSON set. Prices agreed for 646 of 647. Starter pack `692941` was $36.99 globally but $31.96 in the Santa Clara listing. Global catalog prices are therefore never labeled store-specific prices.
8. Store quantities, original shelf prices, SKU fields and inventory flags were not returned under the tested standard/custom field names. A successful `view_id=195` response did not prove store-scoped semantics. No guessed store filter is shipped.

## Verified direct contract

| Parameter | Meaning / tested value |
|---|---|
| `account_id` | Public Discovery account `7835` |
| `domain_key` | Verified catalog `microcenter` |
| `auth_key` | Empty; no private key used |
| `request_type` | `search` |
| `search_type` | `keyword` or `category` |
| `q` | Keyword, `*`, or category ID such as `754` |
| `fl` | `pid,title,brand,price,sale_price,thumb_image,url,description,category_flat` |
| `rows` | Up to 200; four-page scan exercised at 200 |
| `start` | Zero-based offset; provider documents maximum 10,000 |
| `sort` | `pid asc` tested for stable scan ordering |
| `fq` | Facet filter; exact product retrieval by `pid:"660548"` tested |
| `request_id` | Fresh request identifier; no user/session identifier |
| `url` | Public Micro Center site URL |

Response envelope: `response.numFound`, `response.start`, `response.docs`, `facet_counts`, `category_map`, `metadata`. The wrapper preserves observation times, scope, source, count, offset, raw product fields and parsed display fields. Unknown local stock and original prices remain null.

Returned facet names include brand, category, category_flat, Material, Color, Diameter, Finish, Subcategory, Valuable Links, Micro Center Deals, Average_Rating and OpenBox. Their values are returned by the backend and can be carried into `fq`. Category facet enumeration is not claimed exhaustive: response limits may cap the list.

## Other surfaces and their limits

| Surface | Route | Status |
|---|---|---|
| Storefront search fragment | `www.microcenter.com/endeca/AjaxResults.aspx` | Tested HTML; plain HTTP AJAX also succeeded; excluded from API-only scan |
| Product / color variants | `/product/{id}/{slug}`, `/quickView/{id}/{slug}` | Tested HTML; local quantities and limits |
| Store directory | `/assets/ajax/StoreChange.aspx` | Tested HTML; packaged directory labeled snapshot |
| ZIP lookup | POST `/assets/ajax/storeZipCode.aspx` | Tested HTML; optional fallback only |
| Autosuggest | POST `/assets/ajax/autosuggest.aspx` | Tested HTML; direct provider suggestion API not yet verified |
| Advanced refinements | `/assets/ajax/advancedsearchbr.aspx` | Found in public source, not exercised |
| Current native comparison | `/endeca/CompareV2.aspx` | Live form observed; wrapper composes exact-SKU details instead |
| Legacy comparison | `/endeca/compare.aspx` | Found in source; test failed; not used |
| Banner promotions | `/assets/ajax/BannerX.aspx` | Observed 200 JSON; ad rendering, not a bulk-price quote service |
| Engagement host | `microcenter-api.bloomreach.co` | Observed analytics/experiment calls; not established as product inventory |
| Quantity-priced cart | `cart.microcenter.com` | Prior disposable anonymous test only; no mutation code exposed |

Quantity study: 1/5/10 matte-black spools totaled $10.99/$54.95/$109.90. A 12-roll basket adding blue–green silk and black PETG+ totaled the expected $137.88, without extra quantity discount. Removed all test lines, verified $0.00, disposed context; no checkout. Those observations are specific to tested baskets, not every promotion.

## What was not established in v0.1.0 (historical)

- A direct JSON service for exact store quantities, store-specific original/sale prices or pickup eligibility.
- A completed full Santa Clara all-category inventory capture. Its broad HTML scan advertised 16,895 items but stopped on hidden-price cards; parser support was corrected, scan remains incomplete.
- A complete 749-item local inventory: 749 is global catalog membership; 647 was the separately verified local in-stock listing.
- A vendor-supported developer API, permission to exceed rate limits, or access to private systems.

No authenticated management APIs were queried. No private keys, cookies or customer data are required or included. The [Cloudflare `cloudflared` daemon](https://developers.cloudflare.com/tunnel/concepts/) establishes tunnels for infrastructure you control; it is unrelated to direct catalog discovery or accessing a retailer's private backend.

## November 12 follow-up: native store JSON endpoint verified

The earlier conclusion that local stock required a browser was incorrect. Plain HTTP AJAX requests were not tested thoroughly enough. Micro Center's native endpoint accepts ordinary POST requests with the expected headers:

```text
POST https://www.microcenter.com/assets/ajax/getProductAttributes.aspx?storeid=195
Accept: application/json
Content-Type: application/x-www-form-urlencoded
X-Requested-With: XMLHttpRequest

 type=product&product_id=660548
```

No cookies, credentials, browser state, clearance tokens or Authorization header are required. The client supplies a descriptive User-Agent. Response was HTTP 200, `application/json; charset=utf-8`, without `cf-mitigated`. The page's public first-party JavaScript references this route as product-data enrichment; the handler itself is read-only in the usage exercised here.

### Store-selection controls

| Request | Native result |
|---|---|
| Denim 660548, `storeid=195`, no cookies | `in_stock: "True"`, SKU 518159, price 10.99, original 19.99 |
| Denim 660548, `storeid=185`, no cookies | `in_stock: "False"`, same product/SKU and price |
| Denim 660548, public `storeSelected=195` cookie | True |
| Denim 660548, public `storeSelected=185` cookie | False |
| Pack 692941, `storeid=195` | price 31.96, original 49.99 |
| Pack 692941, tested preference 195 or 029 | price 31.96 in both cases |

The store preference cookie is not an authentication cookie. It was tested to understand semantics, but implementation uses only the `storeid` URL parameter and sends no Cookie header. The explicit true/false location contrast proves store-sensitive availability. Pack prices were identical across the tested native-store contexts, so the evidence establishes a discrepancy with the stale/global Discovery source, not a cross-store price difference.

Fields returned: product_id, short_sku, title, brand, price, original_price, discount, in_stock, can_pickup, can_ship, UPC, manufacturer_number, category metadata, member-price flags and physical specifications. Numerical stock quantity is absent. `can_pickup: True` can coexist with `in_stock: False` and represents eligibility, not availability.

### Batch and completeness tests

Comma-separated `product_id`, plural `product_ids`, and JSON `product_list` input shapes each returned only a small metadata object with no product. They are not treated as a working batch contract. The implementation verifies one candidate per request with shared pacing, disk cache and per-item resumable checkpoints.

Global catalog pagination and store lookup are separate. Store search responses retain candidate offsets/counts and do not mislabel global totals as local totals. Complete scans validate every unique candidate before publishing a local available-item total. Unit quantities remain null throughout.

These verified native JSON capabilities supersede the earlier “What was not established” statements about availability flags and current/original prices. Exact unit counts and a batch native inventory endpoint remain unverified. The historical observations above are retained to show how the conclusion changed.

## Extended field and ecosystem mapping

The [native field map](native-fields.md) describes all observed product fields and distinguishes purchase eligibility, member flags and vendor specifications from stock quantities or guaranteed prices. The [route inventory](endpoint-surfaces.json) labels each first-party JavaScript route by evidence and SDK usage. The [related-project review](related-projects.md) records hosted API/MCP capabilities and source findings without treating vendor claims as verified upstream endpoints.
