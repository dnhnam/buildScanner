import cv2
import numpy as np

from scanner import core, curve
from synth import make_curved_photo, make_page, make_photo


def text_line_bow(img):
    """Độ võng lớn nhất (px) của các dòng chữ dài sau khi làm phẳng."""
    g = img if img.ndim == 2 else cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    bw = (g < 128).astype(np.uint8) * 255
    bw = cv2.morphologyEx(bw, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (25, 5)))
    n, lab, st, _ = cv2.connectedComponentsWithStats(bw)
    bows = []
    for i in range(1, n):
        if st[i][2] < g.shape[1] * 0.4 or st[i][3] > g.shape[0] * 0.05:
            continue
        ys, xs = np.nonzero(lab == i)
        p1, p2 = np.polyfit(xs, ys, 1), np.polyfit(xs, ys, 2)
        t = np.linspace(xs.min(), xs.max(), 50)
        bows.append(np.abs(np.polyval(p2, t) - np.polyval(p1, t)).max())
    assert len(bows) >= 10, "phải đo được các dòng chữ"
    return float(np.median(bows))


def test_straight_outline_roundtrip():
    c = np.array([[10, 20], [300, 25], [310, 400], [5, 390]], float)
    ring = curve.straight_outline(c)
    assert ring.shape == (curve.ring_size(), 2)
    assert np.allclose(curve.corners_of(ring), c)
    assert all(len(e) == curve.N_CTRL for e in curve.edges_of(ring))


def test_warp_curved_matches_perspective_for_straight_edges():
    photo, truth = make_photo()
    a = core.warp(photo, truth)
    b = curve.warp_curved(photo, curve.straight_outline(core.order_corners(truth)))
    true_ratio = 1240 / 1754  # tỉ lệ trang gốc trong ảnh giả lập
    assert abs(b.shape[1] / b.shape[0] - true_ratio) < 0.015
    assert abs(a.shape[0] - b.shape[0]) < 0.02 * a.shape[0] and abs(a.shape[1] - b.shape[1]) < 0.02 * a.shape[1]
    b = cv2.resize(b, (a.shape[1], a.shape[0]), interpolation=cv2.INTER_LINEAR)
    diff = np.abs(cv2.GaussianBlur(a, (5, 5), 0).astype(int) - cv2.GaussianBlur(b, (5, 5), 0).astype(int))
    assert np.median(diff) < 3 and np.percentile(diff, 95) < 25


def test_refine_outline_follows_curved_edge():
    photo, amp = make_curved_photo(amp=60)
    corners, found = core.detect_document(photo)
    assert found
    ring = curve.refine_outline(photo, corners)
    top = curve.edges_of(ring)[0]
    straight = curve.edges_of(curve.straight_outline(curve.corners_of(ring)))[0]
    mid = curve.N_CTRL // 2
    sag = top[mid, 1] - straight[mid, 1]
    assert sag > 0.6 * amp, f"mép trên phải võng xuống ~{amp}px, đo được {sag:.1f}"


def test_curved_paper_is_flattened():
    photo, _ = make_curved_photo(amp=60)
    corners, _ = core.detect_document(photo)
    flat_old = core.process(photo, corners=corners, mode="gray")
    ring, _ = core.detect_outline(photo)
    flat_new = core.process(photo, mode="gray", outline=ring)
    bow_old, bow_new = text_line_bow(flat_old), text_line_bow(flat_new)
    assert bow_new < 0.35 * bow_old, f"cũ {bow_old:.1f}px, mới {bow_new:.1f}px"
    assert bow_new < 8


def test_flat_paper_is_not_distorted():
    photo, truth = make_photo()
    ring, found = core.detect_outline(photo)
    assert found
    straight = curve.straight_outline(curve.corners_of(ring))
    assert np.abs(ring - straight).max() < 15


def test_dark_blocks_are_not_whitened():
    page = make_page()
    page[300:900, 100:500] = 85  # ô tô xám đậm lớn, như bảng biểu mẫu ngân hàng
    yy, xx = np.mgrid[0:page.shape[0], 0:page.shape[1]]
    shade = (1 - 0.3 * xx / page.shape[1])[..., None]  # ánh sáng không đều
    img = (page * shade).astype(np.uint8)
    out = core.enhance(img, "gray")
    block = out[350:850, 150:450]
    assert block.mean() < 160 and block.std() < 25, "ô xám phải giữ màu xám đều, không bị loang trắng"
    paper = out[1000:1100, 900:1100]
    assert np.median(paper) >= 245
