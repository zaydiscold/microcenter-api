# Micro Center Native API — Store Stock and Prices

Get product data and store-sensitive availability from Micro Center's native JSON services. No browser, login, cookies, proxy configuration or retailer API key is used by this implementation. This is an unofficial service, not affiliated with Micro Center.

## Quick start

Look up DGX Spark in Santa Clara and Tustin:

```json
{"mode":"product","productIds":["699008"],"storeIds":["195","101"],"maxProducts":1,"maxResults":2}
```

Scan the filament/resin category:

```json
{"mode":"category","categoryId":"754","storeIds":["195"],"maxProducts":1000,"maxResults":1000,"includeOutOfStock":true}
```

Search graphics-card candidates:

```json
{"mode":"search","query":"RTX 5090","storeIds":["195"],"maxProducts":20,"maxResults":20}
```

Keyword search can match broad catalog metadata. Category518 is graphics cards; category106 is desktop computers. Native stock and prices are checked individually for every candidate and selected store. Use exact product IDs to avoid fuzzy search matches. Product IDs differ from store SKUs.

## Output and completeness

The default dataset contains one row per product/store observation: product ID, SKU, name, brand, current/original price, savings, stock flags, store ID, URL, source, observed_at, backend and browser_used. Search/category mode adds the catalog image and catalog price. `includeRaw` preserves vendor fields such as specifications, aggregate ratings and review counts when present.

`stock.in_stock` is a boolean. `stock.quantity` is null: this endpoint does not return numerical units or the displayed 25+ cap. Pickup/shipping flags express eligibility and can be true while stock is false. No open-box units, review bodies, checkout, coupons or bulk-price tiers are exposed.

The SUMMARY record in the default key-value store reports products checked, store observations checked, saved rows, stop reason and completeness. Hitting maxProducts, maxResults, the catalog offset limit or the user's spending limit can produce a useful partial dataset; that is not labeled a complete category inventory. Pages are global candidate pages, not local stock pages. `startPage` selects a partial window, not a persistent cursor. Results are a sequential observation window, not a transactional snapshot.

Original vendor data can be incomplete or change between requests. Native responses are validated before caching. A 403/challenge or 429 stops the run, preserving already saved dataset rows and an incomplete summary. The Actor does not rotate identities, retry denied requests or silently launch a browser.

## Speed and limits

Requests are sequential with 4–5-second pacing and a 5-minute cache within one cache directory. Up to 1000 candidate products and 4 stores can be selected, with a maximum 4000 output rows. A 749-product, single-store verification can take about an hour. Start with one product for a smoke test. Multiple simultaneous cloud runs do not share a machine-local cache; configure the published Actor for one concurrent run until cloud-origin pacing has been validated.

Use 256 MB memory initially. Local Python execution and schema validation are separate from Docker/cloud validation. The cloud-origin test must pass before advertising production reliability.

## Pricing proposal — publication pending

Proposed launch price: $3 per 1000 successfully saved product/store rows, plus Apify's default synthetic start event. Example: one product at two stores creates two rows, proposed row charge $0.006. A 749-row scan is proposed at $2.247 plus the start event. This price has not been enabled on an Apify account.

Use only the automatic apify-default-dataset-item event for saved rows; do not add a second custom event for the same data. The adapter checks Apify's charge limit before more work. Excluded out-of-stock rows consume upstream time but are not saved or charged as dataset items. Platform compute, storage and network expenses still matter. Actual pricing and cloud behavior must be verified before public publication.

## Local execution

From the repository root:

```sh
pip install -e '.[actor]'
python -m microcenter_api.actor_runner
```

Provide INPUT.json through Apify local storage or the CLI. The optional MICROCENTER_CACHE_DIR environment variable lets local tests share the existing CLI pacing/cache. No Apify account is needed for local SDK execution. Apify login is required for upload, cloud runs and Store publication.

Source: https://github.com/zaydiscold/microcenter-api

## Restarts and migrations

If a restarted or resurrected run already has dataset rows, this adapter refuses to replay it. Existing output remains available and its summary is preserved; start a new run for a new observation window. This prevents duplicate paid rows. Automatic cursor recovery across cloud migrations is not implemented.
