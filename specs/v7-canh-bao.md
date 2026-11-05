# Cảnh báo email khi máy công nợ lỗi hoặc dừng

Trạng thái: ĐÃ CHỐT (người dùng chọn email, 4/11/2026, [`CANH-BAO-01`](../docs/decisions/canh-bao-01.md))

## Đầu ra

- `tools/v7_watchdog.py`: kiểm tại chỗ, chỉ đọc, rồi báo về một check trên healthchecks.io. Có `--dry-run` và `--test-fail`.
- Timer `v7-watchdog` trên `hao`, 15 phút một lần, cả ngày. Link ping ở `/etc/webdebit/alert.env`, ngoài Git.
- Chủ sổ nhận email khi chuyển sang lỗi và khi hết lỗi. `hao` tắt thì email tới sau tối đa khoảng một giờ.

## Đối chiếu dữ liệu và code hiện có

| Kiểm | Lấy từ | Ngưỡng |
| --- | --- | --- |
| Web và DB | `GET /healthz` trên loopback, chạy `SELECT 1` qua đường psql của app | Khác 200 |
| Lượt đối soát còn mới | `checked_at`, `last_error` trong `reconcile.json` | Từ 10 tới 22 giờ VN quá 3 giờ, lúc nào cũng quá 14 giờ. Cùng luật với `reconcileOld` của tab Việc cần làm |
| Máy ghi có vấn đề | `customers[].reason` trong `reconcile.json` | `VERIFY_FAILED`; `WRITE_ERROR`, `CHECK_ERROR` trừ `STALE_LEDGER` (người vừa sửa sổ, lượt sau tính lại) |
| Bản chụp Sheet | Giờ sửa của `snapshot.json`, `prices.json`, `receipts.json`, `road.json`, `ps.json` | Quá 60 phút. Runner 15 phút một lần, lỗi lẻ tự lành (audit DevOps mục 14: 5 lần trong 2 ngày) |
| Timer | `systemctl show`: đối soát, đồng bộ Sheet, giá Sheet, PS, 4 sao lưu | Không `active` |
| Sao lưu | `Result` của service; `LastTriggerUSec` của timer | `Result` khác `success`; hourly quá 12 giờ, ba loại còn lại quá 26 giờ |
| Đĩa | `/`, `/srv`, `/var/lib/postgresql` | Dưới 10% trống |

Cấu hình trên healthchecks.io: một check, chu kỳ 15 phút, thời gian chờ 45 phút. Gói miễn phí có 20 check, giữ 100 sự kiện mỗi check. Đo trên `hao` 4/11/2026: gọi được ra ngoài qua HTTPS, chưa có dịch vụ gửi thư.

## Nguồn quyết định

- [`CANH-BAO-01`](../docs/decisions/canh-bao-01.md), [`MAY-DOI-SOAT-01`](../docs/decisions/may-doi-soat-01.md). Audit DevOps 31/10/2026 mục 2 và 14, ngoài Git.

## Hành vi và bất biến

- Chỉ đọc. Không ghi DB, không đổi file nào ngoài journal.
- Một phép kiểm hỏng không che các phép kiểm khác: nó thành một dòng "Không kiểm được phần …".
- Nội dung gửi đi không có tên khách, số tiền. Link ping là bí mật: không in ra journal, không vào Git.
- Mạng chập chờn thì thử lại 3 lần. Vẫn không được thì thoát khác 0 và để dịch vụ tự báo khi quá giờ.
- Máy canh tự chết thì cũng không còn ping, nên vẫn có email.
- Không có link ping thì chỉ in ra journal, thoát 0.

## Tiêu chí nghiệm thu

- [x] `tests/test_v7_watchdog.py`: từng phép kiểm, lỗi lẻ không báo, đêm không tính là dừng, không lộ tên khách, thử lại khi mạng lỗi, không in link ping.
- [ ] Chạy trên `hao` dưới `v7app`, trong sandbox của unit: mọi phép kiểm đọc được, kết quả "ổn" khớp thực tế.
- [ ] Chủ sổ tạo check và đặt link ping lên `hao`.
- [ ] `--test-fail`: email tới hộp thư chủ sổ; lượt kế có email hết lỗi.
- [ ] Dừng thử: ngừng timer máy canh quá thời gian chờ thì có email, bật lại thì có email hết lỗi.
