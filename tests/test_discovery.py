import json
from urllib.parse import urlsplit, parse_qs
import pytest
from microcenter_api import Client, ParseError


def envelope(ids, total=None, start=0):
    return json.dumps(
        {
            "response": {
                "numFound": len(ids) if total is None else total,
                "start": start,
                "docs": [
                    {
                        "pid": str(i),
                        "title": f"Filament {i}",
                        "price": 10.99,
                        "sale_price": 10.99,
                        "url": f"https://www.microcenter.com/product/{i}/example",
                    }
                    for i in ids
                ],
            },
            "facet_counts": {"facets": []},
        }
    ).encode()


def test_default_client_is_direct_and_cached(tmp_path):
    calls = []

    def fetch(url):
        calls.append(url)
        return envelope([123])

    c = Client(cache_dir=tmp_path, fetch=fetch)
    c.storage.wait = lambda: None
    a = c.search("filament")
    b = c.search("filament")
    assert (
        not a["browser_used"]
        and a["backend"] == "discovery"
        and b["cache_hit"]
        and len(calls) == 1
    )
    assert urlsplit(calls[0]).netloc == "core.dxpapi.com"
    params = parse_qs(urlsplit(calls[0]).query, keep_blank_values=True)
    assert params["auth_key"] == [""] and params["account_id"] == ["7835"]
    assert (
        a["products"][0]["stock"]["in_stock"] is None
        and a["products"][0]["original_price"] is None
    )


@pytest.mark.parametrize("kwargs", [{"in_stock": True}, {"rpp": 201}, {"page": 1000}])
def test_no_unverified_store_scope_or_unbounded_offset(tmp_path, kwargs):
    c = Client(cache_dir=tmp_path, fetch=lambda _: pytest.fail("must not call backend"))
    with pytest.raises(ValueError):
        c.search(**kwargs)


def test_direct_pagination_and_complete_count(tmp_path):
    calls = []

    def fetch(url):
        q = parse_qs(urlsplit(url).query)
        start = int(q["start"][0])
        calls.append(start)
        return envelope(range(start, min(201, start + 200)), 201, start)

    c = Client(cache_dir=tmp_path, fetch=fetch)
    c.storage.wait = lambda: None
    r = c.scan(category="754", checkpoint=tmp_path / "scan.json")
    assert r["complete"] and r["returned"] == 201 and calls == [0, 200]


def test_direct_short_page_fails_closed(tmp_path):
    c = Client(cache_dir=tmp_path, fetch=lambda _: envelope([1, 2], 300))
    c.storage.wait = lambda: None
    with pytest.raises(ParseError):
        c.scan(checkpoint=tmp_path / "scan.json")
    assert not json.loads((tmp_path / "scan.json").read_text())["complete"]


def test_category_conversion_preserves_identity(tmp_path):
    urls = []
    c = Client(cache_dir=tmp_path, fetch=lambda u: urls.append(u) or envelope([1]))
    c.storage.wait = lambda: None
    c.search(fq="category:Filaments & Resins|754")
    q = parse_qs(urlsplit(urls[0]).query)
    assert q["search_type"] == ["category"] and q["q"] == ["754"]


@pytest.mark.parametrize(
    "payload",
    [b"[]", b"null", b'"text"', b'{"response":{"numFound":1,"start":0,"docs":[null]}}'],
)
def test_malformed_json_shapes_are_controlled_errors(tmp_path, payload):
    c = Client(cache_dir=tmp_path, fetch=lambda _: payload)
    c.storage.wait = lambda: None
    with pytest.raises(ParseError):
        c.search("filament")
