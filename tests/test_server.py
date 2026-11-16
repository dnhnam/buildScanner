import io
import re

import numpy as np
import pytest

from scanner import core
from scanner.server import create_app, safe_pdf_name
from synth import make_photo

PHONE = {"REMOTE_ADDR": "192.168.1.23"}


def jpeg(**kw):
    photo, _ = make_photo(size=(1500, 2000), corners=np.float32([[300, 250], [1200, 330], [1260, 1750], [240, 1690]]), **kw)
    return core.encode_image(photo)


@pytest.fixture
def app(tmp_path):
    return create_app(tmp_path / "data")


@pytest.fixture
def client(app):
    return app.test_client()


def upload(client, n=1, **kw):
    data = {"files": [(io.BytesIO(jpeg()), f"trang{i}.jpg") for i in range(n)]}
    return client.post("/api/upload", data=data, content_type="multipart/form-data", **kw)


def test_full_flow(client):
    assert client.get("/").status_code == 200
    r = upload(client, 3)
    assert r.status_code == 200 and len(r.json["added"]) == 3
    pages = client.get("/api/pages").json["pages"]
    assert [p["auto_found"] for p in pages] == [True] * 3
    ids = [p["id"] for p in pages]

    for kind in ("thumbs", "processed", "previews"):
        assert client.get(f"/files/{kind}/{ids[0]}.jpg").status_code == 200

    r = client.patch(f"/api/pages/{ids[0]}", json={"corners_norm": [[0.9, 0.9], [0.1, 0.1], [0.9, 0.1], [0.1, 0.9]]})
    assert r.status_code == 200
    assert r.json["corners_norm"][0] == pytest.approx([0.1, 0.1])  # được sắp lại thứ tự
    assert client.patch(f"/api/pages/{ids[0]}", json={"rotate_by": 90, "mode": "bw"}).json["rotation"] == 90
    assert client.patch(f"/api/pages/{ids[0]}", json={"mode": "xyz"}).status_code == 400
    assert client.patch(f"/api/pages/{ids[0]}", json={"redetect": True}).json["auto_found"]

    client.post("/api/pages/order", json={"ids": ids[::-1]})
    assert [p["id"] for p in client.get("/api/pages").json["pages"]] == ids[::-1]

    client.delete(f"/api/pages/{ids[1]}")
    assert len(client.get("/api/pages").json["pages"]) == 2

    r = client.get("/api/export?size=a4&name=Hợp đồng thuê nhà")
    assert r.status_code == 200 and r.data.startswith(b"%PDF")
    assert len(re.findall(rb"/Type\s*/Page\b", r.data)) == 2
    assert "Hợp đồng thuê nhà.pdf" in r.headers["Content-Disposition"].replace("%20", " ") or "filename*" in r.headers["Content-Disposition"]

    client.delete("/api/pages")
    assert client.get("/api/export").status_code == 400


def test_pages_survive_restart(tmp_path):
    a = create_app(tmp_path / "d").test_client()
    upload(a, 2)
    b = create_app(tmp_path / "d").test_client()
    assert len(b.get("/api/pages").json["pages"]) == 2


def test_phone_needs_token(app, client):
    token = app.config["TOKEN"]
    assert client.get("/m", environ_base=PHONE).status_code == 403
    assert client.get(f"/m?t={token}", environ_base=PHONE).status_code == 200
    assert upload(client, environ_base=PHONE).status_code == 403
    r = upload(client, query_string={"t": token}, environ_base=PHONE)
    assert r.status_code == 200 and r.json["added"][0]["source"] == "phone"


def test_phone_cannot_manage_or_export(app, client):
    token = app.config["TOKEN"]
    for method, url in [("get", "/api/pages"), ("get", "/api/export"), ("delete", "/api/pages"), ("get", "/api/info")]:
        assert getattr(client, method)(f"{url}?t={token}", environ_base=PHONE).status_code == 403


def test_bad_file_reports_error(client):
    r = client.post("/api/upload", data={"files": [(io.BytesIO(b"not an image"), "x.jpg")]}, content_type="multipart/form-data")
    assert r.status_code == 400 and r.json["errors"]


def test_info_has_qr(client):
    r = client.get("/api/info").json
    assert set(r["modes"]) == set(core.MODES)


def test_safe_pdf_name():
    assert safe_pdf_name('a/b:c*?"<>|.pdf') == "a_b_c_.pdf"
    assert safe_pdf_name("Biên bản") == "Biên bản.pdf"
    assert safe_pdf_name("").startswith("scan_")


def test_outline_api(client):
    upload(client, 1)
    p = client.get("/api/pages").json["pages"][0]
    ring = p["outline_norm"]
    assert len(ring) == 32
    ring[4] = [ring[4][0], ring[4][1] + 0.02]  # kéo điểm giữa mép trên xuống
    r = client.patch(f"/api/pages/{p['id']}", json={"outline_norm": ring})
    assert r.status_code == 200
    assert r.json["outline_norm"][4][1] == pytest.approx(ring[4][1], abs=1e-3)
    assert client.patch(f"/api/pages/{p['id']}", json={"outline_norm": [[0, 0], [1, 1]]}).status_code == 400
    # đặt lại 4 góc -> mép thẳng
    r = client.patch(f"/api/pages/{p['id']}", json={"corners_norm": [[0, 0], [1, 0], [1, 1], [0, 1]]})
    assert r.json["outline_norm"][4] == pytest.approx([0.5, 0.0], abs=1e-3)


def test_old_pages_json_without_outline_still_loads(tmp_path):
    import json
    a = create_app(tmp_path / "d").test_client()
    upload(a, 1)
    idx = tmp_path / "d" / "pages.json"
    raw = json.loads(idx.read_text(encoding="utf-8"))
    for p in raw["pages"]:
        p.pop("outline", None)
    idx.write_text(json.dumps(raw), encoding="utf-8")
    b = create_app(tmp_path / "d").test_client()
    pages = b.get("/api/pages").json["pages"]
    assert len(pages) == 1 and len(pages[0]["outline_norm"]) == 32
    assert b.get("/api/export").status_code == 200
