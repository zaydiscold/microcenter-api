"""Micro Center's native read-only JSON product attributes endpoint."""

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from decimal import Decimal, InvalidOperation
from pathlib import Path
from .client import store_id, utcnow, write_json
from .errors import BlockedError, MicroCenterError, ParseError, RateLimitedError

ENDPOINT = "https://www.microcenter.com/assets/ajax/getProductAttributes.aspx"


def validate_store(client, value):
    store = store_id(value)
    if store not in {s["id"] for s in client.stores()["stores"]}:
        raise ValueError("Unknown store ID")
    return store


def http_attributes(url, form):
    req = urllib.request.Request(
        url,
        data=urllib.parse.urlencode(form).encode(),
        headers={
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
            "X-Requested-With": "XMLHttpRequest",
            "User-Agent": "microcenter-api-cli/0.3.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            if urllib.parse.urlsplit(r.url).netloc != "www.microcenter.com":
                raise MicroCenterError("Unexpected native API redirect")
            if "application/json" not in r.headers.get("Content-Type", ""):
                raise ParseError("Native product API did not return JSON")
            return r.read()
    except urllib.error.HTTPError as e:
        if e.code == 429:
            raise RateLimitedError(e.headers.get("Retry-After")) from e
        if e.code in (401, 403):
            try:
                sample = e.read(32768).decode("utf-8", errors="replace").lower()
            except (OSError, TimeoutError):
                sample = ""
            challenged = e.headers.get(
                "cf-mitigated", ""
            ).lower() == "challenge" or any(
                token in sample
                for token in ("challenge-platform", "cf-chl-", "just a moment")
            )
            description = (
                "challenge detected" if challenged else "challenge not established"
            )
            raise BlockedError(
                f"Native product API returned HTTP {e.code} ({description}); stopping without a browser fallback",
                status=e.code,
                challenge_detected=challenged,
            ) from e
        raise MicroCenterError(f"Native product API returned HTTP {e.code}") from e
    except (urllib.error.URLError, TimeoutError) as e:
        raise MicroCenterError(
            "Native product API request failed; no automatic retry"
        ) from e


def boolean(value):
    if value is True or value == "True":
        return True
    if value is False or value == "False":
        return False
    raise ParseError("Native API omitted a valid stock/eligibility flag")


def money(value):
    if value in (None, ""):
        return None
    try:
        n = Decimal(str(value))
        if not n.is_finite() or n < 0:
            raise InvalidOperation
        return float(n)
    except (InvalidOperation, ValueError):
        raise ParseError("Native API returned an invalid price")


def product(client, pid, store):
    pid = str(pid)
    store = validate_store(client, store)
    if not re.fullmatch(r"\d{1,10}", pid):
        raise ValueError("Supply a numeric product ID")
    url = ENDPOINT + "?" + urllib.parse.urlencode({"storeid": store})
    form = {"type": "product", "product_id": pid}
    key = client.storage.key({"backend": "native-json", "url": url, "form": form})
    cached = client.storage.get(key, client.cache_ttl)
    if cached is not None:
        client.metrics["cache_hits"] += 1
        cached["cache_hit"] = True
        return cached
    client.storage.wait()
    raw = client.store_fetch(url, form)
    client.metrics["network_requests"] += 1
    client.metrics["response_bytes"] += len(raw)
    try:
        d = json.loads(raw)
    except (ValueError, TypeError) as e:
        raise ParseError("Native API returned invalid JSON") from e
    if not isinstance(d, dict):
        raise ParseError("Native API returned a non-object envelope")
    if not d.get("product_id"):
        raise MicroCenterError(
            "Product was not listed by the native API; no inventory assumption made"
        )
    if str(d["product_id"]) != pid:
        raise ParseError("Native API product identity did not match the request")
    sku = str(d.get("short_sku", ""))
    if not sku.isdigit():
        raise ParseError("Native API returned no valid store SKU")
    if not isinstance(d.get("title"), str) or not d["title"].strip():
        raise ParseError("Native API returned no valid product title")
    available = boolean(d.get("in_stock"))
    price = money(d.get("price"))
    original = money(d.get("original_price"))
    row = {
        "id": pid,
        "sku": sku,
        "name": d.get("title"),
        "brand": d.get("brand"),
        "category": d.get("category_1"),
        "price": price,
        "original_price": original,
        "savings": round(original - price, 2)
        if original is not None and price is not None
        else None,
        "store_id": store,
        "stock": {
            "text": "In stock" if available else "Out of stock",
            "in_stock": available,
            "quantity": None,
            "quantity_is_lower_bound": False,
            "quantity_provided": False,
        },
        "can_pickup": boolean(d.get("can_pickup")),
        "can_ship": boolean(d.get("can_ship")),
        "upc": d.get("upc"),
        "manufacturer_number": d.get("manufacturer_number"),
        "source": url,
        "observed_at": utcnow(),
        "backend": "native-json",
        "browser_used": False,
        "cache_hit": False,
        "raw": d,
    }
    client.storage.put(key, row)
    return row


def merge(catalog, local):
    link = catalog.get("url")
    if link:
        parts = urllib.parse.urlsplit(link)
        if parts.scheme != "https" or parts.netloc != "www.microcenter.com":
            raise ParseError("Catalog product link is not a Micro Center URL")
        query = [
            (k, v)
            for k, v in urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
            if k.lower() != "storeid"
        ]
        query.append(("storeid", local["store_id"]))
        link = urllib.parse.urlunsplit(
            (
                parts.scheme,
                parts.netloc,
                parts.path,
                urllib.parse.urlencode(query),
                parts.fragment,
            )
        )
    return {
        **catalog,
        **local,
        "catalog_price": catalog.get("price"),
        "url": link,
        "image": catalog.get("image"),
        "catalog_observed_at": catalog.get("observed_at"),
        "catalog_raw": catalog.get("raw"),
    }


def scan(
    client,
    *,
    store,
    query="",
    fq="",
    category=None,
    in_stock=None,
    checkpoint=None,
    max_pages=1000,
    progress=None,
):
    store = validate_store(client, store)
    in_stock = True if in_stock is None else in_stock
    if not isinstance(in_stock, bool):
        raise ValueError("in_stock must be boolean")
    signature = {
        "backend": "native-json",
        "store": store,
        "query": query or "*",
        "fq": fq,
        "category": category,
        "in_stock_only": in_stock,
    }
    state = {
        "signature": signature,
        "started_at": utcnow(),
        "complete": False,
        "checked_ids": [],
        "products": [],
        "observations": [],
        "warnings": [],
        "pages": [],
        "returned": 0,
        "checked": 0,
    }
    item_dir = Path(str(checkpoint) + ".items") if checkpoint else None

    def persist():
        if checkpoint:
            write_json(
                checkpoint,
                {
                    k: v
                    for k, v in state.items()
                    if k not in ("products", "observations")
                },
            )

    if checkpoint and Path(checkpoint).exists():
        state = json.loads(Path(checkpoint).read_text())
        if state.get("signature") != signature:
            raise ValueError("Store checkpoint belongs to another query/store")
        ids = state.get("checked_ids", [])
        if len(set(ids)) != len(ids) or any(
            not re.fullmatch(r"\d{1,10}", str(pid)) for pid in ids
        ):
            raise ParseError("Invalid store checkpoint IDs")
        observations = []
        for pid in ids:
            item = json.loads((item_dir / (pid + ".json")).read_text())
            if item.get("id") != pid or item.get("store_id") != store:
                raise ParseError("Checkpoint item identity or store mismatch")
            observations.append(item)
        state["observations"] = observations
        state["products"] = [
            x for x in observations if not in_stock or x["stock"]["in_stock"]
        ]
        if state["complete"]:
            return state
    catalog = client.scan(
        query=query,
        fq=fq,
        category=category,
        in_stock=None,
        checkpoint=str(checkpoint) + ".catalog.json" if checkpoint else None,
        max_pages=max_pages,
    )
    state.update(
        candidate_total=catalog["returned"],
        catalog_started_at=catalog["started_at"],
        catalog_finished_at=catalog["finished_at"],
    )
    checked = set(state["checked_ids"])
    if not checked.issubset({p["id"] for p in catalog["products"]}):
        raise ParseError("Checkpoint contains IDs outside its catalog")
    persist()
    for candidate in catalog["products"]:
        if candidate["id"] in checked:
            continue
        local = product(client, candidate["id"], store)
        item = merge(candidate, local)
        # Write each observation once; the small manifest is updated atomically.
        if item_dir:
            write_json(item_dir / (item["id"] + ".json"), item)
        state["observations"].append(item)
        state["checked_ids"].append(item["id"])
        checked.add(item["id"])
        if not in_stock or item["stock"]["in_stock"]:
            state["products"].append(item)
        state.update(
            checked=len(checked),
            returned=len(state["products"]),
            updated_at=utcnow(),
            in_stock_count=sum(p["stock"]["in_stock"] for p in state["observations"]),
            out_of_stock_count=sum(
                not p["stock"]["in_stock"] for p in state["observations"]
            ),
        )
        persist()
        if progress:
            progress(state)
    state.update(
        complete=len(checked) == state["candidate_total"],
        finished_at=utcnow(),
        store_id=store,
        backend="native-json",
        browser_used=False,
        quantity_provided=False,
        inventory_scope="Store-specific availability flags and current prices; exact quantities are not returned",
    )
    persist()
    return state
