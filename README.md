# buildScanner

Chuyển ảnh chụp tài liệu từ điện thoại thành một file PDF sạch, giống CamScanner, chạy **hoàn toàn trên laptop**. Không cần internet, không gửi ảnh lên cloud.

- Điện thoại quét mã QR để chụp và gửi ảnh qua Wi-Fi sang laptop, không cần cài app.
- Tự tìm khung tờ giấy, cắt bỏ nền xung quanh và nắn phẳng ảnh chụp xiên.
- Làm trắng nền, xoá bóng đổ và vùng tối, chữ rõ hơn.
- Kéo chỉnh 4 góc bằng tay khi máy nhận sai (có kính lúp phóng to).
- Xoay trang, đổi thứ tự bằng kéo thả, chọn chế độ màu từng trang.
- Gộp tất cả thành **một file PDF** (khổ A4, Letter hoặc theo ảnh).

## Cài đặt trên Windows

1. Cài **Python 3.10 trở lên** từ <https://www.python.org/downloads/>. Khi cài, **tick ô "Add python.exe to PATH"**.
2. Tải thư mục này về máy, ví dụ `C:\buildScanner`.
3. Nhấp đúp **`run.bat`**.
   - Lần đầu, file sẽ tự tạo môi trường và cài thư viện (mất vài phút, cần internet **một lần duy nhất**).
   - Những lần sau app mở ngay và chạy offline.
4. Trình duyệt sẽ tự mở trang `http://localhost:8000`.
5. Nếu Windows Defender hỏi về tường lửa, chọn **Allow** cho mạng **Private**. Không cho phép thì điện thoại sẽ không kết nối được.

## Cách dùng

1. **Gửi ảnh**
   - *Từ điện thoại:* mở camera, quét mã QR trên màn hình laptop, rồi bấm **Chụp trang mới** hoặc **Chọn ảnh có sẵn**. Điện thoại phải dùng **chung Wi-Fi** với laptop.
   - *Từ laptop:* kéo thả ảnh vào khung bên trái (hỗ trợ JPG, PNG, HEIC của iPhone, WEBP, TIFF…).
2. **Kiểm tra từng trang.** Trang nào có dòng vàng "Không tìm thấy khung giấy", hoặc cắt chưa đúng, thì bấm **Chỉnh góc** rồi kéo 4 chấm vào 4 góc tờ giấy.
3. Chọn **chế độ màu**:
   | Chế độ | Dùng khi |
   |---|---|
   | Màu, nền trắng (mặc định) | Giấy tờ có con dấu đỏ, chữ ký xanh, logo màu |
   | Xám | Văn bản thường |
   | Đen trắng | Văn bản thuần chữ, file PDF nhẹ nhất |
   | Giữ nguyên màu | Ảnh, tài liệu nhiều hình |
4. Kéo thả để sắp xếp thứ tự trang, nhập tên file, bấm **Xuất PDF**. File được lưu vào thư mục *Downloads*.

Các trang đang làm được lưu trong thư mục `data\`. Tắt app rồi mở lại vẫn còn, cho đến khi bấm **Xoá tất cả trang**.

### Mẹo chụp để máy tự cắt chuẩn

- Đặt giấy trên **nền tối hơn giấy** (bàn gỗ, bìa sẫm màu). Giấy trắng trên bàn trắng là khó nhận nhất.
- Chụp **đủ cả 4 góc** tờ giấy, để giấy chiếm phần lớn khung hình.
- Đủ sáng, tránh bóng tay và bóng điện thoại đè lên giấy.

## Quét hàng loạt bằng dòng lệnh

Khi đã có sẵn một thư mục ảnh và không cần chỉnh tay:

```bat
scan.bat C:\Users\ban\Pictures\hopdong -o hopdong.pdf
scan.bat anh1.jpg anh2.jpg anh3.jpg -o ketqua.pdf --mode bw
```

Ảnh trong thư mục được sắp theo tên (`trang2` đứng trước `trang10`). Các tuỳ chọn:

- `--mode`: `color`, `gray`, `bw` hoặc `original`
- `--page`: `a4`, `letter` hoặc `auto`
- `--no-crop`: không cắt khung
- `--save-images <thư mục>`: lưu thêm từng trang đã xử lý thành ảnh

(Chạy `run.bat` một lần trước để cài thư viện.)

## Tuỳ chọn khi chạy app

```bat
run.bat --port 9000        :: đổi cổng nếu 8000 đang bận
run.bat --no-browser       :: không tự mở trình duyệt
run.bat --data D:\scan     :: lưu ảnh đang làm ở chỗ khác
```

## Xử lý sự cố

| Hiện tượng | Cách xử lý |
|---|---|
| Điện thoại không mở được trang | Kiểm tra hai máy cùng Wi-Fi. Kiểm tra tường lửa đã cho phép Python ở mạng Private (Windows Security → Firewall → Allow an app). Wi-Fi công cộng hoặc Wi-Fi khách thường chặn các máy nhìn thấy nhau, khi đó hãy phát hotspot từ điện thoại rồi cho laptop kết nối vào. |
| Mã QR trỏ sai địa chỉ (laptop có nhiều card mạng, VPN, máy ảo) | Mở mục "Địa chỉ nhập tay" và thử từng địa chỉ trên điện thoại. |
| Điện thoại báo "mã truy cập hết hạn" | Mỗi lần mở lại app sẽ có mã mới. Hãy quét lại mã QR. |
| Máy cắt sai khung | Bấm **Chỉnh góc**, hoặc chụp lại trên nền tối hơn. |

## Bảo mật

- App chỉ chạy trong mạng nội bộ. Ảnh không rời khỏi laptop.
- Điện thoại cần mã ngẫu nhiên có trong QR (đổi mỗi lần mở app) và chỉ có quyền **gửi ảnh**. Xem, xoá trang và xuất PDF chỉ làm được trên chính laptop.

## Cấu trúc mã nguồn

```
app.py               chạy web server (waitress)
scan_cli.py          quét hàng loạt bằng dòng lệnh
scanner/core.py      xử lý ảnh: dò khung, nắn phối cảnh, làm sạch, ghép PDF (OpenCV + img2pdf)
scanner/store.py     lưu các trang đang làm trong data/
scanner/server.py    các API và trang web (Flask)
scanner/templates/   giao diện laptop + điện thoại
scanner/static/      CSS, JavaScript
tests/               kiểm thử (pytest), dùng ảnh giả lập
```

Chạy test: `.venv\Scripts\python -m pip install pytest` rồi `.venv\Scripts\python -m pytest`.
