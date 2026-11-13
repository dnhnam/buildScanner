"""Chạy buildScanner: python app.py  (hoặc nhấp đúp run.bat trên Windows)."""

from __future__ import annotations

import argparse
import sys
import threading
import webbrowser
from pathlib import Path

from scanner.server import create_app, lan_addresses

BASE = Path(__file__).resolve().parent


def main() -> None:
    for stream in (sys.stdout, sys.stderr):  # tránh lỗi in tiếng Việt trên console Windows cũ
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    ap = argparse.ArgumentParser(description="buildScanner: quét tài liệu từ điện thoại thành PDF (local).")
    ap.add_argument("--port", type=int, default=8000, help="cổng web (mặc định 8000)")
    ap.add_argument("--data", type=Path, default=BASE / "data", help="thư mục lưu ảnh đang quét")
    ap.add_argument("--no-browser", action="store_true", help="không tự mở trình duyệt")
    args = ap.parse_args()

    app = create_app(args.data, args.port)
    local_url = f"http://localhost:{args.port}"

    print("=" * 60)
    print(" buildScanner đang chạy")
    print(f"  Trên laptop:     {local_url}")
    for ip in lan_addresses():
        print(f"  Điện thoại:      http://{ip}:{args.port}/m?t={app.config['TOKEN']}")
    print("  (Quét mã QR trên trang laptop cho nhanh. Điện thoại và laptop phải cùng Wi-Fi.)")
    print("  Nếu Windows hỏi tường lửa: chọn 'Allow' cho mạng Private.")
    print("  Nhấn Ctrl+C để tắt.")
    print("=" * 60, flush=True)

    if not args.no_browser:
        threading.Timer(1.0, webbrowser.open, args=(local_url,)).start()

    from waitress import serve

    serve(app, host="0.0.0.0", port=args.port, threads=8, max_request_body_size=app.config["MAX_CONTENT_LENGTH"])


if __name__ == "__main__":
    main()
