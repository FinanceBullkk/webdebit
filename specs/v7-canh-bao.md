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
| Log sửa Sheet | `edit_log` trong `reconcile.json` ([`SHEET-LOG-01`](../docs/decisions/sheet-log-01.md)) | `STALE`; `UNAVAILABLE` với mã 401, 403, 404. Hết giờ, lỗi 5xx của Google thì lượt sau tự lành, không báo |
| Bản chụp Sheet | Giờ sửa của `snapshot.json`, `prices.json`, `receipts.json`, `road.json`, `ps.json` | Quá 60 phút. Runner 15 phút một lần, lỗi lẻ tự lành (audit DevOps mục 14: 5 lần trong 2 ngày) |
| Nguồn booking còn chuyến mới (bổ sung 18/11/2026) | `rows[].event_date` của `snapshot.json` (`CONT_NGUON`, chuyến biển) và `road.json` (`CONT_BO`, chuyến bộ) | Không dòng nào mang ngày trong 3 ngày gần nhất kể cả hôm nay (`WEBDEBIT_ALERT_SOURCE_DAYS`). Bỏ qua ngày sau hôm nay và ô ngày hỏng. Đo từ 1/5/2026: hai nguồn chưa từng trống quá 2 ngày liền; Tết thì báo là đúng. Không áp cho bảng PS: chỉ giữ dòng có phí nên thưa (có lúc trống 85 ngày) |
| Hộp việc của API (bổ sung 18/11/2026) | Phần `inbox` của `GET /healthz`: `state`, `books`, `failed`, `failed_rounds`, `computed_age_seconds`, chỉ số đếm | `state` là `unavailable`; có sổ lỗi từ 2 lượt nền liền trở lên; chưa tính lại quá 90 phút. Web không trả lời thì im (phần web đã báo); API cũ chưa có phần này thì cũng im |
| Timer | `systemctl show`: đối soát, đồng bộ Sheet, giá Sheet, PS, 4 sao lưu | Không `active` |
| Sao lưu | `Result` của service; `LastTriggerUSec` của timer | `Result` khác `success`; hourly quá 12 giờ, ba loại còn lại quá 26 giờ |
| Đĩa | `/`, `/srv`, `/var/lib/postgresql` | Dưới 10% trống |

Cấu hình trên healthchecks.io: một check, chu kỳ 15 phút, thời gian chờ 45 phút. Gói miễn phí có 20 check, giữ 100 sự kiện mỗi check. Đo trên `hao` 4/11/2026: gọi được ra ngoài qua HTTPS, chưa có dịch vụ gửi thư.

## Nguồn quyết định

- [`CANH-BAO-01`](../docs/decisions/canh-bao-01.md), [`MAY-DOI-SOAT-01`](../docs/decisions/may-doi-soat-01.md). Audit DevOps 31/10/2026 mục 2 và 14, ngoài Git.
- Hai phép kiểm bổ sung 18/11/2026 từ diễn tập sang tháng 12 trên bản sao (PC, Docker không mạng, giờ giả 30/11–3/12): (1) nguồn booking là tab gộp phía Sheet, tab tháng mới chưa vào tab gộp thì bản chụp vẫn mới mà không thêm chuyến, máy canh cũ không thấy; (2) bản chụp chuyến không đọc được làm hộp việc đánh lỗi mọi sổ, máy ngừng dán chuyến và ghi giá, bộ đếm lỗi tự ghi vẫn 0, máy canh cũ không thấy.

## Hành vi và bất biến

- Chỉ đọc. Không ghi DB, không đổi file nào ngoài journal.
- Một phép kiểm hỏng không che các phép kiểm khác: nó thành một dòng "Không kiểm được phần …".
- Nội dung gửi đi không có tên khách, số tiền. Link ping là bí mật: không in ra journal, không vào Git.
- Mạng chập chờn thì thử lại 3 lần. Vẫn không được thì thoát khác 0 và để dịch vụ tự báo khi quá giờ.
- Máy canh tự chết thì cũng không còn ping, nên vẫn có email.
- Không có link ping thì chỉ in ra journal, thoát 0.

## Tiêu chí nghiệm thu

- [x] `tests/test_v7_watchdog.py`: từng phép kiểm, lỗi lẻ không báo, đêm không tính là dừng, không lộ tên khách, thử lại khi mạng lỗi, không in link ping.
- [x] Bổ sung 18/11/2026: `tests/test_v7_watchdog.py` (nguồn trống theo từng nguồn, khoảng trống 2 ngày như dữ liệu thật không báo, ngày sau hôm nay và ô hỏng không che việc dừng; hộp việc: lỗi phải lặp 2 lượt, không đọc được bản chụp, nhịp nền dừng, thân của 503 vẫn đọc), `tests/test_v7_inbox.py` (đếm lượt lỗi liền, tự lành về 0, thiếu bản chụp thành `unavailable`), `tests/test_v7_api_healthz.py` (phần `inbox` chỉ có số đếm).
- [ ] Bổ sung 18/11/2026: sau `Deploy hao`, một lượt máy canh trên `hao` ra "ổn" với hai phép kiểm mới.
- [ ] Chạy trên `hao` dưới `v7app`, trong sandbox của unit: mọi phép kiểm đọc được, kết quả "ổn" khớp thực tế.
- [ ] Chủ sổ tạo check và đặt link ping lên `hao`.
- [ ] `--test-fail`: email tới hộp thư chủ sổ; lượt kế có email hết lỗi.
- [ ] Dừng thử: ngừng timer máy canh quá thời gian chờ thì có email, bật lại thì có email hết lỗi.
