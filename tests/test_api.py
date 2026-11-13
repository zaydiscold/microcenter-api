import threading
import pytest
from fastapi.testclient import TestClient
from microcenter_api.api import create_app
from microcenter_api.errors import BlockedError, RateLimitedError


class FakeClient:
    def __init__(self, **kwargs):
        self.thread = threading.get_ident()
        self.closed = False

    def search(self, **kwargs):
        assert threading.get_ident() == self.thread
        return {"products": [], "request": kwargs}

    def stores(self):
        assert threading.get_ident() == self.thread
        return {"stores": []}

    def close(self):
        assert threading.get_ident() == self.thread
        self.closed = True


def test_openapi_health_validation_and_worker():
    made = []

    def factory(**kwargs):
        c = FakeClient()
        made.append(c)
        return c

    with TestClient(create_app(client_factory=factory)) as api:
        assert api.get("/health").json()["upstream_checked"] is False
        assert not made
        assert "/inventory" in api.get("/openapi.json").json()["paths"]
        assert api.get("/search?page=0").status_code == 422
        assert api.get("/search?rpp=201").status_code == 422
        assert api.get("/search?store=abc").status_code == 422
        assert api.get("/inventory?sku=oops").status_code == 422
        assert api.get("/nearby?zip=abc").status_code == 422
        assert not made
        assert api.get("/stores").status_code == 200
        assert (
            api.get("/search?store=195&in_stock=false").json()["request"]["in_stock"]
            is False
        )
    assert made[0].closed


@pytest.mark.parametrize(
    "error,status", [(BlockedError("blocked"), 503), (RateLimitedError("60"), 429)]
)
def test_upstream_access_errors_do_not_retry(error, status):
    class Broken(FakeClient):
        calls = 0

        def stores(self):
            Broken.calls += 1
            raise error

    with TestClient(create_app(client_factory=Broken)) as api:
        r = api.get("/stores")
        assert r.status_code == status and Broken.calls == 1
        if status == 429:
            assert r.headers["Retry-After"] == "60"


def test_store_product_route_uses_native_json_without_catalog_or_browser(tmp_path):
    import json
    from microcenter_api import Client

    calls = []

    def native(url, form):
        calls.append((url, form))
        return json.dumps(
            {
                "product_id": "660548",
                "short_sku": "518159",
                "title": "Synthetic filament",
                "price": "10.99",
                "original_price": "19.99",
                "in_stock": "False",
                "can_pickup": "True",
                "can_ship": "True",
            }
        ).encode()

    def factory(**config):
        client = Client(
            cache_dir=tmp_path,
            store_fetch=native,
            fetch=lambda _: pytest.fail("product route must not fetch global catalog"),
        )
        client.storage.wait = lambda: None
        return client

    with TestClient(create_app(client_factory=factory)) as api:
        response = api.get("/product?url=660548&store=185")
        assert response.status_code == 200
        row = response.json()["product"]
        assert row["store_id"] == "185" and row["price"] == 10.99
        assert row["stock"]["in_stock"] is False
        assert row["stock"]["quantity"] is None
        assert row["can_pickup"] is True and row["browser_used"] is False
        assert "storeid=185" in calls[0][0]
        assert calls[0][1] == {"type": "product", "product_id": "660548"}
        again = api.get("/product?url=660548&store=185").json()
        assert again["product"]["cache_hit"] is True and len(calls) == 1
