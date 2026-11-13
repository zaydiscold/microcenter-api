"""Pure parsers. No JavaScript execution or browser/account data extraction."""

import json
import re
from urllib.parse import urljoin, urlsplit, urlunsplit, parse_qsl, urlencode
from bs4 import BeautifulSoup
from .errors import ParseError

ORIGIN = "https://www.microcenter.com"


def soup(html):
    return BeautifulSoup(html, "html.parser")


def text(node):
    return " ".join(node.stripped_strings) if node else ""


def amount(value):
    m = re.search(r"\d+(?:\.\d+)?", str(value or "").replace(",", ""))
    return float(m[0]) if m else None


def absolute(path):
    return urljoin(ORIGIN, path)


def local_link(path, store):
    u = urlsplit(absolute(path))
    q = dict(parse_qsl(u.query))
    q["storeid"] = store
    return urlunsplit((u.scheme, u.netloc, u.path, urlencode(q), ""))


def stock(value):
    m = re.search(r"(\d+)(\+)?\s+(?:NEW\s+)?IN STOCK", value, re.I)
    available = (
        bool(int(m[1]))
        if m
        else False
        if re.search(r"sold out|out of stock", value, re.I)
        else None
    )
    return {
        "text": value,
        "quantity": int(m[1]) if m else None,
        "quantity_is_lower_bound": bool(m and m[2]),
        "in_stock": available,
    }


def parse_search(html, store="029"):
    d = soup(html)
    rows = []
    for li in d.select(".product_wrapper"):
        a = li.select_one(".h2 a")
        if not a or not a.get("data-id"):
            raise ParseError("A product card is missing its ID/link")
        price = amount(a.get("data-price"))
        original = amount(text(li.select_one("strike")))
        st = text(li.select_one(".inventoryCnt")) or text(li.select_one(".stock"))
        sku = re.sub(r"^SKU:\s*", "", text(li.select_one("p.sku")))
        if not sku.isdigit():
            raise ParseError("A product card is missing a valid SKU")
        t = text(li)
        img = li.select_one("img")
        rows.append(
            {
                "id": a["data-id"],
                "sku": sku,
                "name": text(a),
                "brand": a.get("data-brand"),
                "category": a.get("data-category"),
                "price": price,
                "price_status": "published" if price is not None else "not_published",
                "original_price": original,
                "savings": round(original - price, 2)
                if original is not None and price is not None
                else None,
                "member_savings": amount(a.get("data-membersaving")),
                "store_id": store,
                "stock": stock(st),
                "url": local_link(a["href"], store),
                "image": absolute(img["src"]) if img and img.get("src") else None,
                "flags": {
                    "in_store_only": bool(re.search("In Store Only", t, re.I)),
                    "open_box": bool(re.search("Open Box", t, re.I)),
                    "closeout": bool(re.search("Closeout", t, re.I)),
                },
                "purchase_limit": next(
                    iter(re.findall(r"Limit\s+\d+\s+per\s+household", t, re.I)), None
                ),
            }
        )
    facets = [
        {"label": text(a), "url": absolute(a["href"])}
        for a in d.select("a.dimValLink[href]")
    ]
    scope = next(
        (f["label"] for f in facets if "items in-stock" in f["label"]),
        text(d.select_one(".my-store-only")),
    )
    m = re.search(r"([\d,]+)\s+items?\s+in.stock", scope, re.I)
    # A bare 'sorry' is not evidence of an empty catalog (it occurs in compare dialogs).
    empty = bool(
        re.search(
            r"\bno (?:results|products)\b|\b0\s+Product\(s\) found|did not match any|couldn.t find (?:any|a match)",
            text(d),
            re.I,
        )
    )
    if not rows and not empty:
        raise ParseError("No product cards and no recognized empty-results state")
    return {
        "products": rows,
        "returned": len(rows),
        "facets": facets,
        "total_in_stock": int(m[1].replace(",", "")) if m else None,
        "scope_text": scope,
        "response_bytes": len(html.encode()),
    }


def parse_stores(html):
    found = {}
    for a in soup(html).select("a[href]"):
        name = text(a)
        q = dict((k.lower(), v) for k, v in parse_qsl(urlsplit(a["href"]).query))
        sid = q.get("storeid")
        if sid and (re.match(r"^[A-Z]{2}\s*-", name) or name == "Shippable Items"):
            found[sid.zfill(3)] = {
                "id": sid.zfill(3),
                "name": name,
                "shipping": name == "Shippable Items",
            }
    if not found:
        raise ParseError("No stores found")
    return {"stores": list(found.values())}


def parse_categories(html):
    found = {}
    for a in soup(html).select("a[href]"):
        fq = dict(parse_qsl(urlsplit(a["href"]).query)).get("fq", "")
        for m in re.finditer(r"(?:^|,)category(?:_flat)?:([^,|]+)\|(\d+)", fq, re.I):
            found[m[2]] = {"id": m[2], "name": m[1], "fq": f"category:{m[1]}|{m[2]}"}
    if not found:
        raise ParseError("No navigation categories found")
    return {"categories": list(found.values())}


def parse_product(html, store="029"):
    d = soup(html)
    schema = None
    for s in d.select('script[type="application/ld+json"]'):
        try:
            j = json.loads(s.string or s.get_text())
        except (ValueError, TypeError):
            continue
        for obj in j if isinstance(j, list) else j.get("@graph", [j]):
            if isinstance(obj, dict) and obj.get("@type") == "Product":
                schema = obj.copy()
                schema.pop("review", None)
    script = "\n".join(s.get_text() for s in d.select("script:not([src])"))
    fields = {}
    for k in [
        "product_id",
        "short_sku",
        "title",
        "brand",
        "price",
        "original_price",
        "discount",
        "in_stock",
        "can_pickup",
        "can_ship",
        "manufacturer_number",
        "upc",
        "has_member_price",
        "showed_member_price",
        "has_proritycare_price",
        "showed_proritycare_price",
    ]:
        m = re.search(r'"' + k + r'"\s*:\s*("(?:[^"\\]|\\.)*")', script)
        if m:
            try:
                fields[k] = json.loads(m[1])
            except ValueError:
                pass
    if not schema and not fields.get("product_id"):
        raise ParseError("Product missing or product markup changed")
    variants = [
        {"label": text(a), "url": local_link(a["href"], store)}
        for a in d.select(".variantFrame[href]")
    ]
    st = text(d.select_one(".inventoryCnt")) or next(
        (
            text(x)
            for x in d.select(".stock")
            if re.search(r"IN STOCK|SOLD OUT|OUT OF STOCK", text(x), re.I)
        ),
        "",
    )
    for s in d.select("script,style,nav,header,footer"):
        s.decompose()
    # Never attribute a recommendation's limit to the primary product.
    panel = d.select_one("#options-button")
    limit = next(
        iter(re.findall(r"Limit\s+\d+\s+per\s+household", text(panel), re.I)), None
    )
    return {
        "id": fields.get("product_id"),
        "fields": fields,
        "schema": schema,
        "variants": variants,
        "stock": stock(st),
        "purchase_limit": limit,
        "store_id": store,
    }


def parse_links(html):
    d = soup(html)
    for s in d.select("script,style"):
        s.decompose()
    return {
        "text": text(d),
        "links": [
            {"label": text(a), "url": absolute(a["href"])} for a in d.select("a[href]")
        ],
    }
