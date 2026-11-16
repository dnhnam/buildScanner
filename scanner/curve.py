"""Làm phẳng tờ giấy cong / gấp dựa trên 4 mép giấy cong.

Ý tưởng:
1. Từ khung 4 góc (đường thẳng), dò lại vị trí thật của mép giấy dọc theo từng
   cạnh -> mỗi cạnh là một đường cong qua N điểm điều khiển ("outline").
2. Nắn phối cảnh theo 4 góc để bỏ phần lớn độ nghiêng, rồi trong không gian đã
   nắn, "kéo căng" phần bên trong theo 4 mép cong thành hình chữ nhật
   (Coons patch). Chiều dài trang lấy theo chiều dài cung của mép, nên giấy
   cong không bị co lại.

Outline là một vòng điểm theo chiều kim đồng hồ bắt đầu từ góc trên-trái:
    trên (TL->TR), phải (TR->BR), dưới (BR->BL), trái (BL->TL)
mỗi cạnh có N_CTRL điểm (kể cả 2 góc), tổng cộng 4*(N_CTRL-1) điểm.
"""

from __future__ import annotations

from typing import Sequence

import cv2
import numpy as np

N_CTRL = 9                 # số điểm điều khiển mỗi cạnh (kể cả 2 góc)
REFINE_SIZE = 1200         # cạnh dài ảnh thu nhỏ dùng để dò mép
SEARCH_RATIO = 0.035       # dò mép trong khoảng ±3.5% kích thước ảnh quanh cạnh thẳng
SAMPLES_PER_EDGE = 64
MIN_EDGE_CONTRAST = 14     # chênh sáng tối thiểu giữa giấy và nền để tin là mép


# --------------------------------------------------------------------------- #
# Tiện ích cho outline
# --------------------------------------------------------------------------- #
def corner_indices(n: int = N_CTRL) -> list[int]:
    return [0, n - 1, 2 * (n - 1), 3 * (n - 1)]


def ring_size(n: int = N_CTRL) -> int:
    return 4 * (n - 1)


def straight_outline(corners: Sequence[Sequence[float]], n: int = N_CTRL) -> np.ndarray:
    """Outline có 4 cạnh thẳng nối 4 góc (TL, TR, BR, BL)."""
    c = np.asarray(corners, dtype=np.float64).reshape(4, 2)
    t = np.linspace(0, 1, n)[:-1, None]
    return np.vstack([c[k] + t * (c[(k + 1) % 4] - c[k]) for k in range(4)])


def edges_of(ring: np.ndarray, n: int | None = None) -> list[np.ndarray]:
    """Tách vòng điểm thành 4 cạnh, mỗi cạnh n điểm, theo chiều kim đồng hồ."""
    ring = np.asarray(ring, dtype=np.float64)
    n = n or len(ring) // 4 + 1
    closed = np.vstack([ring, ring[:1]])
    return [closed[k * (n - 1) : (k + 1) * (n - 1) + 1] for k in range(4)]


def corners_of(ring: np.ndarray) -> np.ndarray:
    ring = np.asarray(ring, dtype=np.float64)
    n = len(ring) // 4 + 1
    return ring[corner_indices(n)]


def resample_outline(ring: np.ndarray, n: int = N_CTRL) -> np.ndarray:
    """Đổi số điểm mỗi cạnh (dùng khi nhận outline có số điểm khác)."""
    out = []
    for e in edges_of(ring):
        dense = catmull_rom(e)
        s = _cumlen(dense)
        target = np.linspace(0, s[-1], n)[:-1]
        out.append(np.column_stack([np.interp(target, s, dense[:, 0]), np.interp(target, s, dense[:, 1])]))
    return np.vstack(out)


def catmull_rom(points: np.ndarray, per_seg: int = 24) -> np.ndarray:
    """Đường cong mượt đi qua đúng các điểm điều khiển (Catmull-Rom)."""
    p = np.asarray(points, dtype=np.float64)
    if len(p) < 3:
        t = np.linspace(0, 1, per_seg + 1)[:, None]
        return p[0] + t * (p[-1] - p[0])
    ext = np.vstack([2 * p[0] - p[1], p, 2 * p[-1] - p[-2]])
    t = np.linspace(0, 1, per_seg, endpoint=False)[:, None]
    t2, t3 = t * t, t * t * t
    segs = []
    for i in range(1, len(ext) - 2):
        p0, p1, p2, p3 = ext[i - 1], ext[i], ext[i + 1], ext[i + 2]
        segs.append(0.5 * (2 * p1 + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2 + (-p0 + 3 * p1 - 3 * p2 + p3) * t3))
    segs.append(p[-1:])
    return np.vstack(segs)


