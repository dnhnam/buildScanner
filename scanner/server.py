"""Web server local: giao diện trên laptop + trang tải ảnh cho điện thoại."""

from __future__ import annotations

import ipaddress
import re
import secrets
import socket
from datetime import datetime
from functools import wraps
from io import BytesIO
from pathlib import Path

import qrcode
import qrcode.image.svg
from flask import Flask, abort, jsonify, render_template, request, send_file

from . import core
from .store import PageStore

MAX_UPLOAD_MB = 60


def lan_addresses() -> list[str]:
    """Các địa chỉ IPv4 trong mạng LAN của laptop, địa chỉ chính (theo route mặc định) đứng đầu."""
    found: list[str] = []
    try:  # Không gửi gói tin nào: connect UDP chỉ để hệ điều hành chọn card mạng
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            found.append(s.getsockname()[0])
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            found.append(info[4][0])
    except OSError:
        pass
    result = []
    for ip in found:
        addr = ipaddress.ip_address(ip)
        if ip not in result and addr.is_private and not addr.is_loopback and not addr.is_link_local:
            result.append(ip)
    return result


def safe_pdf_name(name: str) -> str:
    name = re.sub(r'[\\/:*?"<>|\r\n\t]+', "_", (name or "").strip()).strip(" .")
    if not name:
        name = "scan_" + datetime.now().strftime("%Y%m%d_%H%M%S")
    return name if name.lower().endswith(".pdf") else name + ".pdf"


def create_app(data_dir: Path, port: int = 8000) -> Flask:
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_MB * 1024 * 1024
    app.json.ensure_ascii = False
    store = PageStore(data_dir)
    token = secrets.token_urlsafe(8)  # mã ngẫu nhiên mỗi lần chạy, nằm trong mã QR
    app.config.update(STORE=store, TOKEN=token, PORT=port)

    def is_local() -> bool:
        return request.remote_addr in ("127.0.0.1", "::1")

    def has_token() -> bool:
        return secrets.compare_digest(request.args.get("t", "") or request.headers.get("X-Token", ""), token)

    def local_only(fn):
        """Chỉ laptop (localhost) được quản lý trang và xuất PDF; máy khác trong mạng thì không."""

        @wraps(fn)
        def wrapper(*a, **kw):
            if not is_local():
                abort(403)
            return fn(*a, **kw)

        return wrapper

    def json_error(msg: str, code: int = 400):
        return jsonify(error=msg), code

    # ------------------------------------------------------------------ pages
    @app.get("/")
    def desktop():
        if not is_local():
            if has_token():
                return render_template("mobile.html", token=token)
            abort(403)
        return render_template("desktop.html")

    @app.get("/m")
    def mobile():
        if not (is_local() or has_token()):
            return render_template("mobile_denied.html"), 403
        return render_template("mobile.html", token=token)

    # ------------------------------------------------------------------ API
    @app.get("/api/info")
    @local_only
    def info():
        ips = lan_addresses()
        urls = [f"http://{ip}:{port}/m?t={token}" for ip in ips]
        qr_svg = ""
        if urls:
            img = qrcode.make(urls[0], image_factory=qrcode.image.svg.SvgPathImage, box_size=10, border=2)
            buf = BytesIO()
            img.save(buf)
            qr_svg = buf.getvalue().decode("utf-8")
        return jsonify(urls=urls, qr_svg=qr_svg, modes=list(core.MODES))

    @app.get("/api/pages")
    @local_only
    def pages():
        return jsonify(version=store.version, pages=store.list())

    @app.post("/api/upload")
    def upload():
        if not (is_local() or has_token()):
            abort(403)
        files = request.files.getlist("files")
        if not files:
            return json_error("Không có file nào được gửi lên")
        mode = request.form.get("mode", "color")
        if mode not in core.MODES:
            mode = "color"
        added, errors = [], []
        for f in files:
            name = f.filename or "anh.jpg"
            try:
                page = store.add(f.read(), name, source="laptop" if is_local() else "phone", mode=mode)
                added.append(page.to_api())
            except Exception as exc:  # file hỏng / không phải ảnh
                errors.append({"name": name, "error": f"Không đọc được ảnh ({exc.__class__.__name__})"})
        return jsonify(added=added, errors=errors, total=len(store.pages)), (200 if added else 400)

    @app.patch("/api/pages/<page_id>")
    @local_only
    def update_page(page_id: str):
        body = request.get_json(silent=True) or {}
        try:
            page = store.update(
                page_id,
                corners_norm=body.get("corners_norm"),
                mode=body.get("mode"),
                rotate_by=int(body.get("rotate_by") or 0),
                redetect=bool(body.get("redetect")),
                full=bool(body.get("full")),
            )
        except KeyError:
            return json_error("Không tìm thấy trang", 404)
        except (ValueError, TypeError) as exc:
            return json_error(str(exc))
        return jsonify(page.to_api())

    @app.delete("/api/pages/<page_id>")
    @local_only
    def delete_page(page_id: str):
        store.delete(page_id)
        return jsonify(ok=True)

    @app.delete("/api/pages")
    @local_only
    def clear_pages():
        store.clear()
        return jsonify(ok=True)

    @app.post("/api/pages/order")
    @local_only
    def reorder():
        ids = (request.get_json(silent=True) or {}).get("ids") or []
        store.reorder([str(i) for i in ids])
        return jsonify(ok=True)

    @app.post("/api/pages/mode")
    @local_only
    def mode_all():
        mode = (request.get_json(silent=True) or {}).get("mode")
        if mode not in core.MODES:
            return json_error("Chế độ không hợp lệ")
        store.set_mode_all(mode)
        return jsonify(ok=True)

    @app.get("/files/<kind>/<page_id>.jpg")
    @local_only
    def page_file(kind: str, page_id: str):
        if kind not in ("previews", "processed", "thumbs") or not re.fullmatch(r"[0-9a-f]{12}", page_id):
            abort(404)
        path = store.path(kind, page_id)
        if not path.exists():
            abort(404)
        return send_file(path, mimetype="image/jpeg", max_age=0)

    @app.get("/api/export")
    @local_only
    def export():
        size = request.args.get("size", "a4")
        try:
            pdf = store.export_pdf(size)
        except ValueError as exc:
            return json_error(str(exc))
        return send_file(
            BytesIO(pdf),
            mimetype="application/pdf",
            as_attachment=True,
            download_name=safe_pdf_name(request.args.get("name", "")),
        )

    @app.errorhandler(413)
    def too_large(_):
        return json_error(f"File quá lớn (tối đa {MAX_UPLOAD_MB} MB mỗi lần gửi)", 413)

    return app
