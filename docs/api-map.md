# Direct API discovery and verification

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
| Storefront search fragment | `www.microcenter.com/endeca/AjaxResults.aspx` | Tested; HTML and browser-backed fallback |
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

## What was not established

- A direct JSON service for exact store quantities, store-specific original/sale prices or pickup eligibility.
- A completed full Santa Clara all-category inventory capture. Its broad HTML scan advertised 16,895 items but stopped on hidden-price cards; parser support was corrected, scan remains incomplete.
- A complete 749-item local inventory: 749 is global catalog membership; 647 was the separately verified local in-stock listing.
- A vendor-supported developer API, permission to exceed rate limits, or access to private systems.

No authenticated management APIs were queried. No private keys, cookies or customer data are required or included. The [Cloudflare `cloudflared` daemon](https://developers.cloudflare.com/tunnel/concepts/) establishes tunnels for infrastructure you control; it is unrelated to direct catalog discovery or accessing a retailer's private backend.
