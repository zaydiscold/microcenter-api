import json
from urllib.parse import parse_qs, urlsplit
import pytest
from microcenter_api import StorefrontClient as Client, BlockedError, ParseError
from microcenter_api import parsers
from microcenter_api.errors import RateLimitedError
from microcenter_api.storage import Storage


def card(i=1, stock="25+ IN STOCK", price="10.99", sku=None):
    return f'''<li class="product_wrapper"><p class="sku">SKU: {sku or str(100000 + i)}</p><div class="h2"><a href="/product/{i}/synthetic-matte-pla" data-id="{i}" data-brand="Example" data-category="Filaments &amp; Resins" data-price="{price}">Matte PLA {i}</a></div><span class="inventoryCnt">{stock}</span><strike>$19.99</strike><img src="https://productimages.microcenter.com/example.jpg"></li>'''


def page(ids, total=None):
    return (
        '<a class="dimValLink" href="?myStore=true">'
        + str(total if total is not None else len(ids))
        + " items in-stock in Santa Clara</a>"
        + "".join(card(i) for i in ids)
    )


class FakeTransport:
    def __init__(self, handler):
        self.handler = handler
        self.calls = []
        self.closed = False

    def fetch(self, url, form=None):
        self.calls.append((url, form))
        return self.handler(url, form)

    def close(self):
        self.closed = True


def client(tmp_path, handler, ttl=300):
    t = FakeTransport(handler)
    c = Client(cache_dir=tmp_path, transport=t, cache_ttl=ttl)
    c.storage.wait = lambda: None
    return c, t


def test_stock_lower_bound_sold_out_and_shipping():
    d = parsers.parse_search(page([1]))["products"][0]
    assert d["stock"]["quantity"] == 25 and d["stock"]["quantity_is_lower_bound"]
    assert d["category"] == "Filaments & Resins"
    assert parsers.stock("SOLD OUT at Miami Store")["in_stock"] is False
    assert parsers.stock("Usually ships in 5-7 business days")["quantity"] is None
    assert parsers.stock("0 IN STOCK")["in_stock"] is False


@pytest.mark.parametrize(
    "html",
    [
        "<h1>Sorry, compare four items only</h1>",
        "<title>Unexpected</title>",
        '<li class="product_wrapper">broken card</li>',
    ],
)
def test_markup_failures_are_not_empty_catalogs(html):
    with pytest.raises(ParseError):
        parsers.parse_search(html)


def test_real_empty_message():
    assert parsers.parse_search("<p>No products found</p>")["returned"] == 0


def test_cache_reuses_observation_and_avoids_network(tmp_path):
    c, t = client(tmp_path, lambda *_: page([1]))
    a = c.search("matte", store="195")
    b = c.search("matte", store="195")
    assert len(t.calls) == 1 and not a["cache_hit"] and b["cache_hit"]
    assert a["observed_at"] == b["observed_at"]
    c.search("matte", store="101")
    assert len(t.calls) == 2


def test_exact_sku_inventory_filters_fuzzy_fallback(tmp_path):
    stores = '<a href="?storeid=195">CA - Santa Clara</a>'
    c, t = client(
        tmp_path,
        lambda url, _: (
            stores
            if "StoreChange" in url
            else card(1, sku="518159") + card(2, sku="999999")
        ),
    )
    r = c.inventory("518159", stores=["195"])
    assert [p["sku"] for p in r["stores"][0]["products"]] == ["518159"]
    assert c.inventory("111111", stores=["195"])["stores"][0]["status"] == "not_listed"
    with pytest.raises(ValueError):
        c.inventory("518159", stores=["999"])


def test_scan_checkpoint_resume_after_rate_limit(tmp_path):
    checkpoint = tmp_path / "scan.json"

    def first(url, _):
        p = int(parse_qs(urlsplit(url).query)["page"][0])
        if p == 2:
            raise RateLimitedError("60")
        return page(range(1, 97), 98)

    c, t = client(tmp_path / "cache", first)
    with pytest.raises(RateLimitedError):
        c.scan(checkpoint=checkpoint)
    state = json.loads(checkpoint.read_text())
    assert (
        state["next_page"] == 2
        and not state["complete"]
        and len(state["products"]) == 96
    )
    c2, t2 = client(tmp_path / "cache", lambda *_: page([97, 98], 98))
    result = c2.scan(checkpoint=checkpoint)
    assert result["complete"] and result["returned"] == 98 and len(t2.calls) == 1
    assert parse_qs(urlsplit(t2.calls[0][0]).query)["page"] == ["2"]
    with pytest.raises(ValueError):
        c2.scan(store="101", checkpoint=checkpoint)


def test_repeated_page_cannot_claim_completion(tmp_path):
    c, _ = client(tmp_path, lambda *_: page(range(96), 192))
    with pytest.raises(ParseError):
        c.scan(checkpoint=tmp_path / "scan.json")
    assert not json.loads((tmp_path / "scan.json").read_text())["complete"]


