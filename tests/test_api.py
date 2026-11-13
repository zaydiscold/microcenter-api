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
