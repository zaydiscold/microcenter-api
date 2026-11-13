# Changelog

## 0.2.0

- Native, cookie-free JSON lookup for store-sensitive availability, store SKU and current/original prices; no browser fallback for default store requests.
- Store-aware product, search, inventory and comparison operations across bundled stores, including Santa Clara195 and Miami185 negative-control verification.
- Paced category scans with per-item atomic checkpoints, resumable catalog discovery and explicit candidate/global versus local totals.
- Keep numerical quantities unknown; reject misleading store-price sorts over global candidate prices and validate store IDs before network activity.
- Preserve product specifications, ratings, review counts and purchase/member-price flags in raw data; document every observed field.
- Map first-party route references with evidence labels and review existing APIs, MCP offerings and open-source stock checkers.

## 0.1.0

- Direct, browser-free public Bloomreach JSON search, category scans, facets and exact product-ID lookup.
- Explicit separation of global catalog prices from unverified local inventory; browser-backed store verification is opt-in.
- Sequential shared pacing, cached observations, JSON/CSV exports, local filtering and resumable scans.
- Full 749-item global filament/resin scan validated against 647 separately verified Santa Clara listing IDs.
- Optional FastAPI service with OpenAPI docs, synthetic regression tests and CI without live scraping.
