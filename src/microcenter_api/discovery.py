"""Direct Bloomreach Discovery JSON client. No browser, cookies or private keys."""

import json, re, time, urllib.error, urllib.parse, urllib.request
from pathlib import Path
from .client import cache_home, utcnow, write_json
from .storage import Storage
from .errors import MicroCenterError, BlockedError, RateLimitedError, ParseError

ENDPOINT = "https://core.dxpapi.com/api/v1/core/"
FIELDS = "pid,title,brand,price,sale_price,thumb_image,url,description,category_flat"


class DiscoveryClient:
    def __init__(
        self,
        *,
        delay=4.0,
        jitter=1.0,
        cache_ttl=300,
        cache_dir=None,
        fetch=None,
        store_fetch=None,
        **kwargs,
    ):
        self.storage = Storage(
            Path(cache_dir or cache_home()) / "cache.sqlite", delay=delay, jitter=jitter
        )
        self.cache_ttl = max(0, float(cache_ttl))
        self.fetch = fetch or self._http
        from .store_api import http_attributes

        self.store_fetch = store_fetch or http_attributes
        self.metrics = {"network_requests": 0, "cache_hits": 0, "response_bytes": 0}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def close(self):
        pass

    def _http(self, url):
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "microcenter-api-cli/0.2.0",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as r:
                if urllib.parse.urlsplit(r.url).netloc != "core.dxpapi.com":
                    raise MicroCenterError("Unexpected upstream redirect")
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 429:
                raise RateLimitedError(e.headers.get("Retry-After")) from e
            if e.code in (401, 403):
                raise BlockedError(
                    "Direct search access was denied; no browser fallback or credential retry was attempted"
                ) from e
            raise MicroCenterError(f"Direct search returned HTTP {e.code}") from e
        except (urllib.error.URLError, TimeoutError) as e:
            raise MicroCenterError(
                "Direct search request failed; no automatic retry"
            ) from e

    def _query(self, query="*", *, category=None, fq="", start=0, rows=24, sort=""):
        params = {
            "account_id": "7835",
            "domain_key": "microcenter",
            "auth_key": "",
            "request_type": "search",
            "search_type": "category" if category else "keyword",
            "q": str(category) if category else query or "*",
            "fl": FIELDS,
            "rows": rows,
            "start": start,
            "url": "https://www.microcenter.com/",
        }
        if fq:
            params["fq"] = fq
        if sort and sort != "match":
            params["sort"] = {
                "pricelow": "sale_price asc",
                "pricehigh": "sale_price desc",
            }.get(sort, sort)
        cache_key = self.storage.key({"backend": "discovery", "params": params})
        cached = self.storage.get(cache_key, self.cache_ttl)
        if cached is not None:
            self.metrics["cache_hits"] += 1
            cached["cache_hit"] = True
            return cached
        self.storage.wait()
        params["request_id"] = str(time.time_ns())
        url = ENDPOINT + "?" + urllib.parse.urlencode(params)
        raw = self.fetch(url)
        self.metrics["network_requests"] += 1
        self.metrics["response_bytes"] += len(raw)
        try:
            data = json.loads(raw)
        except (ValueError, TypeError) as e:
            raise ParseError("Direct backend did not return JSON") from e
        if not isinstance(data, dict):
            raise ParseError("Direct backend returned a non-object JSON envelope")
        response = data.get("response")
        if (
            not isinstance(response, dict)
            or not isinstance(response.get("numFound"), int)
            or not isinstance(response.get("docs"), list)
        ):
            raise ParseError("Invalid Discovery JSON envelope")
        if response.get("start") != start:
            raise ParseError("Direct backend returned an unexpected page offset")
        result = {
            "source": ENDPOINT,
            "request": {
                k: v for k, v in params.items() if k not in {"auth_key", "request_id"}
            },
            "observed_at": utcnow(),
            "backend": "discovery",
            "browser_used": False,
            "cache_hit": False,
            "total_results": response["numFound"],
            "start": start,
            "returned": len(response["docs"]),
            "products": [self._product(x) for x in response["docs"]],
            "facets": data.get("facet_counts", {}),
            "category_map": data.get("category_map", {}),
            "response_bytes": len(raw),
            "inventory_scope": "catalog only; store quantities and store-specific prices are unverified",
        }
        self.storage.put(cache_key, result)
        return result

    @staticmethod
    def _product(doc):
        if not isinstance(doc, dict):
            raise ParseError("Discovery product is not an object")
        if not doc.get("pid") or not doc.get("title"):
            raise ParseError("Discovery product has no ID or title")
        return {
            "id": str(doc["pid"]),
            "name": doc["title"],
            "brand": doc.get("brand"),
            "category": doc.get("category_flat"),
            "price": doc.get("sale_price", doc.get("price")),
            "catalog_price": doc.get("price"),
            "original_price": None,
            "savings": None,
            "sku": None,
            "stock": {
                "text": "Not provided by this endpoint",
                "quantity": None,
                "quantity_is_lower_bound": False,
                "in_stock": None,
            },
            "url": doc.get("url"),
            "image": doc.get("thumb_image"),
            "description": doc.get("description"),
            "raw": doc,
        }

    def search(
        self,
        query="",
        *,
        category=None,
        fq="",
        page=1,
        rpp=24,
        sort="match",
        store=None,
        in_stock=None,
    ):
        if in_stock is not None and not isinstance(in_stock, bool):
            raise ValueError("in_stock must be boolean")
        if store is not None:
            from .store_api import product, merge, validate_store

            store = validate_store(self, store)
            if in_stock is not None and not isinstance(in_stock, bool):
                raise ValueError("in_stock must be boolean")
            if re.search(r"price|saving|discount", str(sort), re.I):
                raise ValueError(
                    "Store search cannot globally sort native prices using catalog candidates; complete a store scan and sort its local snapshot instead"
                )

            base = self.search(
                query, category=category, fq=fq, page=page, rpp=rpp, sort=sort
            )
            rows = [merge(p, product(self, p["id"], store)) for p in base["products"]]
            if in_stock is not False:
                rows = [p for p in rows if p["stock"]["in_stock"]]
            return {
                **base,
                "products": rows,
                "returned": len(rows),
                "candidate_returned": base["returned"],
                "candidate_total_results": base["total_results"],
                "candidate_sort": sort,
                "sort_scope": "global-catalog-candidates",
                "total_results": None,
                "store_id": str(store).zfill(3),
                "backend": "discovery+native-json",
                "inventory_scope": "Store-specific availability and prices; global candidate pagination; exact quantities unavailable",
            }
        if in_stock is True:
            raise ValueError("Select a store to filter local availability")
        if not isinstance(page, int) or page < 1 or (page - 1) * rpp > 10000:
            raise ValueError(
                "Direct backend offset must be between 0 and 10000; partition large scans by category"
            )
        if not isinstance(rpp, int) or not 1 <= rpp <= 200:
            raise ValueError("rpp must be between 1 and 200")
        # Accept the storefront category expression as a convenience; do not guess store fields.
        if fq.startswith("category:") and "," not in fq:
            m = re.fullmatch(r"category:[^|]+\|(\d+)", fq)
            if m:
                category = m[1]
                fq = ""
        return self._query(
            query, category=category, fq=fq, start=(page - 1) * rpp, rows=rpp, sort=sort
        )

    def product(self, url, *, store=None):
        value = str(url)
        m = re.search(r"^https://www\.microcenter\.com/product/(\d+)(?:/|$)", value)
        pid = m[1] if m else value if value.isdigit() else None
        if not pid:
            raise ValueError(
                "Supply a numeric product ID or canonical Micro Center product URL"
            )
        if store is not None:
            from .store_api import product

            item = product(self, pid, store)
            return {
                "source": item["source"],
                "observed_at": item["observed_at"],
                "backend": "native-json",
                "browser_used": False,
                "store_id": item["store_id"],
                "product": item,
                "products": [item],
                "returned": 1,
            }
        result = self._query("*", fq='pid:"' + pid + '"', rows=1)
        exact = [p for p in result["products"] if p["id"] == pid]
        if len(exact) != 1:
            raise MicroCenterError("Exact product ID was not found in the catalog")
        return {**result, "product": exact[0]}

    def categories(self, store=None):
        if store is not None:
            raise ValueError("Direct category facets are global, not store inventory")
        r = self._query("*", rows=1)
        fields = r["facets"].get("facets", [])
        cat = next((f for f in fields if f.get("name") == "category_flat"), {})
        return {k: v for k, v in r.items() if k not in ("products", "returned")} | {
            "categories": cat.get("value", []),
            "exhaustive": False,
        }

    def stores(self):
        data = json.loads((Path(__file__).parent / "stores.json").read_text())
        data["live"] = False
        data["note"] = "Store-ID directory snapshot; not inventory"
        return data

    def inventory(self, sku, *, stores=None):
        from .client import store_id
        from .store_api import product

        if not re.fullmatch(r"\d{1,8}", str(sku)):
            raise ValueError("Supply an exact numeric store SKU")
        directory = self.stores()["stores"]
        wanted = (
            {store_id(s) for s in stores} if stores else {s["id"] for s in directory}
        )
        if not wanted or not wanted.issubset({s["id"] for s in directory}):
            raise ValueError("Unknown store ID")
        first = sorted(wanted)[0]
        candidates = self.search(str(sku), rpp=24)["products"]
        pid = None
        for p in candidates:
            local = product(self, p["id"], first)
            if local["sku"].lstrip("0") == str(sku).lstrip("0"):
                pid = p["id"]
                break
        if pid is None:
            return {
                "sku": str(sku),
                "status": "not_listed",
                "stores": [],
                "note": "No exact SKU match; no zero-stock assumption",
            }
        rows = []
        for s in directory:
            if s["id"] in wanted:
                rows.append({"store": s, "product": product(self, pid, s["id"])})
        return {
            "sku": str(sku),
            "product_id": pid,
            "backend": "native-json",
            "browser_used": False,
            "stores": rows,
            "quantity_provided": False,
        }

    def compare(self, skus, *, store=None):
        if not 1 <= len(skus) <= 4:
            raise ValueError("Compare one to four exact store SKUs")
        store = "029" if store is None else store
        rows = []
        for sku in skus:
            result = self.inventory(sku, stores=[store])
            rows.append(
                result["stores"][0]["product"]
                if result["stores"]
                else {"sku": str(sku), "status": "not_listed"}
            )
        return {
            "products": rows,
            "backend": "native-json",
            "browser_used": False,
            "quantity_provided": False,
        }

    def suggest(self, *args, **kwargs):
        raise ValueError(
            "Direct autocomplete is not yet verified; use --storefront explicitly"
        )

    def nearby(self, *args, **kwargs):
        raise ValueError(
            "Direct nearby-store lookup is not yet verified; use --storefront explicitly"
        )

    def scan(
        self,
        *,
        store=None,
        query="",
        fq="",
        category=None,
        in_stock=None,
        checkpoint=None,
        max_pages=1000,
        progress=None,
    ):
        if store is not None:
            from .store_api import scan

            return scan(
                self,
                store=store,
                query=query,
                fq=fq,
                category=category,
                in_stock=in_stock,
                checkpoint=checkpoint,
                max_pages=max_pages,
                progress=progress,
            )
        if in_stock is True:
            raise ValueError("Select a store to filter local availability")
        signature = {
            "backend": "discovery",
            "query": query or "*",
            "fq": fq,
            "category": category,
            "rows": 200,
            "sort": "pid asc",
        }
        state = {
            "signature": signature,
            "started_at": utcnow(),
            "products": [],
            "pages": [],
            "next_page": 1,
            "complete": False,
            "warnings": [],
        }
        if checkpoint and Path(checkpoint).exists():
            state = json.loads(Path(checkpoint).read_text())
            if state.get("signature") != signature:
                raise ValueError("Checkpoint belongs to another query/backend")
            if state["complete"]:
                return state
        if checkpoint:
            write_json(checkpoint, state)
        seen = {p["id"] for p in state["products"]}
        for page in range(state["next_page"], max_pages + 1):
            result = self.search(
                query, category=category, fq=fq, page=page, rpp=200, sort="pid asc"
            )
            if page == 1 and result["total_results"] > 10200:
                raise MicroCenterError(
                    "Catalog exceeds the backend offset limit. Narrow this scan by category; no truncated success will be reported."
                )
            fresh = []
            for p in result["products"]:
                if p["id"] not in seen:
                    seen.add(p["id"])
                    fresh.append(p)
            if result["products"] and not fresh:
                raise ParseError("Repeated Discovery page; checkpoint retained")
            state["products"].extend(fresh)
            state["pages"].append(
                {
                    "page": page,
                    "start": result["start"],
                    "returned": result["returned"],
                    "observed_at": result["observed_at"],
                    "response_bytes": result["response_bytes"],
                    "cache_hit": result["cache_hit"],
                }
            )
            state.update(
                returned=len(seen),
                total_results=result["total_results"],
                updated_at=utcnow(),
                next_page=page + 1,
            )
            terminal = result["start"] + result["returned"] >= result["total_results"]
            if result["returned"] < 200 and not terminal:
                raise ParseError(
                    "Short page contradicts advertised total; checkpoint retained"
                )
            if terminal:
                if len(seen) != result["total_results"]:
                    raise ParseError(
                        "Unique count differs from total; refusing to label incomplete scan complete"
                    )
                state.update(
                    complete=True,
                    finished_at=utcnow(),
                    inventory_scope="global catalog; local inventory not verified",
                )
            if checkpoint:
                write_json(checkpoint, state)
            if progress:
                progress(state)
            if state["complete"]:
                return state
        raise MicroCenterError("Page cap reached; checkpoint retained")
