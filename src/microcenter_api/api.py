"""Optional loopback HTTP API. Upstream calls stay on one dedicated thread."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from typing import Annotated
from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import JSONResponse
from .discovery import DiscoveryClient as Client
from .errors import BlockedError, RateLimitedError, MicroCenterError

Store = Annotated[str | None, Query(pattern=r"^\d{1,3}$")]
Sku = Annotated[str, Query(pattern=r"^\d{1,8}$")]


def create_app(config=None, *, client_factory=Client):
    config = config or {}
    worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="microcenter-upstream")
    holder = {}

    def execute(method, kwargs):
        if "client" not in holder:
            holder["client"] = client_factory(**config)
        return getattr(holder["client"], method)(**kwargs)

    async def run(method, **kwargs):
        try:
            return await asyncio.get_running_loop().run_in_executor(
                worker, execute, method, kwargs
            )
        except ValueError as e:
            raise HTTPException(422, str(e)) from e
        except RateLimitedError as e:
            headers = {"Retry-After": e.retry_after} if e.retry_after else None
            return JSONResponse({"error": str(e)}, status_code=429, headers=headers)
        except BlockedError as e:
            raise HTTPException(503, str(e)) from e
        except MicroCenterError as e:
            raise HTTPException(502, str(e)) from e

    @asynccontextmanager
    async def lifespan(app):
        yield
        if "client" in holder:
            await asyncio.get_running_loop().run_in_executor(
                worker, holder["client"].close
            )
        worker.shutdown(wait=True)

    app = FastAPI(
        title="Micro Center API",
        version="0.3.0",
        description="Unofficial read-only catalog, store availability and prices. Cached, sequential, anonymously accessed.",
        lifespan=lifespan,
    )

    @app.get("/health")
    async def health():
        return {"ok": True, "upstream_checked": False, "read_only": True}

    @app.get("/stores")
    async def stores():
        return await run("stores")

    @app.get("/categories")
    async def categories(store: Store = None):
        return await run("categories", store=store)

    @app.get("/search")
    async def search(
        query: str = "",
        store: Store = None,
        fq: str = "",
        category: str | None = None,
        in_stock: bool | None = None,
        page: int = Query(1, ge=1, le=10000),
        rpp: int = 24,
        sort: str = "match",
    ):
        if not 1 <= rpp <= 200:
            raise HTTPException(422, "rpp must be between 1 and 200")
        return await run(
            "search",
            query=query,
            store=store,
            fq=fq,
            category=category,
            in_stock=in_stock,
            page=page,
            rpp=rpp,
            sort=sort,
        )

    @app.get("/product")
    async def product(url: str, store: Store = None):
        return await run("product", url=url, store=store)

    @app.get("/inventory")
    async def inventory(sku: Sku, stores: Annotated[list[str] | None, Query()] = None):
        return await run("inventory", sku=sku, stores=stores)

    @app.get("/compare")
    async def compare(
        skus: Annotated[list[str], Query(min_length=1, max_length=4)],
        store: Store = None,
    ):
        return await run("compare", skus=skus, store=store)

    @app.get("/suggest")
    async def suggest(query: str = Query(min_length=2, max_length=200)):
        return await run("suggest", query=query)

    @app.get("/nearby")
    async def nearby(zip: Annotated[str, Query(pattern=r"^\d{5}$")]):
        return await run("nearby", zip_code=zip)

    return app
