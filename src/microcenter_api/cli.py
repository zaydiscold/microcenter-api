"""Command-line entrypoint. JSON on stdout; scan progress and errors on stderr."""

import argparse, csv, json, sys
from pathlib import Path
from .client import Client as StorefrontClient, write_json
from .discovery import DiscoveryClient as Client
from .errors import MicroCenterError


def save(data, path=None, fmt="json"):
    if fmt == "csv":
        rows = data.get("products", [])
        fields = [
            "id",
            "sku",
            "name",
            "category",
            "brand",
            "price",
            "original_price",
            "savings",
            "store_id",
            "stock",
            "url",
        ]
        f = Path(path).open("w", newline="") if path else sys.stdout
        try:
            writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            for row in rows:
                writer.writerow({**row, "stock": row.get("stock", {}).get("text", "")})
        finally:
            if path:
                f.close()
    elif path:
        write_json(path, data)
    else:
        print(json.dumps(data, indent=2))


def main():
    p = argparse.ArgumentParser(
        description="Unofficial read-only Micro Center API and CLI"
    )
    p.add_argument(
        "--cdp-url",
        help="Optional existing Chromium debug endpoint; a separate anonymous context is created",
    )
    p.add_argument(
        "--storefront",
        action="store_true",
        help="Explicit slower HTML/browser fallback for local stock",
    )
    p.add_argument("--headed", action="store_true")
    p.add_argument("--delay", type=float, default=4.0)
    p.add_argument("--jitter", type=float, default=1.0)
    p.add_argument("--cache-ttl", type=float, default=300)
    p.add_argument("--cache-dir", type=Path)
    p.add_argument("--output", type=Path)
    p.add_argument("--format", choices=["json", "csv"], default="json")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("stores")
    sub.add_parser("categories")
    for name in ("search", "scan"):
        a = sub.add_parser(name)
        a.add_argument("query", nargs="?", default="")
        a.add_argument("--store", default=None)
        a.add_argument("--fq", default="")
        a.add_argument("--category")
        a.add_argument("--include-out-of-stock", action="store_true")
        if name == "search":
            a.add_argument("--page", type=int, default=1)
            a.add_argument("--rpp", type=int, default=24)
            a.add_argument("--sort", default="match")
        else:
            a.add_argument("--checkpoint", type=Path, required=True)
            a.add_argument("--max-pages", type=int, default=1000)
    a = sub.add_parser("product")
    a.add_argument("url")
    a.add_argument("--store", default=None)
    a = sub.add_parser("inventory")
    a.add_argument("sku")
    a.add_argument("--stores", nargs="+")
    a = sub.add_parser("compare")
    a.add_argument("skus", nargs="+")
    a.add_argument("--store", default=None)
    a = sub.add_parser("suggest")
    a.add_argument("query")
    a = sub.add_parser("nearby")
    a.add_argument("zip_code")
    a = sub.add_parser("filter")
    a.add_argument("snapshot", type=Path)
    a.add_argument("--query", default="")
    a.add_argument("--category", default="")
    a.add_argument("--sale", action="store_true")
    a.add_argument("--max-price", type=float)
    a.add_argument("--sort", choices=["price", "savings", "name"], default="price")
    a = sub.add_parser("gallery")
    a.add_argument("snapshot", type=Path)
    a.add_argument(
        "--images",
        type=Path,
        help="Optional direct catalog snapshot for matching CDN image URLs by product ID",
    )
    a = sub.add_parser("serve")
    a.add_argument("--port", type=int, default=8766)
    args = vars(p.parse_args())
    command = args.pop("command")
    storefront = args.pop("storefront")
    out = args.pop("output")
    fmt = args.pop("format")
    config = {
        k: args.pop(k)
        for k in ["cdp_url", "headed", "delay", "jitter", "cache_ttl", "cache_dir"]
    }
    try:
        if command == "gallery":
            from .gallery import gallery

            if not out:
                raise ValueError(
                    "gallery requires --output photo-gallery.html before the command"
                )
            print(json.dumps(gallery(args["snapshot"], out, args.get("images"))))
            return
        if command == "filter":
            data = json.loads(args["snapshot"].read_text())
            rows = data.get("products", [])
            if (
                args["sale"]
                and rows
                and all(x.get("original_price") is None for x in rows)
            ):
                raise ValueError(
                    "This catalog has no verified original prices; sale status is unknown. Use a store-verified snapshot."
                )
            rows = [
                x
                for x in rows
                if args["query"].lower() in x["name"].lower()
                and args["category"].lower() in (x.get("category") or "").lower()
                and (not args["sale"] or (x.get("savings") or 0) > 0)
                and (
                    args["max_price"] is None
                    or (x.get("price") is not None and x["price"] <= args["max_price"])
                )
            ]
            rows.sort(
                key=lambda r: (r.get(args["sort"]) is None, r.get(args["sort"]) or 0),
                reverse=args["sort"] == "savings",
            )
            save(
                {
                    "products": rows,
                    "returned": len(rows),
                    "snapshot": str(args["snapshot"]),
                    "network_requests": 0,
                },
                out,
                fmt,
            )
            return
        if command == "serve":
            try:
                import uvicorn
                from .api import create_app
            except ImportError:
                raise MicroCenterError(
                    'Install API dependencies: pip install "microcenter-api-cli[api]"'
                )
            uvicorn.run(
                create_app(
                    config, client_factory=StorefrontClient if storefront else Client
                ),
                host="127.0.0.1",
                port=args["port"],
                access_log=False,
            )
            return
        if "include_out_of_stock" in args:
            include = args.pop("include_out_of_stock")
            args["in_stock"] = (
                (not include) if storefront or args.get("store") is not None else None
            )
        if storefront:
            if "category" in args:
                category = args.pop("category")
                if category:
                    args["fq"] = "category:Category|" + category
            if args.get("store") is None and "store" in args:
                args["store"] = "195"
        with (StorefrontClient if storefront else Client)(**config) as client:
            if command == "scan":

                def report(state):
                    if "checked" in state:
                        message = f"checked={state['checked']}/{state['candidate_total']} in_stock={state['in_stock_count']} complete={state['complete']}"
                    else:
                        message = f"page={state['pages'][-1]['page']} unique={state['returned']} advertised={state.get('advertised_in_stock', state.get('total_results'))} complete={state['complete']}"
                    print(message, file=sys.stderr, flush=True)

                args["progress"] = report
            result = getattr(client, command)(**args)
            if command == "scan":
                result["metrics"] = client.metrics
            save(result, out, fmt)
    except (MicroCenterError, ValueError, OSError, json.JSONDecodeError) as e:
        print(f"microcenter: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("microcenter: interrupted; scan checkpoint retained", file=sys.stderr)
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
