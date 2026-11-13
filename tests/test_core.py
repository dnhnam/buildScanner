import re

import cv2
import numpy as np
import pytest

from scanner import core
from synth import make_photo

CASES = [
    dict(bg_color=(60, 90, 130), corners=None),                                                    # bàn gỗ, chụp xiên
    dict(bg_color=(30, 30, 30), corners=np.float32([[400, 300], [2600, 350], [2650, 3700], [350, 3650]])),  # nền đen, gần thẳng
    dict(bg_color=(150, 110, 70), corners=np.float32([[900, 600], [2200, 900], [2000, 3000], [700, 2700]])),  # giấy nhỏ, nghiêng nhiều
]


@pytest.mark.parametrize("case", CASES)
def test_detect_document_finds_paper(case):
    photo, truth = make_photo(**case)
    corners, found = core.detect_document(photo)
    assert found
    err = np.abs(corners - core.order_corners(truth)).max()
    assert err < 40, f"lệch {err}px"


def test_detect_document_falls_back_to_full_image():
    noise = np.random.default_rng(1).integers(100, 140, (1200, 900, 3), dtype=np.uint8)
    corners, found = core.detect_document(noise)
    assert not found
    assert np.array_equal(corners, core.full_image_corners(noise))


def test_order_corners():
    pts = np.float32([[100, 90], [5, 100], [0, 0], [110, 2]])
    assert core.order_corners(pts).tolist() == [[0, 0], [110, 2], [100, 90], [5, 100]]


@pytest.mark.parametrize("mode", core.MODES)
def test_process_modes(mode):
    photo, truth = make_photo()
    out = core.process(photo, truth, mode, rotation=90)
    h, w = out.shape[:2]
    assert w > h  # đã xoay 90 độ: trang dọc thành ngang
    if mode in ("gray", "bw"):
        assert out.ndim == 2
    if mode == "bw":
        assert set(np.unique(out)) <= {0, 255}
    if mode in ("color", "gray", "bw"):
        # nền giấy sau khi làm sạch phải gần trắng tuyệt đối, kể cả góc bị tối
        corner = out[h // 2 - 40 : h // 2, w - 120 : w - 40] if mode != "original" else None
        assert np.median(corner) >= 245


def test_cleaned_page_has_no_dark_background_border():
    photo, _ = make_photo()
    corners, _ = core.detect_document(photo)
    out = core.process(photo, corners, "gray")
    for edge in (out[:3], out[-3:], out[:, :3], out[:, -3:]):
        assert np.mean(edge) > 200


def test_unicode_paths(tmp_path):
    photo, _ = make_photo(size=(800, 1000), corners=np.float32([[100, 100], [700, 120], [690, 900], [110, 880]]))
    path = tmp_path / "ảnh hợp đồng.jpg"
    core.save_image(photo, path)
    assert core.load_image(path).shape == photo.shape


def test_build_pdf_a4():
    photo, truth = make_photo()
    pages = [core.page_bytes(core.process(photo, truth, m), m) for m in ("color", "bw")]
    pdf = core.build_pdf(pages, "a4")
    assert pdf.startswith(b"%PDF")
    assert len(re.findall(rb"/Type\s*/Page\b", pdf)) == 2
    assert b"595.2" in pdf and b"841.8" in pdf  # A4 = 595.28 x 841.89 pt


def test_build_pdf_rejects_empty():
    with pytest.raises(ValueError):
        core.build_pdf([])
