import json
from urllib.parse import urlsplit, parse_qs
import pytest
from microcenter_api import Client, ParseError
from microcenter_api.errors import RateLimitedError


def native(pid="660548", available="True", sku="518159", price="10.99"):
    return json.dumps(
        {
            "product_id": pid,
            "short_sku": sku,
            "title": "Synthetic matte filament",
            "brand": "Example",
            "category_1": "Filaments & Resins|754",
            "price": price,
            "original_price": "19.99",
            "in_stock": available,
            "can_pickup": "True",
            "can_ship": "True",
        }
    ).encode()


def catalog(ids, start=0):
    return json.dumps(
        {
            "response": {
                "numFound": len(ids),
                "start": start,
                "docs": [
                    {
                        "pid": str(i),
                        "title": "Example filament",
                        "price": 36.99,
                        "sale_price": 36.99,
                        "url": f"https://www.microcenter.com/product/{i}/example",
                    }
                    for i in ids
                ],
            },
            "facet_counts": {},
        }
    ).encode()


def test_store_json_honors_store_and_keeps_quantity_unknown(tmp_path):
    calls = []

    def fetch(url, form):
        store = parse_qs(urlsplit(url).query)["storeid"][0]
        calls.append((store, form))
        assert form == {"type": "product", "product_id": "660548"}
        return native(available="False" if store == "185" else "True")

    c = Client(cache_dir=tmp_path, store_fetch=fetch)
    c.storage.wait = lambda: None
    miami = c.product("660548", store="185")["product"]
    sc = c.product("660548", store="195")["product"]
    assert miami["stock"]["in_stock"] is False and sc["stock"]["in_stock"] is True
    assert (
        sc["price"] == 10.99 and sc["original_price"] == 19.99 and sc["savings"] == 9.0
    )
    assert sc["stock"]["quantity"] is None and not sc["stock"]["quantity_provided"]
    assert sc["browser_used"] is False and len(calls) == 2
    assert (
        c.product("660548", store="195")["product"]["cache_hit"] is True
        and len(calls) == 2
    )


@pytest.mark.parametrize(
    "payload", [b"[]", b"{}", native(pid="999"), native(available="unknown")]
)
def test_invalid_native_data_fails_closed(tmp_path, payload):
    from microcenter_api.errors import MicroCenterError

    c = Client(cache_dir=tmp_path, store_fetch=lambda *_: payload)
    c.storage.wait = lambda: None
    with pytest.raises(MicroCenterError):
        c.product("660548", store="195")


def test_store_search_uses_native_prices_and_candidate_pagination(tmp_path):
    c = Client(
        cache_dir=tmp_path,
        fetch=lambda _: catalog([1, 2]),
        store_fetch=lambda u, f: native(
            pid=f["product_id"],
            available="False" if f["product_id"] == "2" else "True",
            price="31.96",
        ),
    )
    c.storage.wait = lambda: None
    r = c.search(category="754", store="195")
    assert (
        r["candidate_returned"] == 2
        and r["candidate_total_results"] == 2
        and r["total_results"] is None
    )
    assert (
        r["returned"] == 1
        and r["products"][0]["price"] == 31.96
        and r["products"][0]["catalog_price"] == 36.99
    )


def test_store_scan_resumes_item_checkpoints(tmp_path):
    calls = []

    def first(u, f):
        pid = f["product_id"]
        calls.append(pid)
        if pid == "2":
            raise RateLimitedError("60")
        return native(pid=pid)

    checkpoint = tmp_path / "scan.json"
    c = Client(
        cache_dir=tmp_path / "cache",
        fetch=lambda _: catalog([1, 2, 3]),
        store_fetch=first,
    )
    c.storage.wait = lambda: None
    with pytest.raises(RateLimitedError):
        c.scan(category="754", store="195", checkpoint=checkpoint)
    manifest = json.loads(checkpoint.read_text())
    assert manifest["checked_ids"] == ["1"] and not manifest["complete"]
    assert "observations" not in manifest and "products" not in manifest
    c2 = Client(
        cache_dir=tmp_path / "cache",
        fetch=lambda _: pytest.fail("catalog should resume from checkpoint"),
        store_fetch=lambda u, f: (
            calls.append(f["product_id"])
            or native(
                pid=f["product_id"],
                available="False" if f["product_id"] == "2" else "True",
            )
        ),
    )
    c2.storage.wait = lambda: None
    r = c2.scan(category="754", store="195", checkpoint=checkpoint)
    assert r["complete"] and r["checked"] == 3 and r["returned"] == 2
    assert (
        calls == ["1", "2", "2", "3"]
        and r["out_of_stock_count"] == 1
        and not r["browser_used"]
    )
    assert c2.scan(category="754", store="195", checkpoint=checkpoint)["returned"] == 2


def test_store_inventory_checks_exact_sku(tmp_path):
    c = Client(
        cache_dir=tmp_path,
        fetch=lambda _: catalog([660548]),
        store_fetch=lambda u, f: native(
            available="False" if "storeid=185" in u else "True"
        ),
    )
    c.storage.wait = lambda: None
    r = c.inventory("518159", stores=["185", "195"])
    assert r["browser_used"] is False and len(r["stores"]) == 2
    assert {
        s["store"]["id"]: s["product"]["stock"]["in_stock"] for s in r["stores"]
    } == {"185": False, "195": True}
    assert c.inventory("999999", stores=["195"])["status"] == "not_listed"


@pytest.mark.parametrize("operation", ["search", "scan"])
def test_unknown_store_rejected_before_catalog_calls(tmp_path, operation):
    c = Client(
        cache_dir=tmp_path,
        fetch=lambda _: pytest.fail(
            "invalid store must fail before any catalog request"
        ),
    )
    with pytest.raises(ValueError):
        getattr(c, operation)(store="999")


def test_store_price_sort_cannot_use_stale_catalog_order(tmp_path):
    c = Client(
        cache_dir=tmp_path,
        fetch=lambda _: pytest.fail("price sort should fail before network"),
    )
    with pytest.raises(ValueError):
        c.search(store="195", sort="pricelow")


def test_store_merge_links_keep_selected_store_and_slug():
    from microcenter_api.store_api import merge

    r = merge(
        {
            "id": "1",
            "url": "https://www.microcenter.com/product/1/example?storeID=029&x=1#specs",
            "price": 10,
        },
        {"id": "1", "store_id": "195", "price": 9},
    )
    u = urlsplit(r["url"])
    q = parse_qs(u.query)
    assert (
        u.path == "/product/1/example"
        and u.fragment == "specs"
        and q == {"x": ["1"], "storeid": ["195"]}
    )


def test_missing_native_title_cannot_poison_snapshot(tmp_path):
    data = json.loads(native())
    data["title"] = None
    c = Client(cache_dir=tmp_path, store_fetch=lambda *_: json.dumps(data).encode())
    c.storage.wait = lambda: None
    with pytest.raises(ParseError):
        c.product("660548", store="195")


def test_store_scan_rejects_string_boolean_before_network(tmp_path):
    c = Client(cache_dir=tmp_path, fetch=lambda _: pytest.fail("must validate first"))
    with pytest.raises(ValueError):
        c.scan(store="195", in_stock="false")
