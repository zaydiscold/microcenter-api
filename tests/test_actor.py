import asyncio
from copy import deepcopy
import pytest
from microcenter_api.actor_runner import run, validate_input
from microcenter_api.errors import RateLimitedError


class Actor:
    def __init__(self, data, limit=1000):
        self.data = data
        self.limit = limit
        self.rows = []
        self.records = {}
        self.status = ""

    async def open_dataset(self):
        return self

    async def get_data(self, limit=1):
        from types import SimpleNamespace

        return SimpleNamespace(items=self.rows[:limit])

    async def get_input(self):
        return self.data

    def get_charging_manager(self):
        return self

    def is_event_charge_limit_reached(self, _):
        return len(self.rows) >= self.limit

    async def push_data(self, row):
        self.rows.append(deepcopy(row))

    async def set_value(self, key, value):
        self.records[key] = deepcopy(value)

    async def set_status_message(self, value):
        self.status = value


class Client:
    def __init__(self, **kwargs):
        self.calls = []
        self.closed = False

    def stores(self):
        return {"stores": [{"id": "195"}, {"id": "101"}]}

    def product(self, pid, store):
        self.calls.append((pid, store))
        return {
            "product": {
                "id": pid,
                "store_id": store,
                "name": "Synthetic filament",
                "price": 10,
                "stock": {"in_stock": store == "195", "quantity": None},
                "raw": {"spec": "kept"},
                "backend": "native-json",
                "browser_used": False,
            }
        }

    def search(self, **kwargs):
        self.calls.append(("catalog", kwargs["page"]))
        return {
            "products": [{"id": "1"}, {"id": "2"}],
            "start": 0,
            "returned": 2,
            "total_results": 2,
        }

    def close(self):
        self.closed = True


def execute(data, limit=1000, client=None):
    actor = Actor(data, limit)
    client = client or Client()
    result = asyncio.run(run(actor, client_factory=lambda **_: client))
    return actor, client, result


def test_two_stores_have_separate_rows_and_unknown_quantities():
    a, c, s = execute(
        {
            "mode": "product",
            "productIds": ["1"],
            "storeIds": ["195", "101"],
            "includeRaw": True,
        }
    )
    assert s["complete"] and len(a.rows) == 2 and c.closed
    assert [x["stock"]["in_stock"] for x in a.rows] == [True, False]
    assert all(x["stock"]["quantity"] is None for x in a.rows)
    assert all("?storeid=" + x["store_id"] in x["url"] for x in a.rows)
    assert a.rows[0]["raw"] == {"spec": "kept"}


def test_budget_stops_before_next_network_observation():
    a, c, s = execute(
        {"mode": "product", "productIds": ["1", "2"], "storeIds": ["195", "101"]},
        limit=1,
    )
    assert c.calls == [("1", "195")] and len(a.rows) == 1
    assert s["stop_reason"] == "charge_limit" and not s["complete"]
    a, c, s = execute({"mode": "product", "productIds": ["1"]}, limit=0)
    assert c.calls == [] and s["results_saved"] == 0


def test_catalog_cap_does_not_claim_complete_and_raw_is_optional():
    a, c, s = execute({"maxProducts": 1})
    assert len(a.rows) == 1 and not s["complete"] and s["stop_reason"] == "maxProducts"
    assert "raw" not in a.rows[0] and "catalog_raw" not in a.rows[0]


def test_filtered_observations_are_not_output_or_billable_rows():
    a, c, s = execute(
        {
            "mode": "product",
            "productIds": ["1"],
            "storeIds": ["195", "101"],
            "includeOutOfStock": False,
        }
    )
    assert len(c.calls) == 2 and len(a.rows) == 1 and s["complete"]
    assert s["store_observations_checked"] == 2


def test_validation_precedes_client_or_network_activity():
    with pytest.raises(ValueError):
        asyncio.run(
            run(
                Actor({"maxProducts": 0}),
                client_factory=lambda **_: pytest.fail("must validate first"),
            )
        )
    for invalid in [
        {"includeRaw": "false"},
        {"storeIds": ["195", "https://evil"]},
        {"mode": "product", "productIds": ["https://evil"]},
        {"mode": "category", "categoryId": "bad"},
    ]:
        with pytest.raises(ValueError):
            validate_input(invalid)


def test_denial_keeps_saved_rows_and_marks_summary_incomplete():
    class Limited(Client):
        def product(self, pid, store):
            if pid == "2":
                raise RateLimitedError("60")
            return super().product(pid, store)

    a = Actor({"mode": "product", "productIds": ["1", "2"]})
    c = Limited()
    with pytest.raises(RateLimitedError):
        asyncio.run(run(a, client_factory=lambda **_: c))
    assert len(a.rows) == 1 and a.records["SUMMARY"]["stop_reason"] == "error"
    assert not a.records["SUMMARY"]["complete"] and c.closed


def test_result_cap_on_final_observation_is_still_complete():
    a, c, s = execute(
        {
            "mode": "product",
            "productIds": ["1"],
            "storeIds": ["195", "101"],
            "maxResults": 2,
        }
    )
    assert s["complete"] and s["stop_reason"] == "exhausted" and len(a.rows) == 2


@pytest.mark.parametrize("bad", [[], False, 0, ""])
def test_falsy_non_object_input_cannot_start_default_paid_work(bad):
    with pytest.raises(ValueError):
        asyncio.run(
            run(
                Actor(bad),
                client_factory=lambda **_: pytest.fail(
                    "invalid input must not construct a client"
                ),
            )
        )


def test_existing_dataset_refuses_restart_before_network_or_new_charges():
    from microcenter_api.errors import MicroCenterError

    a, c, s = execute({"mode": "product", "productIds": ["1"]})
    saved = list(a.rows)
    summary = deepcopy(a.records["SUMMARY"])
    with pytest.raises(MicroCenterError, match="duplicate charges"):
        asyncio.run(
            run(
                a,
                client_factory=lambda **_: pytest.fail(
                    "restart must fail before client construction"
                ),
            )
        )
    assert a.rows == saved and a.records["SUMMARY"] == summary


def test_duplicate_catalog_ids_cannot_charge_twice_or_claim_complete():
    from microcenter_api import ParseError

    class Duplicated(Client):
        def search(self, **kwargs):
            return {
                "products": [{"id": "1"}, {"id": "1"}],
                "start": 0,
                "returned": 2,
                "total_results": 2,
            }

    a = Actor({})
    c = Duplicated()
    with pytest.raises(ParseError):
        asyncio.run(run(a, client_factory=lambda **_: c))
    assert c.calls == [("1", "195")] and len(a.rows) == 1
    assert a.records["SUMMARY"]["complete"] is False
