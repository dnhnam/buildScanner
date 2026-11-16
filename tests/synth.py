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


def make_curved_photo(amp=60, size=(2400, 3200), bg_color=(70, 95, 125)):
    """Tờ giấy bị cong (mép trên/dưới và các dòng chữ võng xuống hình cung), hơi xiên.

    Trả về (ảnh, độ võng tính bằng px).
    """
    W, H = size
    page = make_page()
    ph, pw = page.shape[:2]
    # vị trí trang trong ảnh: hình thang nhẹ
    corners = np.float32([[420, 380], [1980, 420], [2040, 2850], [360, 2800]])
    M = cv2.getPerspectiveTransform(np.float32([[0, 0], [pw, 0], [pw, ph], [0, ph]]), corners)
    Minv = np.linalg.inv(M)
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    # Với mỗi điểm ảnh đích, tìm điểm trên trang: trước hết bỏ phối cảnh, rồi bỏ độ võng
    den = Minv[2, 0] * xx + Minv[2, 1] * yy + Minv[2, 2]
    u = (Minv[0, 0] * xx + Minv[0, 1] * yy + Minv[0, 2]) / den
    v = (Minv[1, 0] * xx + Minv[1, 1] * yy + Minv[1, 2]) / den
    px_per_page = (corners[1, 0] - corners[0, 0]) / pw  # px ảnh trên 1 px trang
    sag = amp / px_per_page * np.sin(np.pi * np.clip(u / pw, 0, 1))  # võng nhiều nhất ở giữa bề ngang
    v_src = v - sag
    bg = np.zeros((H, W, 3), np.uint8) + np.uint8(bg_color)
    photo = cv2.remap(page, u.astype(np.float32), v_src.astype(np.float32), cv2.INTER_LINEAR)
    inside = (u >= 0) & (u < pw) & (v_src >= 0) & (v_src < ph)
    photo[~inside] = bg[~inside]
    return photo, amp
