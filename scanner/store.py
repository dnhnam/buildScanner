"""Lưu các trang đang quét trên đĩa (thư mục data/), giữ được khi tắt app."""

from __future__ import annotations

import json
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

import cv2
import numpy as np

from . import core, curve

ORIGINAL_MAX_SIDE = 4000   # ảnh gốc lưu lại tối đa 4000px (đủ cho A4 300 dpi)
PREVIEW_MAX_SIDE = 1400    # ảnh gốc thu nhỏ cho màn hình chỉnh góc
THUMB_MAX_SIDE = 480       # ảnh nhỏ trong lưới trang


@dataclass
class Page:
    id: str
    name: str
    created: float
    width: int
    height: int
    corners: list[list[float]]          # toạ độ pixel trên ảnh gốc đã lưu
    auto_found: bool                    # máy có tự tìm được khung giấy không
    mode: str = "color"
    rotation: int = 0
    rev: int = 0                        # tăng mỗi lần xử lý lại, để trình duyệt tải ảnh mới
    source: str = field(default="laptop")
    outline: list[list[float]] | None = None   # mép cong (xem scanner.curve); None = 4 cạnh thẳng

    def ring(self) -> np.ndarray:
        if self.outline:
            return np.asarray(self.outline, dtype=np.float64)
        return curve.straight_outline(self.corners)

    def set_ring(self, ring: np.ndarray) -> None:
        ring = np.asarray(ring, dtype=np.float64)
        ring[:, 0] = np.clip(ring[:, 0], 0, self.width - 1)
        ring[:, 1] = np.clip(ring[:, 1], 0, self.height - 1)
        self.outline = ring.round(1).tolist()
        self.corners = curve.corners_of(ring).round(1).tolist()

    def _norm(self, pts) -> list[list[float]]:
        return [[x / (self.width - 1), y / (self.height - 1)] for x, y in pts]

    def to_api(self) -> dict:
        d = asdict(self)
        d["corners_norm"] = self._norm(self.corners)
        d["outline_norm"] = self._norm(self.ring())
        return d


