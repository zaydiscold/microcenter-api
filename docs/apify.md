# Apify packaging and launch status

The repository includes a runnable Actor adapter, Dockerfile, input/output schemas and listing README under .actor/. The package is prepared locally; no public Apify Store listing or paid pricing is claimed until account login, cloud-origin validation and publication have succeeded.

## Run locally

```sh
pip install -e '.[actor]'
python -m microcenter_api.actor_runner
```

The SDK uses local storage without an Apify login. Put INPUT.json in the default key-value store under APIFY_LOCAL_STORAGE_DIR, or use the Apify CLI's local input option. MICROCENTER_CACHE_DIR can point at the CLI's existing cache to share local pacing.

```sh
npx apify-cli validate-schema
docker build -f .actor/Dockerfile -t microcenter-apify:local .
```

[The Actor README](../.actor/README.md) contains example inputs and the complete field/limit contract. All native calls use the existing client: no new scraping engine, browser, proxy or retail credentials. Inputs bound work to 1000 candidate products, 4 stores and 4000 output observations. Dataset rows are saved individually. SUMMARY describes any cap, error or partial window, and survives as the last saved state on ordinary errors. The adapter does not promise resumption across a new cloud run.

## Billing behavior

The adapter uses only Apify's synthetic apify-default-dataset-item event through Actor.push_data. It does not call a second custom charge event for the same row. It checks the SDK charge limit before more catalog work, store lookups or output. Filtering an out-of-stock row does not save/bill a dataset item, though the upstream request still consumes time. The platform start event and dataset pricing must be configured in the account; source code alone does not enable monetization.

Proposed launch pricing is $3 per 1000 product/store observations plus the platform's default synthetic start event. This is a proposal, not a configured price. A product checked at two stores yields two rows. Pricing should be confirmed against real cloud usage, account tier, commission, compute/storage/network fees and failure rates before publication. Do not advertise exact quantities or broader fields absent from the native endpoint.

## Cloud validation and publication

1. Sign in to the intended Apify account and read its plan/prepaid usage state without changing billing.
2. Upload the reviewed package as a private Actor. Use 256 MB memory initially and configure one concurrent run; independent cloud containers do not share the local SQLite pacing gate.
3. Run a bounded smoke test for one exact product at two stores, with a small explicit spending ceiling. Check saved output, timestamps, selected stores, native price/stock semantics and actual compute usage.
4. A local Docker run proves the container and dependencies work. It does not prove access from Apify's cloud IPs. If cloud-origin requests are denied, preserve the error and keep the Actor private rather than promising production reliability.
5. Review the concrete pricing and Store listing, then enable the approved pricing and publish.

Routine account login may open the system-default browser. When a user specifies an existing browser, route its authorization link there and preserve existing tabs. Do not change the OS default browser or create a replacement profile to complete login.

## Local evidence, November 13, 2026

- Apify SDK 4.2.1, macOS/Python 3.14: matte Denim 660548 and DGX Spark 699008, Santa Clara 195 and Tustin 101, four real observations saved.
- Linux/Python 3.12 Docker container: DGX Spark 699008 at both stores, two observations saved and complete summary. No retailer/browser cookies used.
- Input and output schemas validated by Apify CLI 1.12.0.
- Synthetic tests cover two-store identity, unknown quantities, raw inclusion, candidate caps, exact-boundary completeness, invalid inputs, charge-budget stop and partial output preservation after denial/rate limiting.

Cloud build/run, account upload, marketplace publication and revenue remain separate states. Do not infer any of them from local success.

## Restarts and migrations

If a restarted or resurrected run already has dataset rows, this adapter refuses to replay it. Existing output remains available and its summary is preserved; start a new run for a new observation window. This prevents duplicate paid rows. Automatic cursor recovery across cloud migrations is not implemented.

Real SDK local PPE simulation also passed zero-row (no native calls), one-row (stop before the second store) and exact two-row budgets. Synthetic source tests cover duplicate catalog IDs without double charging or false completeness, rejection of invalid falsy inputs and restart replay refusal over existing datasets. These tests do not establish real cloud billing or availability.
