"""Bounded, streaming Apify adapter over the existing read-only JSON client."""

import asyncio
import os
import re
from pathlib import Path

from .discovery import DiscoveryClient as Client
from .errors import ParseError, MicroCenterError
from .store_api import merge, validate_store

DATASET_EVENT = "apify-default-dataset-item"


def validate_input(data):
    if not isinstance(data, dict):
        raise ValueError("Actor input must be an object")
    allowed = {
        "mode",
        "query",
        "categoryId",
        "productIds",
        "storeIds",
        "maxProducts",
        "maxResults",
        "includeOutOfStock",
        "includeRaw",
        "startPage",
    }
    if set(data) - allowed:
        raise ValueError(
            "Unknown input fields: " + ", ".join(sorted(set(data) - allowed))
        )
    value = {
        "mode": "search",
        "query": "filament",
        "storeIds": ["195"],
        "maxProducts": 50,
        "maxResults": 200,
        "includeOutOfStock": True,
        "includeRaw": False,
        "startPage": 1,
        **data,
    }
    if value["mode"] not in ("search", "category", "product"):
        raise ValueError("mode must be search, category or product")
    for key, limit in [("maxProducts", 1000), ("maxResults", 4000), ("startPage", 51)]:
        if type(value[key]) is not int or not 1 <= value[key] <= limit:
            raise ValueError(f"{key} must be an integer from1 to{limit}")
    for key in ("includeRaw", "includeOutOfStock"):
        if type(value[key]) is not bool:
            raise ValueError(key + " must be boolean")
    stores = value["storeIds"]
    if not isinstance(stores, list) or not 1 <= len(stores) <= 4:
        raise ValueError("Select1–4 store IDs")
    if any(not isinstance(s, str) or not re.fullmatch(r"\d{1,3}", s) for s in stores):
        raise ValueError("Store IDs must be numeric strings")
    value["storeIds"] = list(dict.fromkeys(s.zfill(3) for s in stores))
    if value["mode"] == "product":
        ids = value.get("productIds")
        if not isinstance(ids, list) or not ids or len(ids) > 1000:
            raise ValueError("product mode requires1–1000 productIds")
        if any(not isinstance(p, str) or not re.fullmatch(r"\d{1,10}", p) for p in ids):
            raise ValueError("productIds must be numeric strings, not URLs or SKUs")
        value["productIds"] = list(dict.fromkeys(ids))
    elif value["mode"] == "category":
        if not isinstance(value.get("categoryId"), str) or not re.fullmatch(
            r"\d{1,12}", value["categoryId"]
        ):
            raise ValueError("category mode requires a numeric categoryId string")
    elif (
        not isinstance(value["query"], str)
        or not value["query"].strip()
        or len(value["query"]) > 200
    ):
        raise ValueError("query must contain1–200 characters")
    return value


def candidates(client, cfg, state):
    seen = set()
    if cfg["mode"] == "product":
        ids = cfg["productIds"]
        for pid in ids[: cfg["maxProducts"]]:
            yield {"id": pid}
        state["catalog_complete"] = len(ids) <= cfg["maxProducts"]
        return
    page = cfg["startPage"]
    while True:
        result = client.search(
            query=cfg["query"] if cfg["mode"] == "search" else "",
            category=cfg.get("categoryId") if cfg["mode"] == "category" else None,
            page=page,
            rpp=200,
            sort="pid asc",
        )
        state["candidate_total"] = result["total_results"]
        page_seen = set()
        fresh = []
        for p in result["products"]:
            if p["id"] not in seen and p["id"] not in page_seen:
                page_seen.add(p["id"])
                fresh.append(p)
        if result["products"] and not fresh:
            raise ParseError("Repeated catalog page; no truncated success reported")
        for p in fresh:
            if len(seen) >= cfg["maxProducts"]:
                state["stop_reason"] = "maxProducts"
                return
            seen.add(p["id"])
            yield p
        terminal = result["start"] + result["returned"] >= result["total_results"]
        if terminal:
            if cfg["startPage"] == 1 and len(seen) != result["total_results"]:
                raise ParseError("Unique catalog count differs from advertised total")
            state["catalog_complete"] = (
                cfg["startPage"] == 1 and len(seen) == result["total_results"]
            )
            return
        if result["returned"] < 200:
            raise ParseError("Short catalog page contradicts advertised total")
        page += 1
        if (page - 1) * 200 > 10000:
            state["stop_reason"] = "catalog_offset_limit"
            return