class PageStore:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.dirs = {k: self.root / k for k in ("originals", "previews", "processed", "thumbs")}
        for d in self.dirs.values():
            d.mkdir(parents=True, exist_ok=True)
        self.index_path = self.root / "pages.json"
        self.lock = threading.RLock()
        self.version = 0
        self.pages: list[Page] = []
        self._load()

    # ------------------------------------------------------------------ #
    def _load(self) -> None:
        if not self.index_path.exists():
            return
        try:
            raw = json.loads(self.index_path.read_text(encoding="utf-8"))
            self.pages = [Page(**p) for p in raw.get("pages", [])]
            self.pages = [p for p in self.pages if self.path("originals", p.id).exists()]
        except (ValueError, TypeError, KeyError):
            self.pages = []

    def _save(self) -> None:
        self.version += 1
        tmp = self.index_path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"pages": [asdict(p) for p in self.pages]}, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self.index_path)

    def path(self, kind: str, page_id: str) -> Path:
        return self.dirs[kind] / f"{page_id}.jpg"

    def get(self, page_id: str) -> Page:
        for p in self.pages:
            if p.id == page_id:
                return p
        raise KeyError(page_id)

    def list(self) -> list[dict]:
        with self.lock:
            return [p.to_api() for p in self.pages]

    # ------------------------------------------------------------------ #
    def add(self, data: bytes, name: str, source: str = "laptop", mode: str = "color") -> Page:
        """Nhận một ảnh mới: chuẩn hoá, tự dò khung, xử lý, lưu."""
        img = core.limit_size(core.load_image(data), ORIGINAL_MAX_SIDE)
        ring, found = core.detect_outline(img)
        corners = curve.corners_of(ring)
        h, w = img.shape[:2]
        page = Page(
            id=uuid.uuid4().hex[:12],
            name=name,
            created=time.time(),
            width=w,
            height=h,
            corners=corners.round(1).tolist(),
            auto_found=bool(found),
            mode=mode,
            source=source,
        )
        page.set_ring(ring)
        core.save_image(img, self.path("originals", page.id), quality=95)
        core.save_image(core.limit_size(img, PREVIEW_MAX_SIDE), self.path("previews", page.id), quality=85)
        self._render(page, img)
        with self.lock:
            self.pages.append(page)
            self._save()
        return page

    def update(
        self,
        page_id: str,
        *,
        corners_norm: list[list[float]] | None = None,
        outline_norm: list[list[float]] | None = None,
        mode: str | None = None,
        rotate_by: int | None = None,
        redetect: bool = False,
        full: bool = False,
    ) -> Page:
        with self.lock:
            page = self.get(page_id)
        img = None
        if redetect or full:
            img = self.original(page)
            if full:
                page.set_ring(curve.straight_outline(core.full_image_corners(img)))
                page.auto_found = True
            else:
                ring, found = core.detect_outline(img)
                page.set_ring(ring)
                page.auto_found = bool(found)
        if corners_norm is not None:
            pts = self._denorm(page, corners_norm)
            if pts.shape != (4, 2):
                raise ValueError("Cần đúng 4 góc")
            page.set_ring(curve.straight_outline(core.order_corners(pts)))
            page.auto_found = True
        if outline_norm is not None:
            pts = self._denorm(page, outline_norm)
            if len(pts) < 8 or len(pts) % 4:
                raise ValueError("Mép giấy không hợp lệ")
            if len(pts) != curve.ring_size():
                pts = curve.resample_outline(pts)
            page.set_ring(pts)
            page.auto_found = True
        if mode is not None:
            if mode not in core.MODES:
                raise ValueError(f"Chế độ không hợp lệ: {mode}")
            page.mode = mode
        if rotate_by:
            page.rotation = (page.rotation + rotate_by) % 360
        self._render(page, img)
        with self.lock:
            self._save()
        return page

    @staticmethod
    def _denorm(page: Page, pts_norm) -> np.ndarray:
        pts = np.clip(np.asarray(pts_norm, dtype=np.float64).reshape(-1, 2), 0.0, 1.0)
        pts[:, 0] *= page.width - 1
        pts[:, 1] *= page.height - 1
        return pts

    def set_mode_all(self, mode: str) -> None:
        for p in list(self.pages):
            if p.mode != mode:
                self.update(p.id, mode=mode)

    def reorder(self, ids: list[str]) -> None:
        with self.lock:
            by_id = {p.id: p for p in self.pages}
            ordered = [by_id.pop(i) for i in ids if i in by_id]
            self.pages = ordered + list(by_id.values())  # trang nào thiếu trong ids thì giữ ở cuối
            self._save()

    def delete(self, page_id: str) -> None:
        with self.lock:
            self.pages = [p for p in self.pages if p.id != page_id]
            self._save()
        for kind in self.dirs:
            self.path(kind, page_id).unlink(missing_ok=True)

    def clear(self) -> None:
        for p in list(self.pages):
            self.delete(p.id)

    # ------------------------------------------------------------------ #
    def original(self, page: Page) -> np.ndarray:
        return core.load_image(self.path("originals", page.id))

    def _render(self, page: Page, img: np.ndarray | None = None) -> None:
        if img is None:
            img = self.original(page)
        out = core.process(img, mode=page.mode, rotation=page.rotation, outline=page.ring())
        core.save_image(out, self.path("processed", page.id), quality=92)
        thumb = core.limit_size(out, THUMB_MAX_SIDE)
        if thumb.ndim == 2:
            thumb = cv2.cvtColor(thumb, cv2.COLOR_GRAY2BGR)
        core.save_image(thumb, self.path("thumbs", page.id), quality=80)
        page.rev += 1

    def export_pdf(self, page_size: str = "a4") -> bytes:
        with self.lock:
            pages = list(self.pages)
        blobs = []
        for p in pages:
            img = core.process(self.original(p), mode=p.mode, rotation=p.rotation, outline=p.ring())
            blobs.append(core.page_bytes(img, p.mode))
        return core.build_pdf(blobs, page_size)
