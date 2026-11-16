"""Quét hàng loạt bằng dòng lệnh, không cần mở giao diện.

Ví dụ:
    python scan_cli.py C:\\Users\\ban\\Pictures\\hopdong -o hopdong.pdf
    python scan_cli.py anh1.jpg anh2.jpg anh3.jpg -o ketqua.pdf --mode bw
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from scanner import core


def natural_key(p: Path):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", p.name)]


def collect(inputs: list[Path]) -> list[Path]:
    files: list[Path] = []
    for item in inputs:
        if item.is_dir():
            files += sorted((f for f in item.iterdir() if f.suffix.lower() in core.SUPPORTED_EXT), key=natural_key)
        elif item.is_file():
            files.append(item)
        else:
            print(f"! Bỏ qua (không tồn tại): {item}", file=sys.stderr)
    return files


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    ap = argparse.ArgumentParser(description="Chuyển ảnh chụp tài liệu thành một file PDF.")
    ap.add_argument("inputs", nargs="+", type=Path, help="file ảnh hoặc thư mục chứa ảnh (sắp theo tên)")
    ap.add_argument("-o", "--output", type=Path, default=Path("scan.pdf"), help="file PDF đầu ra")
    ap.add_argument("--mode", choices=core.MODES, default="color",
                    help="color: nền trắng giữ màu | gray: xám | bw: đen trắng | original: không chỉnh màu")
    ap.add_argument("--page", choices=["a4", "letter", "auto"], default="a4", help="khổ trang PDF")
    ap.add_argument("--no-crop", action="store_true", help="không tự cắt khung giấy, giữ toàn ảnh")
    ap.add_argument("--save-images", type=Path, help="lưu thêm từng trang đã xử lý vào thư mục này")
    args = ap.parse_args()

    files = collect(args.inputs)
    if not files:
        print("Không tìm thấy ảnh nào.", file=sys.stderr)
        return 1
    if args.save_images:
        args.save_images.mkdir(parents=True, exist_ok=True)

    pages = []
    for i, f in enumerate(files, 1):
        try:
            img = core.load_image(f)
        except Exception as exc:
            print(f"! [{i}/{len(files)}] {f.name}: không đọc được ({exc})", file=sys.stderr)
            continue
        if args.no_crop:
            out, found = core.process(img, core.full_image_corners(img), args.mode), True
        else:
            ring, found = core.detect_outline(img)
            out = core.process(img, mode=args.mode, outline=ring)
        pages.append(core.page_bytes(out, args.mode))
        note = "" if found else "  (không thấy khung giấy, giữ toàn ảnh)"
        print(f"  [{i}/{len(files)}] {f.name}{note}")
        if args.save_images:
            core.save_image(out, args.save_images / f"{i:03d}_{f.stem}.jpg")

    if not pages:
        return 1
    args.output.write_bytes(core.build_pdf(pages, args.page))
    print(f"Đã tạo {args.output} ({len(pages)} trang)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
