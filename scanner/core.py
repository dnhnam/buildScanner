"""Lõi xử lý ảnh: tìm khung giấy, nắn phối cảnh, làm sạch nền, xuất PDF.

Mọi thao tác đọc/ghi file đi qua Pillow hoặc cv2.imencode/imdecode thay vì
cv2.imread/imwrite, vì hai hàm này không đọc được đường dẫn có dấu tiếng Việt
trên Windows.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Iterable, Sequence

import cv2
import img2pdf
import numpy as np
from PIL import Image, ImageOps

try:  # Ảnh HEIC chụp từ iPhone (khi chép file trực tiếp sang laptop)
    from pillow_heif import register_heif_opener

    register_heif_opener()
except ImportError:  # pragma: no cover - thư viện tuỳ chọn
    pass

MODES = ("color", "gray", "bw", "original")
PAGE_SIZES = {
    "a4": (img2pdf.mm_to_pt(210), img2pdf.mm_to_pt(297)),
    "letter": (img2pdf.in_to_pt(8.5), img2pdf.in_to_pt(11)),
}
SUPPORTED_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff", ".heic", ".heif"}

DETECT_SIZE = 800          # cạnh dài của ảnh thu nhỏ dùng để dò khung
MAX_OUTPUT_SIDE = 3508     # A4 ở 300 dpi
MIN_AREA_RATIO = 0.15      # khung giấy phải chiếm ít nhất 15% ảnh


# --------------------------------------------------------------------------- #
# Đọc / ghi ảnh
# --------------------------------------------------------------------------- #
def load_image(source: str | Path | bytes) -> np.ndarray:
    """Đọc ảnh (đường dẫn hoặc bytes) thành mảng BGR, đã xoay theo EXIF."""
    fp = io.BytesIO(source) if isinstance(source, (bytes, bytearray)) else source
    with Image.open(fp) as im:
        im = ImageOps.exif_transpose(im)
        im = im.convert("RGB")
        rgb = np.asarray(im)
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)


def encode_image(img: np.ndarray, fmt: str = ".jpg", quality: int = 90) -> bytes:
    params = [cv2.IMWRITE_JPEG_QUALITY, quality] if fmt == ".jpg" else []
    ok, buf = cv2.imencode(fmt, img, params)
    if not ok:
        raise ValueError("Không mã hoá được ảnh")
    return buf.tobytes()


def save_image(img: np.ndarray, path: str | Path, quality: int = 90) -> None:
    path = Path(path)
    path.write_bytes(encode_image(img, path.suffix.lower() or ".jpg", quality))


# --------------------------------------------------------------------------- #
# Tìm khung giấy
# --------------------------------------------------------------------------- #
def order_corners(pts: np.ndarray) -> np.ndarray:
    """Sắp 4 điểm theo thứ tự: trên-trái, trên-phải, dưới-phải, dưới-trái."""
    pts = np.asarray(pts, dtype=np.float32).reshape(4, 2)
    s = pts.sum(axis=1)
    d = np.diff(pts, axis=1).ravel()  # y - x
    return np.array(
        [pts[np.argmin(s)], pts[np.argmin(d)], pts[np.argmax(s)], pts[np.argmax(d)]],
        dtype=np.float32,
    )


def full_image_corners(img: np.ndarray) -> np.ndarray:
    h, w = img.shape[:2]
    return np.array([[0, 0], [w - 1, 0], [w - 1, h - 1], [0, h - 1]], dtype=np.float32)


def _quad_from_contour(cnt: np.ndarray) -> np.ndarray | None:
    peri = cv2.arcLength(cnt, True)
    for eps in (0.02, 0.03, 0.04, 0.05):
        approx = cv2.approxPolyDP(cnt, eps * peri, True)
        if len(approx) == 4 and cv2.isContourConvex(approx):
            return approx.reshape(4, 2).astype(np.float32)
    # Không ra tứ giác gọn (góc giấy bị quăn, bị che): dùng bao lồi + minAreaRect
    hull = cv2.convexHull(cnt)
    approx = cv2.approxPolyDP(hull, 0.02 * cv2.arcLength(hull, True), True)
    if len(approx) == 4:
        return approx.reshape(4, 2).astype(np.float32)
    return None


def _candidate_masks(gray: np.ndarray) -> Iterable[np.ndarray]:
    """Sinh các ảnh nhị phân khác nhau để dò viền giấy, từ chắc chắn đến dự phòng."""
    # Đóng hình thái học để xoá chữ, chỉ còn mảng giấy
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (9, 9))
    closed = cv2.morphologyEx(gray, cv2.MORPH_CLOSE, kernel, iterations=2)
    blur = cv2.GaussianBlur(closed, (5, 5), 0)

    # 1) Cạnh Canny với ngưỡng tự động theo trung vị
    med = float(np.median(blur))
    lo, hi = int(max(0, 0.66 * med)), int(min(255, 1.33 * med))
    edges = cv2.Canny(blur, lo, hi)
    yield cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=2)

    # 2) Canny ngưỡng cố định (ảnh tương phản thấp)
    edges = cv2.Canny(blur, 30, 90)
    yield cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=2)

    # 3) Otsu: giấy thường sáng hơn nền
    _, otsu = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    yield cv2.morphologyEx(otsu, cv2.MORPH_OPEN, kernel)


def detect_document(img: np.ndarray) -> tuple[np.ndarray, bool]:
    """Trả về (4 góc theo toạ độ ảnh gốc, có_tìm_thấy_hay_không).

    Nếu không tìm được khung hợp lệ, trả về 4 góc của toàn ảnh.
    """
    h, w = img.shape[:2]
    scale = DETECT_SIZE / max(h, w)
    small = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA) if scale < 1 else img
    scale = min(scale, 1.0)
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    sh, sw = gray.shape
    img_area = sh * sw

    best: np.ndarray | None = None
    best_area = 0.0
    for mask in _candidate_masks(gray):
        contours, _ = cv2.findContours(mask, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        for cnt in sorted(contours, key=cv2.contourArea, reverse=True)[:5]:
            if cv2.contourArea(cnt) < MIN_AREA_RATIO * img_area:
                break
            quad = _quad_from_contour(cnt)
            if quad is None:
                continue
            area = cv2.contourArea(quad)
            # Bỏ qua khung trùng gần hết viền ảnh (thường là viền khung hình, không phải giấy)
            if area > 0.98 * img_area:
                continue
            if area > best_area:
                best, best_area = quad, area
        if best is not None:
            break

    if best is None:
        return full_image_corners(img), False
    corners = order_corners(best / scale)
    corners[:, 0] = np.clip(corners[:, 0], 0, w - 1)
    corners[:, 1] = np.clip(corners[:, 1], 0, h - 1)
    return corners, True


# --------------------------------------------------------------------------- #
# Nắn phối cảnh và làm sạch
# --------------------------------------------------------------------------- #
def warp(img: np.ndarray, corners: Sequence[Sequence[float]]) -> np.ndarray:
    src = order_corners(np.asarray(corners, dtype=np.float32))
    tl, tr, br, bl = src
    width = int(round(max(np.linalg.norm(tr - tl), np.linalg.norm(br - bl))))
    height = int(round(max(np.linalg.norm(bl - tl), np.linalg.norm(br - tr))))
    width, height = max(width, 1), max(height, 1)
    dst = np.array([[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]], dtype=np.float32)
    m = cv2.getPerspectiveTransform(src, dst)
    return cv2.warpPerspective(img, m, (width, height), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)


def _background(channel: np.ndarray) -> np.ndarray:
    """Ước lượng nền giấy (ánh sáng không đều, bóng đổ) bằng cách xoá chữ rồi làm mờ.

    Tính trên ảnh thu nhỏ cho nhanh rồi phóng lại.
    """
    h, w = channel.shape
    f = 600 / max(h, w)
    small = cv2.resize(channel, (max(1, int(w * f)), max(1, int(h * f))), interpolation=cv2.INTER_AREA) if f < 1 else channel
    bg = cv2.dilate(small, np.ones((7, 7), np.uint8))
    bg = cv2.medianBlur(bg, 21)
    return cv2.resize(bg, (w, h), interpolation=cv2.INTER_LINEAR)


def _flatten(channel: np.ndarray) -> np.ndarray:
    bg = _background(channel).astype(np.float32)
    out = channel.astype(np.float32) / np.maximum(bg, 1.0) * 255.0
    return np.clip(out, 0, 255).astype(np.uint8)


def _levels(img: np.ndarray, black: int = 30, white: int = 225) -> np.ndarray:
    """Kéo vùng gần trắng thành trắng hẳn, chữ đậm hơn."""
    lut = np.clip((np.arange(256) - black) * 255.0 / (white - black), 0, 255).astype(np.uint8)
    return cv2.LUT(img, lut)


def enhance(img: np.ndarray, mode: str = "color") -> np.ndarray:
    """Làm sạch ảnh đã nắn.

    - color:    nền trắng, giữ màu (con dấu đỏ, chữ ký xanh)
    - gray:     nền trắng, thang xám
    - bw:       đen trắng thuần, file nhẹ nhất
    - original: không xử lý màu
    """
    if mode == "original":
        return img
    if mode == "color":
        channels = [_flatten(c) for c in cv2.split(img)]
        return _levels(cv2.merge(channels))
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    flat = _flatten(gray)
    if mode == "gray":
        return _levels(flat)
    if mode == "bw":
        block = max(15, (min(gray.shape) // 40) | 1)  # số lẻ, tỉ lệ theo kích thước ảnh
        bw = cv2.adaptiveThreshold(flat, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, block, 15)
        return cv2.medianBlur(bw, 3)
    raise ValueError(f"Chế độ không hợp lệ: {mode!r}. Chọn một trong {MODES}")


def rotate(img: np.ndarray, degrees: int) -> np.ndarray:
    degrees %= 360
    if degrees == 90:
        return cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
    if degrees == 180:
        return cv2.rotate(img, cv2.ROTATE_180)
    if degrees == 270:
        return cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)
    return img


def trim_border(img: np.ndarray, ratio: float = 0.006) -> np.ndarray:
    """Cắt bỏ một dải mỏng quanh mép để không sót viền nền bàn sau khi nắn."""
    h, w = img.shape[:2]
    t = int(round(ratio * min(h, w)))
    if t == 0 or h <= 4 * t or w <= 4 * t:
        return img
    return img[t : h - t, t : w - t]


def limit_size(img: np.ndarray, max_side: int = MAX_OUTPUT_SIDE) -> np.ndarray:
    h, w = img.shape[:2]
    if max(h, w) <= max_side:
        return img
    f = max_side / max(h, w)
    return cv2.resize(img, (int(w * f), int(h * f)), interpolation=cv2.INTER_AREA)


def process(
    img: np.ndarray,
    corners: Sequence[Sequence[float]] | None = None,
    mode: str = "color",
    rotation: int = 0,
) -> np.ndarray:
    """Toàn bộ quy trình cho một trang: (dò khung) → nắn → làm sạch → xoay."""
    if corners is None:
        corners, _ = detect_document(img)
    out = trim_border(warp(img, corners))
    out = limit_size(out)
    out = enhance(out, mode)
    return rotate(out, rotation)


# --------------------------------------------------------------------------- #
# PDF
# --------------------------------------------------------------------------- #
def page_bytes(img: np.ndarray, mode: str) -> bytes:
    """Mã hoá một trang để nhúng vào PDF: đen trắng → PNG 1-bit, còn lại → JPEG."""
    if mode == "bw":
        buf = io.BytesIO()
        Image.fromarray(img if img.ndim == 2 else cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)).convert("1").save(buf, "PNG")
        return buf.getvalue()
    return encode_image(img, ".jpg", 88)


def build_pdf(pages: Sequence[bytes], page_size: str = "a4") -> bytes:
    """Ghép các trang (bytes JPEG/PNG) thành một PDF.

    page_size: "a4", "letter" (ảnh được co vừa trang, tự xoay ngang/dọc)
               hoặc "auto" (trang có kích thước theo ảnh, ở 300 dpi).
    """
    if not pages:
        raise ValueError("Chưa có trang nào để xuất PDF")
    if page_size == "auto":
        layout = img2pdf.get_fixed_dpi_layout_fun((300, 300))
    else:
        size = PAGE_SIZES.get(page_size)
        if size is None:
            raise ValueError(f"Khổ giấy không hợp lệ: {page_size!r}")
        layout = img2pdf.get_layout_fun(size, fit=img2pdf.FitMode.into, auto_orient=True)
    return img2pdf.convert(list(pages), layout_fun=layout)
