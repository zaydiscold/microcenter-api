import json
from microcenter_api.gallery import gallery


def test_gallery_escapes_content_and_rejects_lookalike_hosts(tmp_path):
    source = tmp_path / "data.json"
    target = tmp_path / "gallery.html"
    source.write_text(
        json.dumps(
            {
                "products": [
                    {
                        "id": "1",
                        "name": "Matte filament <img onerror=alert(1)>",
                        "price": 10,
                        "savings": None,
                        "stock": {},
                        "url": "https://evilmicrocenter.com/a",
                        "image": "https://fakerackcdn.com/a",
                    }
                ]
            }
        )
    )
    r = gallery(source, target)
    page = target.read_text()
    assert r["filaments"] == 1 and r["network_requests"] == 0
    assert (
        "&lt;img onerror=" in page
        and "https://evilmicrocenter" not in page
        and "https://fakerackcdn" not in page
    )
    assert "Global catalog snapshot; local inventory unverified" in page
    assert 'id="sale" type="checkbox" checked' not in page