async def run(actor, *, client_factory=Client):
    supplied = await actor.get_input()
    cfg = validate_input({} if supplied is None else supplied)
    # A migrated/resurrected process may retain already charged dataset rows.
    # Refuse replay rather than silently appending and charging the same work.
    dataset = await actor.open_dataset()
    existing = await dataset.get_data(limit=1)
    if existing.items:
        raise MicroCenterError(
            "This run already contains dataset observations; restarting is refused to prevent duplicate charges. Start a new run for a new observation window."
        )
    state = {
        "complete": False,
        "catalog_complete": False,
        "candidate_total": None,
        "products_checked": 0,
        "store_observations_checked": 0,
        "results_saved": 0,
        "stores": cfg["storeIds"],
        "backend": "native-json",
        "browser_used": False,
        "quantity_provided": False,
        "stop_reason": None,
    }
    await actor.set_value("SUMMARY", state)
    cache = Path(
        os.environ.get(
            "MICROCENTER_CACHE_DIR",
            str(
                Path(os.environ.get("APIFY_LOCAL_STORAGE_DIR", "storage"))
                / "microcenter-cache"
            ),
        )
    )
    client = client_factory(cache_dir=cache, cache_ttl=300, delay=4, jitter=1)
    try:
        for sid in cfg["storeIds"]:
            validate_store(client, sid)
        iterator = candidates(client, cfg, state)
        manager = actor.get_charging_manager()
        while True:
            if manager.is_event_charge_limit_reached(DATASET_EVENT):
                state["stop_reason"] = "charge_limit"
                break
            if state["results_saved"] >= cfg["maxResults"]:
                state["stop_reason"] = "maxResults"
                break
            candidate = await asyncio.to_thread(next, iterator, None)
            if candidate is None:
                state["complete"] = state["catalog_complete"]
                if not state["stop_reason"]:
                    state["stop_reason"] = (
                        "exhausted" if state["complete"] else "candidate_window"
                    )
                break
            state["products_checked"] += 1
            for sid in cfg["storeIds"]:
                if (
                    manager.is_event_charge_limit_reached(DATASET_EVENT)
                    or state["results_saved"] >= cfg["maxResults"]
                ):
                    state["stop_reason"] = (
                        "charge_limit"
                        if manager.is_event_charge_limit_reached(DATASET_EVENT)
                        else "maxResults"
                    )
                    break
                local = (
                    await asyncio.to_thread(client.product, candidate["id"], store=sid)
                )["product"]
                row = merge(candidate, local)
                if not row.get("url"):
                    row["url"] = (
                        f"https://www.microcenter.com/product/{row['id']}/?storeid={sid}"
                    )
                state["store_observations_checked"] += 1
                if cfg["includeOutOfStock"] or row["stock"]["in_stock"]:
                    if not cfg["includeRaw"]:
                        row = {
                            k: v
                            for k, v in row.items()
                            if k not in ("raw", "catalog_raw")
                        }
                    await actor.push_data(row)
                    state["results_saved"] += 1
                await actor.set_value("SUMMARY", dict(state))
            if state["stop_reason"] in ("charge_limit", "maxResults"):
                break
        # A result/charge cap reached exactly on the final requested observation
        # does not make an otherwise exhaustive window incomplete.
        expected = (
            len(cfg["productIds"])
            if cfg["mode"] == "product"
            else state["candidate_total"]
        )
        if (
            expected is not None
            and (cfg["mode"] == "product" or cfg["startPage"] == 1)
            and expected <= cfg["maxProducts"]
            and state["products_checked"] == expected
            and state["store_observations_checked"] == expected * len(cfg["storeIds"])
        ):
            state.update(complete=True, catalog_complete=True, stop_reason="exhausted")
        await actor.set_status_message(
            f"Saved {state['results_saved']} observations; {state['stop_reason']}"
        )
        return state
    except Exception:
        state["stop_reason"] = "error"
        raise
    finally:
        await actor.set_value("SUMMARY", dict(state))
        client.close()


def main():
    from apify import Actor

    async def entry():
        async with Actor:
            await run(Actor)

    asyncio.run(entry())


if __name__ == "__main__":
    main()