def test_shared_rate_gate_and_expired_cache(tmp_path):
    now = [100.0]
    sleeps = []

    def sleep(seconds):
        sleeps.append(seconds)
        now[0] += seconds

    s = Storage(
        tmp_path / "cache.sqlite", delay=4, jitter=0, clock=lambda: now[0], sleep=sleep
    )
    other = Storage(
        tmp_path / "cache.sqlite", delay=4, jitter=0, clock=lambda: now[0], sleep=sleep
    )
    s.wait()
    other.wait()
    assert sleeps == [4]
    s.put("k", {"x": 1})
    assert s.get("k", 5) == {"x": 1}
    now[0] += 6
    assert s.get("k", 5) is None


@pytest.mark.parametrize(
    "kwargs", [{"page": 0}, {"rpp": 1000}, {"store": "evil"}, {"in_stock": "false"}]
)
def test_input_validation_prevents_network(tmp_path, kwargs):
    c, t = client(tmp_path, lambda *_: page([1]))
    with pytest.raises(ValueError):
        c.search(**kwargs)
    assert not t.calls


@pytest.mark.parametrize(
    "url",
    [
        "https://evil.example/product/1/foo",
        "http://www.microcenter.com/product/1/foo",
        "https://www.microcenter.com/product/1",
        "https://www.microcenter.com@evil.example/product/1/foo",
    ],
)
def test_product_url_origin_and_slug_validation(tmp_path, url):
    c, t = client(tmp_path, lambda *_: "")
    with pytest.raises(ValueError):
        c.product(url)
    assert not t.calls


def test_product_metadata_and_variant_links():
    html = """<span class="inventoryCnt">6 NEW IN STOCK</span><script type="application/ld+json">{"@type":"Product","name":"Example","offers":{"price":"10.99"},"review":[{"text":"discard"}]}</script><script>const p={"product_id":"660548","short_sku":"518159","price":"10.99","has_member_price":"False"};</script><a class="variantFrame" href="/product/2/blue">Blue</a>"""
    p = parsers.parse_product(html, "195")
    assert p["id"] == "660548" and p["stock"]["quantity"] == 6
    assert p["fields"]["short_sku"] == "518159" and "review" not in p["schema"]
    assert "storeid=195" in p["variants"][0]["url"]


def test_block_stops_scan_and_persists_checkpoint(tmp_path):
    def blocked(*_):
        raise BlockedError("blocked")

    c, t = client(tmp_path, blocked)
    with pytest.raises(BlockedError):
        c.scan(checkpoint=tmp_path / "scan.json")
    assert (
        len(t.calls) == 1
        and not json.loads((tmp_path / "scan.json").read_text())["complete"]
    )


def test_hidden_price_preserves_product_without_inventing_zero():
    p = parsers.parse_search(card(price=""))["products"][0]
    assert (
        p["price"] is None
        and p["price_status"] == "not_published"
        and p["savings"] is None
    )


def test_short_page_cannot_claim_full_catalog(tmp_path):
    c, _ = client(tmp_path, lambda *_: page(range(24), 1000))
    checkpoint = tmp_path / "scan.json"
    with pytest.raises(ParseError):
        c.scan(checkpoint=checkpoint)
    assert not json.loads(checkpoint.read_text())["complete"]
    assert json.loads(checkpoint.read_text())["next_page"] == 1


def test_duplicate_ids_within_page_are_deduplicated(tmp_path):
    c, _ = client(tmp_path, lambda *_: page([1, 1], 1))
    r = c.scan(checkpoint=tmp_path / "scan.json")
    assert r["complete"] and len(r["products"]) == 1


def test_recommendation_limit_does_not_apply_to_main_product():
    h = """<script>{"product_id":"123"}</script><div id="options-button"><form class="crtfrm">Buy</form></div><div class="recommendations">Limit 1 per household</div>"""
    assert parsers.parse_product(h)["purchase_limit"] is None
    assert (
        parsers.parse_product(
            h.replace(">Buy</form>", ">Buy Limit 2 per household</form>")
        )["purchase_limit"]
        == "Limit 2 per household"
    )


def test_cdp_send_and_receive_errors_are_controlled():
    from microcenter_api.transport import CDPTransport
    from microcenter_api.errors import MicroCenterError

    class Broken:
        def send(self, value):
            raise RuntimeError("closed")

    b = CDPTransport(cdp_url="http://127.0.0.1:9222")
    b.socket = Broken()
    with pytest.raises(MicroCenterError):
        b._send("Page.enable")

    class ReadBroken:
        def send(self, value):
            pass

        def settimeout(self, value):
            pass

        def recv(self):
            raise RuntimeError("timeout")

    b.socket = ReadBroken()
    with pytest.raises(MicroCenterError):
        b._send("Page.enable")