def _cumlen(pts: np.ndarray) -> np.ndarray:
    d = np.linalg.norm(np.diff(pts, axis=0), axis=1)
    return np.concatenate([[0.0], np.cumsum(d)])


# --------------------------------------------------------------------------- #
# Dò mép cong
# --------------------------------------------------------------------------- #
def _nan_median_filter(x: np.ndarray, half: int) -> np.ndarray:
    out = np.full_like(x, np.nan)
    for i in range(len(x)):
        win = x[max(0, i - half) : i + half + 1]
        win = win[~np.isnan(win)]
        if len(win):
            out[i] = np.median(win)
    return out


def _robust_offsets(raw: np.ndarray, t: np.ndarray) -> np.ndarray | None:
    """Lọc nhiễu (kẹp giấy, bóng, chữ sát mép) rồi làm mượt độ lệch dò được."""
    valid = ~np.isnan(raw)
    if valid.mean() < 0.4:
        return None
    med = _nan_median_filter(raw, 4)
    resid = raw - med
    mad = np.nanmedian(np.abs(resid)) * 1.4826
    good = valid & (np.abs(resid) <= max(3.0, 3.0 * mad))
    if good.mean() < 0.4:
        return None
    off = np.interp(t, t[good], raw[good])
    return np.convolve(np.pad(off, 2, mode="edge"), np.ones(5) / 5, mode="valid")


