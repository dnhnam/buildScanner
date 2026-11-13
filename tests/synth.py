"""Tạo ảnh giả lập: tờ giấy có chữ, chụp xiên trên mặt bàn, ánh sáng không đều."""
import cv2
import numpy as np


def make_page(w=1240, h=1754):
    page = np.full((h, w, 3), 245, np.uint8)
    for i, y in enumerate(range(150, h - 150, 60)):
        cv2.putText(page, f"Dong van ban so {i + 1} - Lorem ipsum dolor sit amet", (100, y),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.2, (30, 30, 30), 2, cv2.LINE_AA)
    cv2.circle(page, (w - 250, h - 250), 120, (40, 40, 200), 6)  # "con dấu" đỏ
    return page


def make_photo(bg_color=(60, 90, 130), corners=None, size=(3000, 4000), seed=0):
    rng = np.random.default_rng(seed)
    W, H = size
    page = make_page()
    ph, pw = page.shape[:2]
    if corners is None:
        corners = np.float32([[620, 520], [2380, 700], [2520, 3500], [480, 3380]])
    m = cv2.getPerspectiveTransform(np.float32([[0, 0], [pw, 0], [pw, ph], [0, ph]]), corners)
    bg = np.zeros((H, W, 3), np.float32) + np.float32(bg_color)
    bg += rng.normal(0, 8, (H, W, 1)).astype(np.float32)  # vân bàn
    photo = cv2.warpPerspective(page, m, (W, H), dst=bg.astype(np.uint8), borderMode=cv2.BORDER_TRANSPARENT)
    # ánh sáng không đều: tối dần về góc dưới phải
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    light = 1.0 - 0.35 * (xx / W + yy / H) / 2
    photo = np.clip(photo.astype(np.float32) * light[..., None], 0, 255).astype(np.uint8)
    return photo, corners
