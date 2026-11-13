"""Public catalog client with caching, pacing, exact identity checks and resumable scans."""

import copy, json, os, re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode, urlsplit
from . import parsers
from .errors import ParseError, MicroCenterError
from .storage import Storage
from .transport import BrowserTransport, CDPTransport


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def cache_home():
    return Path(
        os.environ.get(
            "MICROCENTER_CACHE_DIR", Path.home() / ".cache" / "microcenter-api"
        )
    )


def store_id(value):
    if value is None:
        value = "029"
    s = str(value)
    if not s.isdigit() or not 1 <= len(s) <= 3:
        raise ValueError("store must be a one-to-three digit store ID")
    return s.zfill(3)


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(value, indent=2) + "\n")
    temp.replace(path)


class Client:
    def __init__(
        self,
        *,
        cdp_url=None,
        headed=False,
        delay=4.0,
        jitter=1.0,
        cache_ttl=300,
        cache_dir=None,
        transport=None,
    ):
        self.transport = transport or (
            CDPTransport(cdp_url=cdp_url)
            if cdp_url
            else BrowserTransport(headed=headed)
        )
        self.storage = Storage(
            Path(cache_dir or cache_home()) / "cache.sqlite", delay=delay, jitter=jitter
        )
        self.transport.before_request = self.storage.wait
        self.cache_ttl = max(0, float(cache_ttl))
        self.metrics = {"network_requests": 0, "cache_hits": 0, "response_bytes": 0}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def close(self):
        self.transport.close()

    def _request(self, path, params, parser, form=None):
        # Public read-only allowlist. No cart/account/checkout or arbitrary URLs.
        allowed = {
            "/endeca/AjaxResults.aspx",
            "/assets/ajax/StoreChange.aspx",
            "/assets/ajax/storeZipCode.aspx",
            "/assets/ajax/autosuggest.aspx",
            "/search/search_results.aspx",
        }
        if path not in allowed and not re.fullmatch(
            r"/(?:product|quickView)/\d+/[^/?#\\]+", path
        ):
            raise ValueError("Unsupported public read endpoint")
        if any(x in path.lower() for x in ("..", "%2e", "%2f", "%5c")):
            raise ValueError("Encoded/traversal product paths are not supported")
        url = (
            parsers.ORIGIN
            + path
            + "?"
            + urlencode({k: v for k, v in params.items() if v not in (None, "")})
        )
        key = self.storage.key({"url": url, "form": form})
        cached = self.storage.get(key, self.cache_ttl)
        if cached is not None:
            self.metrics["cache_hits"] += 1
            cached["cache_hit"] = True
            return cached
        html = self.transport.fetch(url, form=form)
        self.metrics["network_requests"] += 1
        self.metrics["response_bytes"] += len(html.encode())
        parsed = parser(html)
        data = {
            "source": url,
            "observed_at": utcnow(),
            "anonymous": True,
            "cache_hit": False,
            **parsed,
        }
        self.storage.put(key, data)
        return data

    def stores(self):
        return self._request("/assets/ajax/StoreChange.aspx", {}, parsers.parse_stores)

    def categories(self, store="029"):
        return self._request(
            "/search/search_results.aspx",
            {"storeid": store_id(store), "rpp": 24},
            parsers.parse_categories,
        )

    def search(
        self,
        query="",
        *,
        store="029",
        fq="",
        category=None,
        in_stock=True,
        page=1,
        rpp=24,
        sort="match",
    ):
        if category:
            fq = "category:Category|" + str(category)
        if in_stock is None:
            in_stock = True
        store = store_id(store)
        if not isinstance(page, int) or not 1 <= page <= 10000:
            raise ValueError("page must be between 1 and 10000")
        if rpp not in (24, 48, 96):
            raise ValueError("rpp must be 24, 48, or 96")
        if not isinstance(in_stock, bool):
            raise ValueError("in_stock must be boolean")
        params = {
            "storeid": store,
            "Ntt": query,
            "fq": fq,
            "myStore": str(in_stock).lower(),
            "rpp": rpp,
            "page": page,
            "sortby": sort,
        }
        data = self._request(
            "/endeca/AjaxResults.aspx", params, lambda h: parsers.parse_search(h, store)
        )
        return {
            **data,
            "store_id": store,
            "page": page,
            "rpp": rpp,
            "query": query,
            "fq": fq,
            "in_stock_only": in_stock,
        }

    def product(self, url, *, store="029"):
        u = urlsplit(url)
        if (
            u.scheme != "https"
            or u.netloc != "www.microcenter.com"
            or not re.fullmatch(r"/(?:product|quickView)/\d+/[^/?#\\]+", u.path)
        ):
            raise ValueError(
                "Use a full canonical Micro Center product URL from search"
            )
        store = store_id(store)
        return self._request(
            u.path, {"storeid": store}, lambda h: parsers.parse_product(h, store)
        )

    def suggest(self, query):
        if not 2 <= len(query) <= 200:
            raise ValueError("query must contain 2–200 characters")
        return self._request(
            "/assets/ajax/autosuggest.aspx",
            {},
            parsers.parse_links,
            {"term": query, "N": ""},
        )

    def nearby(self, zip_code):
        if not re.fullmatch(r"\d{5}", str(zip_code)):
            raise ValueError("zip must contain five digits")
        return self._request(
            "/assets/ajax/storeZipCode.aspx",
            {},
            parsers.parse_links,
            {"zip": zip_code, "url": parsers.ORIGIN + "/"},
        )

    def inventory(self, sku, *, stores=None):
        if not re.fullmatch(r"\d{1,8}", str(sku)):
            raise ValueError("sku must be an exact numeric store SKU")
        wanted = {store_id(x) for x in stores} if stores else None
        destinations = [
            s for s in self.stores()["stores"] if wanted is None or s["id"] in wanted
        ]
        if not destinations or (wanted and wanted != {s["id"] for s in destinations}):
            raise ValueError("Unknown store ID in requested destinations")
        rows = []
        for s in destinations:
            d = self.search(str(sku), store=s["id"], in_stock=False)
            matches = [
                p for p in d["products"] if p["sku"].lstrip("0") == str(sku).lstrip("0")
            ]
            rows.append(
                {
                    "store": s,
                    "observed_at": d["observed_at"],
                    "status": "found" if matches else "not_listed",
                    "products": matches,
                }
            )
        return {
            "sku": str(sku),
            "stores": rows,
            "note": "not_listed does not establish zero stock; only exact SKU matches are returned",
        }

    def compare(self, skus, *, store="029"):
        if not 1 <= len(skus) <= 4:
            raise ValueError("Compare one to four exact SKUs")
        rows = []
        for sku in skus:
            if not re.fullmatch(r"\d{1,8}", str(sku)):
                raise ValueError("Invalid store SKU")
            d = self.search(str(sku), store=store, in_stock=False)
            matches = [
                p for p in d["products"] if p["sku"].lstrip("0") == str(sku).lstrip("0")
            ]
            rows.append(
                self.product(matches[0]["url"], store=store)
                if matches
                else {"sku": str(sku), "status": "not_listed"}
            )
        return {"products": rows}

    def scan(
        self,
        *,
        store="195",
        query="",
        fq="",
        in_stock=True,
        checkpoint=None,
        max_pages=1000,
        progress=None,
    ):
        if max_pages < 1:
            raise ValueError("max_pages must be positive")
        # The storefront treats a blank query as empty, not "all products".
        if not query and not fq:
            query = "*"
        signature = {
            "store": store_id(store),
            "query": query,
            "fq": fq,
            "in_stock": in_stock,
            "rpp": 96,
            "sort": "match",
        }
        state = {
            "signature": signature,
            "started_at": utcnow(),
            "pages": [],
            "products": [],
            "complete": False,
            "next_page": 1,
            "warnings": [],
        }
        if checkpoint and Path(checkpoint).exists():
            state = json.loads(Path(checkpoint).read_text())
            if state.get("signature") != signature:
                raise ValueError("Checkpoint belongs to a different store/query/filter")
            if state.get("complete"):
                return state
        seen = {p["id"] for p in state["products"]}
        last_saved = copy.deepcopy(state)
        try:
            for page in range(state["next_page"], max_pages + 1):
                d = self.search(
                    query,
                    store=signature["store"],
                    fq=fq,
                    in_stock=in_stock,
                    page=page,
                    rpp=96,
                )
                fresh = []
                page_ids = set()
                for p in d["products"]:
                    if p["id"] not in seen and p["id"] not in page_ids:
                        fresh.append(p)
                        page_ids.add(p["id"])
                if d["products"] and not fresh:
                    raise ParseError(
                        "Repeated page: refusing to silently truncate scan"
                    )
                if len(fresh) < d["returned"]:
                    state["warnings"].append(
                        f"Page {page}: {d['returned'] - len(fresh)} duplicate IDs during changing inventory"
                    )
                for p in fresh:
                    seen.add(p["id"])
                    state["products"].append(p)
                state["pages"].append(
                    {
                        "page": page,
                        "returned": d["returned"],
                        "observed_at": d["observed_at"],
                        "cache_hit": d["cache_hit"],
                        "response_bytes": d["response_bytes"],
                    }
                )
                state.update(
                    next_page=page + 1,
                    updated_at=utcnow(),
                    advertised_in_stock=d["total_in_stock"],
                    returned=len(state["products"]),
                )
                if d["returned"] < 96:
                    if (
                        in_stock
                        and d["total_in_stock"] is not None
                        and len(seen) != d["total_in_stock"]
                    ):
                        # Keep the previous checkpoint so this page can be retried.
                        state["next_page"] = page
                        raise ParseError(
                            "Short page contradicts advertised total; scan remains incomplete"
                        )
                    state["complete"] = True
                    state["finished_at"] = utcnow()
                    if (
                        in_stock
                        and d["total_in_stock"] is not None
                        and len(seen) != d["total_in_stock"]
                    ):
                        state["warnings"].append(
                            "Unique count differs from current advertised stock; inventory may have changed during scan"
                        )
                if checkpoint:
                    write_json(checkpoint, state)
                last_saved = copy.deepcopy(state)
                if progress:
                    progress(state)
                if state["complete"]:
                    return state
            raise MicroCenterError(
                "Page cap reached; checkpoint retained. Raise --max-pages to resume."
            )
        except BaseException:
            if checkpoint:
                write_json(checkpoint, last_saved)
            raise