def refine_outline(img: np.ndarray, corners: Sequence[Sequence[float]], n: int = N_CTRL) -> np.ndarray:
    """Từ 4 góc (khung thẳng), tìm đường mép giấy thật ở mỗi cạnh.

    Với mỗi điểm mẫu trên cạnh thẳng, quét theo phương vuông góc tìm chỗ
    chuyển từ giấy (sáng, bên trong) sang nền (tối hơn, bên ngoài). Cạnh nào
    không đủ tương phản thì giữ thẳng.
    """
    corners = np.asarray(corners, dtype=np.float64).reshape(4, 2)
    h, w = img.shape[:2]
    s = min(1.0, REFINE_SIZE / max(h, w))
    small = cv2.resize(img, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA) if s < 1 else img
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY) if small.ndim == 3 else small
    gray = cv2.GaussianBlur(gray, (5, 5), 0).astype(np.float32)

    c = corners * s
    centroid = c.mean(axis=0)
    R = int(SEARCH_RATIO * max(gray.shape))
    IN0, IN1, OUT0, OUT1 = -8, -2, 2, 12  # cửa sổ trong / ngoài quanh vị trí thử
    steps = np.arange(-R + IN0, R + OUT1 + 1, dtype=np.float32)
    t = np.linspace(0.04, 0.96, SAMPLES_PER_EDGE)
    t_ctrl = np.linspace(0, 1, n)

    edge_offsets, normals = [], []
    for k in range(4):
        p0, p1 = c[k], c[(k + 1) % 4]
        tang = (p1 - p0) / max(np.linalg.norm(p1 - p0), 1e-6)
        nrm = np.array([tang[1], -tang[0]])
        if np.dot(nrm, (p0 + p1) / 2 - centroid) < 0:
            nrm = -nrm
        base = p0[None, :] + t[:, None] * (p1 - p0)[None, :]
        pts = base[:, None, :] + steps[None, :, None] * nrm[None, None, :]
        prof = cv2.remap(gray, pts[..., 0].astype(np.float32), pts[..., 1].astype(np.float32),
                         cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
        csum = np.concatenate([np.zeros((len(t), 1), np.float32), np.cumsum(prof, axis=1)], axis=1)

        def wmean(a, b, i0):  # trung bình prof[:, i0+a : i0+b] cho mọi vị trí
            return (csum[:, i0 + b + 1] - csum[:, i0 + a]) / (b - a + 1)

        scores = []
        for p in range(-R, R + 1):
            i0 = p - steps[0].astype(int)
            scores.append(wmean(IN0, IN1, int(i0)) - wmean(OUT0, OUT1, int(i0)))
        scores = np.stack(scores, axis=1)  # (mẫu, vị trí)
        best = scores.argmax(axis=1)
        raw = (best - R).astype(np.float64)
        raw[scores.max(axis=1) < MIN_EDGE_CONTRAST] = np.nan
        off = _robust_offsets(raw, t)
        edge_offsets.append(np.zeros(n) if off is None else np.interp(t_ctrl, t, off))
        normals.append(nrm)

    ring = []
    for k in range(4):
        p0, p1 = c[k], c[(k + 1) % 4]
        pts = p0 + t_ctrl[:, None] * (p1 - p0) + edge_offsets[k][:, None] * normals[k]
        ring.append(pts[:-1])
    ring = np.vstack(ring)
    # Góc = góc cũ dịch theo pháp tuyến của cả hai cạnh gặp nhau tại đó
    for k, idx in enumerate(corner_indices(n)):
        prev = (k - 1) % 4
        ring[idx] = c[k] + edge_offsets[k][0] * normals[k] + edge_offsets[prev][-1] * normals[prev]
    ring /= s
    ring[:, 0] = np.clip(ring[:, 0], 0, w - 1)
    ring[:, 1] = np.clip(ring[:, 1], 0, h - 1)
    return ring


# --------------------------------------------------------------------------- #
# Làm phẳng
# --------------------------------------------------------------------------- #
def _param_by_arclength(dense: np.ndarray, count: int) -> tuple[np.ndarray, float]:
    """Lấy `count` điểm cách đều theo chiều dài cung trên đường cong dày."""
    s = _cumlen(dense)
    target = np.linspace(0, s[-1], count)
    pts = np.column_stack([np.interp(target, s, dense[:, 0]), np.interp(target, s, dense[:, 1])])
    return pts.astype(np.float32), float(s[-1])


def warp_curved(img: np.ndarray, ring: np.ndarray) -> np.ndarray:
    """Nắn tờ giấy theo outline cong thành hình chữ nhật phẳng."""
    ring = np.asarray(ring, dtype=np.float64)
    top, right, bottom, left = edges_of(ring)
    tl, tr, br, bl = top[0], top[-1], bottom[0], bottom[-1]

    # Bước 1: nắn phối cảnh theo 4 góc
    # Lấy cạnh dài hơn (cạnh gần máy ảnh, ít bị co do phối cảnh): giữ đúng tỉ lệ trang hơn trung bình
    w0 = max(np.linalg.norm(tr - tl), np.linalg.norm(br - bl))
    h0 = max(np.linalg.norm(bl - tl), np.linalg.norm(br - tr))
    w0, h0 = max(w0, 2.0), max(h0, 2.0)
    rect = np.array([[0, 0], [w0, 0], [w0, h0], [0, h0]], dtype=np.float32)
    H = cv2.getPerspectiveTransform(np.float32([tl, tr, br, bl]), rect)
    Hinv = np.linalg.inv(H)

    def to_rect(pts):
        return cv2.perspectiveTransform(np.float32(pts)[None], H)[0].astype(np.float64)

    # Bước 2: 4 mép cong trong không gian đã nắn, lấy mẫu theo chiều dài cung
    top_d = catmull_rom(to_rect(top))
    bot_d = catmull_rom(to_rect(bottom[::-1]))   # BL -> BR
    left_d = catmull_rom(to_rect(left[::-1]))    # TL -> BL
    right_d = catmull_rom(to_rect(right))        # TR -> BR
    len_top = _cumlen(top_d)[-1]
    len_bot = _cumlen(bot_d)[-1]
    len_left = _cumlen(left_d)[-1]
    len_right = _cumlen(right_d)[-1]
    W = max(2, int(round((len_top + len_bot) / 2)))
    Hh = max(2, int(round((len_left + len_right) / 2)))

    T, _ = _param_by_arclength(top_d, W)
    B, _ = _param_by_arclength(bot_d, W)
    L, _ = _param_by_arclength(left_d, Hh)
    Rr, _ = _param_by_arclength(right_d, Hh)
    u = np.linspace(0, 1, W, dtype=np.float32)[None, :]
    v = np.linspace(0, 1, Hh, dtype=np.float32)[:, None]
    c00, c10, c11, c01 = rect  # TL, TR, BR, BL trong không gian đã nắn

    # Coons patch: nội suy phần bên trong từ 4 mép
    maps = []
    for d in (0, 1):
        val = ((1 - v) * T[None, :, d] + v * B[None, :, d]
               + (1 - u) * L[:, None, d] + u * Rr[:, None, d]
               - ((1 - u) * (1 - v) * c00[d] + u * (1 - v) * c10[d] + u * v * c11[d] + (1 - u) * v * c01[d]))
        maps.append(val.astype(np.float32))
    X, Y = maps

    # Bước 3: từ không gian đã nắn về ảnh gốc
    den = Hinv[2, 0] * X + Hinv[2, 1] * Y + Hinv[2, 2]
    mx = (Hinv[0, 0] * X + Hinv[0, 1] * Y + Hinv[0, 2]) / den
    my = (Hinv[1, 0] * X + Hinv[1, 1] * Y + Hinv[1, 2]) / den
    return cv2.remap(img, mx.astype(np.float32), my.astype(np.float32), cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
