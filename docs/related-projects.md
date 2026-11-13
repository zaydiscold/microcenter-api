# Existing Micro Center clients, APIs and MCP surfaces

Researched November 12, 2026 (America/Los_Angeles). This is a source review, not an endorsement or a claim that paid services were live-tested. No signup, purchase, credentials, executable third-party code or remote MCP installation was used.

## Hosted APIs and MCP

| Project | Primary source | Documented capability | What we can learn |
|---|---|---|---|
| API.SH | [Product](https://api.sh/docs/microcenter-product), [search](https://api.sh/docs/microcenter-search), [reviews](https://api.sh/docs/microcenter-reviews), [Q&A](https://api.sh/docs/microcenter-questions), [MCP](https://api.sh/docs/mcp) | Four Micro Center operations behind its key; page-derived JSON, store selection and MCP integration | Separate aggregates from review/Q&A bodies; preserve timestamps, raw fields and nullable values. Its displayed product example has an empty store_inventory list, so documentation is not evidence of complete cross-store coverage on every product. |
| Scavio | [Micro Center API](https://scavio.dev/microcenter-api) | Documents search, product and stores plus remote MCP; advertises unit counts, open-box records, specs and cross-store flags | Model capped stock separately from exact units; model open-box records independently from new products. No native upstream inventory endpoint disclosed in the inspected page. |
| Apify community actor | [fortuitous_pirate/microcenter-scraper](https://apify.com/fortuitous_pirate/microcenter-scraper) | Keyword/category/store scraping and optional detail pages; advertises MCP readiness | Its example output is explicitly generic. Header and body disagree about pricing, and the claimed 25 locations is below our 31 physical stores plus shipping selector. Treat claims as leads, not validated field coverage. |

The hosted services expose their own JSON contracts. This does not prove that Micro Center's upstream pages contain an equivalent public native JSON endpoint. We did not adopt a paid dependency or route our scan through them.

## Open-source implementations inspected

Sources were downloaded read-only through GitHub REST tree listings and raw.githubusercontent.com. No code was executed or copied into this client. The companion research-sources.json records the commit references and file blob SHAs and inspected paths for reproducibility.

| Repository | Observed approach | Useful finding |
|---|---|---|
| [ayoTyler/StockSmart](https://github.com/ayoTyler/StockSmart) | Selenium, storeSelected cookie and product-page inspection | Confirms store preference cookie convention, but supplies no browser-free upstream inventory endpoint. |
| [willgorman/microcenter-inventory](https://github.com/willgorman/microcenter-inventory) | Selenium WebDriver with storeSelected cookie and parsed stock text | Quantity label parsing and metrics design; no new JSON stock endpoint found in inspected checker. |
| [darakelian/MCStockCheckerBot](https://github.com/darakelian/MCStockCheckerBot) | Requests page content and parses inline inventory array | A genuine avenue: historical code treats qoh as a quantity. Current captured Denim page has only0/1 qoh values while selected-store text showed multiple units. Do not reuse its quantity interpretation without checking current semantics. |
| [ethanbeauc/microcenter-notify](https://github.com/ethanbeauc/microcenter-notify) | HTML scraping plus Pushover notification | Confirms ordinary price/availability monitoring use case; notification behavior is outside this read-only client. |
| [wonsong82/microcenter_finder](https://github.com/wonsong82/microcenter_finder) | Selected JavaScript paths only | No useful native product API found in those paths; not a complete codebase audit. |

GitHub repository searches for `microcenter mcp` returned no matches; `microcenter api` returned this repository only at observation time. This is a limited discovery result, not proof that no other implementations exist. Broad `microcenter` search returned40 repositories; five relevant implementations were inspected. X search `microcenter API` produced mostly unrelated posts and an old scraper mention, with no additional endpoint evidence.

## Additional avenues and confidence

- **Verified:** native JSON already provides aggregate ratings, review count, detailed specifications, product highlights, color, UPC/MPN, listing flags and member-price flags. See [the full field map](native-fields.md). These require no extra request per product.
- **Observed in current page source:** inline inventory array with one flag per store. It is HTML-embedded and therefore outside the API-only scan. Current0/1 values must not become numerical unit counts.
- **Source-discovered:** recommendation handlers and advanced-refinement routes. They may help catalog discovery, but their payloads, completeness and store semantics are unverified. See endpoint-surfaces.json for route provenance and status.
- **Unverified:** direct review/Q&A provider endpoint, exact stock quantities, open-box units, native batch inventory and additional bulk tiers. A Bazaarvoice asset reference is a lead only; no review endpoint or key contract has been claimed verified.
- **Not exercised:** cart, account, notification, analytics-reporting and checkout mutations. Public JavaScript mentions routes with multiple operations; only `type=product` is used on getProductAttributes.aspx.

## Reproducibility

1. `gh search repos microcenter --limit 40 --json fullName,description,url,updatedAt`.
2. Query `https://api.github.com/repos/{owner}/{repo}/git/trees/HEAD?recursive=1` and `https://api.github.com/repos/{owner}/{repo}/commits/HEAD`; save returned references and verify downloaded file contents against the tree entries using Git blob hashes.
3. Read the listed source files from the pinned commit via raw.githubusercontent.com. Inspect HTTP calls and selectors without running source.
4. Compare the native JSON fields with vendor documentation; keep advertised, source-observed and live-verified states distinct.
5. Reproduce the native endpoint using the request in api-map.md and native-fields.md. Reuse the paced CLI/cache for repeated calls.


## November 13 follow-up: actual access checks and marketplace metadata

API.SH's product endpoint returned 401 without its x-api-key header. Scavio's product endpoint returned 401 without Authorization. This verifies access requirements, not the advertised product output. No competitor account or paid run was created.

Apify public Store/API metadata was retrieved without login. Direct Micro Center listings included sian.agency/microcenter-product-scraper, fortuitous_pirate/microcenter-scraper, memo23/microcenter-product-scraper, pyralislabs/microcenter-ai-instore-sniper and quarterly_jingo/microcenter-scraper. Their configured pricing events and recent run statistics provide stronger evidence of active listings than marketing text alone. Run-success metadata still does not establish that quantities, prices or completeness are correct. Configured FREE and BRONZE prices differ on some Actors; compare actual event/tier prices rather than only the headline “from” price. We did not run these paid Actors.

The [Firecrawl Micro Center provider](https://www.firecrawl.dev/alexandria/microcenter-com) advertises five typed capabilities (product, reviews, stores, SKU lookup and search), each listed at 5 credits per execution. Actual search_products(category Filaments & Resins|754,store 195) and get_product(DGX 699008,store 195) both returned provider 502 errors. Retrying the known-product call also returned 502. Receipts reported 0 credits charged. The advertised contract is therefore a useful field/schema reference, but it did not supply a working independent data check in this run.

The native client independently completed 90 selected high-end products across Santa Clara 195 and Tustin 101, 180 observations. Availability differed by store and some returned native prices differed, including the PNY RTX PRO 6000. This validates the store parameter beyond the earlier filament control. Filament refresh attempts encountered transient HTTP 403 responses and stopped; later single diagnostic requests for those IDs returned 200 JSON. A 403 alone is not proof of a Cloudflare challenge or proof of a network-change cause.
