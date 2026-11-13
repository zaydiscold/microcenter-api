"""Offline photo gallery generation from an explicitly observed catalog snapshot."""

import html, json
from pathlib import Path
from urllib.parse import urlsplit


def gallery(snapshot, output, images=None):
    data = json.loads(Path(snapshot).read_text())
    items = data.get("products", [])
    if images:
        by_id = {
            p["id"]: p for p in json.loads(Path(images).read_text()).get("products", [])
        }
        items = [
            {**p, "image": by_id.get(p["id"], {}).get("image") or p.get("image")}
            for p in items
        ]
    rows = [
        p
        for p in items
        if "filament" in p["name"].lower() and "resin" not in p["name"].lower()
    ]

    def color_order(p):
        name = p["name"].lower()
        if "matte" in name and any(
            t in name for t in ("denim", "peach", "banana", "pastel", "purple", "lulz")
        ):
            return (0, p.get("price") or 999999, name)
        if any(t in name for t in ("rainbow", "dual color", "triple color")):
            return (1, p.get("price") or 999999, name)
        if "translucent" in name:
            return (2, p.get("price") or 999999, name)
        return (3, p.get("price") or 999999, name)

    rows.sort(key=color_order)

    def safe_url(value, product=False):
        u = urlsplit(value or "")
        domains = (
            ("microcenter.com",) if product else ("microcenter.com", "rackcdn.com")
        )
        return (
            value
            if u.scheme == "https"
            and any(
                u.hostname == d or (u.hostname or "").endswith("." + d) for d in domains
            )
            else ""
        )

    sid = data.get("signature", {}).get("store")
    scope = (
        "Santa Clara store snapshot"
        if sid == "195"
        else "Store " + str(sid) + " snapshot"
        if sid
        else "Global catalog snapshot; local inventory unverified"
    )
    sale_default = any((p.get("savings") or 0) > 0 for p in rows)
    cards = []
    for p in rows:
        name = p["name"]
        lower = name.lower()
        material = (
            "PETG"
            if "petg" in lower
            else "Matte PLA"
            if "matte" in lower
            else "Silk PLA"
            if "silk" in lower
            else "Other filament"
        )
        fun = any(
            t in lower
            for t in [
                "matte",
                "silk",
                "petg",
                "rainbow",
                "glitter",
                "iridescent",
                "chameleon",
                "frosty",
            ]
        )
        sale = (p.get("savings") or 0) > 0
        e = html.escape
        old = f"<del>${p['original_price']:.2f}</del>" if sale else ""
        price = (
            f"${p['price']:.2f}" if p.get("price") is not None else "Price unavailable"
        )
        saving = f"Save ${p['savings']:.2f}" if sale else "No verified discount"
        cards.append(
            f'''<article data-material="{material}" data-price="{p.get("price") or 999999}" data-sale="{int(sale)}" data-fun="{int(fun)}"><a href="{e(safe_url(p.get("url"), True))}" target="_blank" rel="noopener"><img loading="lazy" src="{e(safe_url(p.get("image")))}" alt="{e(name)}"></a><small>{material}</small><h2><a href="{e(safe_url(p.get("url"), True))}" target="_blank" rel="noopener">{e(name.split(";")[0])}</a></h2><div class="price">{price} {old}</div><div class="meta">{saving} · {e(p.get("stock", {}).get("text", "Unknown stock"))}</div></article>'''
        )
    observed = (
        data.get("finished_at") or data.get("observed_at") or "See source snapshot"
    )
    page = (
        """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Filament color and sale finder</title><style>body{margin:0;background:#f5f2eb;color:#232923;font:16px system-ui}header,main{max-width:1450px;margin:auto;padding:28px}h1{font-size:40px;letter-spacing:-1px;margin:0 0 12px}header p{max-width:1000px;line-height:1.6}nav{display:flex;gap:12px;flex-wrap:wrap;padding:18px 0}input,select{font:inherit;padding:10px;border:1px solid #aaa;border-radius:6px}label{display:flex;align-items:center;gap:8px}#query{flex:1;min-width:220px}.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:20px}article{background:#fff;padding:18px;border-radius:10px}article img{width:100%;height:210px;object-fit:contain}article a{color:inherit;text-decoration:none}h2{font-size:16px;line-height:1.5;min-height:90px}small,.meta{color:#59655b}.price{font-size:24px;font-weight:700;color:#00624b}del{font-size:16px;color:#6c756f;font-weight:400}.meta{font-size:14px;line-height:1.5;margin-top:8px}article[hidden]{display:none}#count{font-weight:600}</style></head><body><header><h1>Filament color & sale finder</h1><p>"""
        + html.escape(scope)
        + """. Photos, original prices, sale prices and displayed stock in one place. Start with the matte, silk, PETG and special-color deals; uncheck the filters to browse every captured filament. Each product links to its listing for a fresh check. Photos load from the vendor when online. Check spool weight in the name; prices are per listed item, before tax.</p><p>Observed through """
        + '<time id="observed" datetime="'
        + html.escape(observed)
        + '">'
        + html.escape(observed)
        + "</time>"
        + """ · Counts are a snapshot, not reservations.</p><nav><input id="query" placeholder="Search: denim, rainbow, copper, purple…"><select id="material"><option>All materials</option><option>Matte PLA</option><option>Silk PLA</option><option>PETG</option><option>Other filament</option></select><select id="price"><option value="999999">Any price</option><option value="12">Up to $12</option><option value="16">Up to $16</option><option value="20">Up to $20</option></select><label><input id="sale" type="checkbox" """
        + ("checked" if sale_default else "")
        + """>On sale</label><label><input id="fun" type="checkbox" checked>Interesting colors & finishes</label></nav><div id="count"></div></header><main><div class="grid">"""
        + "".join(cards)
        + """</div></main><script>const stamp=document.querySelector("#observed");const date=new Date(stamp.dateTime);if(!isNaN(date))stamp.textContent=date.toLocaleString(undefined,{dateStyle:"medium",timeStyle:"short"});const cards=[...document.querySelectorAll('article')];function filter(){let n=0;const q=document.querySelector('#query').value.toLowerCase(),m=document.querySelector('#material').value,p=Number(document.querySelector('#price').value),s=document.querySelector('#sale').checked,f=document.querySelector('#fun').checked;for(const c of cards){c.hidden=!(c.textContent.toLowerCase().includes(q)&&(m==='All materials'||m===c.dataset.material)&&Number(c.dataset.price)<=p&&(!s||c.dataset.sale==='1')&&(!f||c.dataset.fun==='1'));if(!c.hidden)n++}document.querySelector('#count').textContent=n+' matching filaments'}document.querySelectorAll('input,select').forEach(x=>x.addEventListener('input',filter));filter()</script></body></html>"""
    )
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(page)
    return {
        "output": str(Path(output).resolve()),
        "filaments": len(rows),
        "sale_items": sum((p.get("savings") or 0) > 0 for p in rows),
        "network_requests": 0,
    }
