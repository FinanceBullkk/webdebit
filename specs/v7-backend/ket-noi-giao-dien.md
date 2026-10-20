# Kết nối giao diện V7 — hợp đồng bản thử

Bản chia sẻ đã lọc từ `codex/v7-opening-read` tại `011819e`, chuẩn bị ngày 21/10/2026. Nhật ký nguồn chứa tên/số liệu khách đã loại khỏi bản nhập; hồ sơ gốc chỉ đọc còn trên nhánh nguồn. Kết quả cũ không phải bằng chứng phiên này. Xem [báo cáo chuẩn bị](../../docs/v7-merge-prep.md).

**ĐỀ XUẤT:** schema `sokhach`, hàm PostgreSQL, HTTP API, công cụ bản sao là mã thử để review. Không phải migration production hay quyền ghi tiền thật. **ĐÃ CHỐT theo hồ sơ nguồn:** người dùng cho phép nối API thử ngày 20/10/2026; giữ bản fixture riêng, actor từ server, không lấy từ body. Chính sách xem [sổ quyết định](../../docs/decisions.md), nhất là V7-SO, V7-BE và V7-COPY. **ĐÃ TRIỂN KHAI:** mã thử trên nhánh nguồn; không xác nhận runtime hiện tại. **ĐÃ KIỂM CHỨNG phiên này:** chỉ ghi trong báo cáo chuẩn bị. **CÒN MỞ:** DB/browser tích hợp, nguồn thật, danh tính runtime, nghiệm thu và gate triển khai riêng.

## Thao tác, điểm vào và kiểm

| Thao tác | Điểm vào | Kiểm hiện có |
| --- | --- | --- |
| Mở sổ fixture | `preview/so-khach-v7.html`, fixture/model/UI V7 | `preview/test-so-khach-v7-model.js` |
| Mở sổ API | `preview/so-khach-v7-live.html`, `so-khach-v7-api.js`, `web/v7_ledger_api.py` | `preview/test-so-khach-v7-api.js`, `tests/test_v7_ledger_api.py` |
| Dán/sửa/điều chỉnh/thu/hủy/khóa | POST API, `tools/v7_backend_functions.sql` | fake HTTP/Node; `tools/test_pg_v7_backend.py` dành cho PostgreSQL cô lập, chưa chạy trong task này |
| Đọc/đối soát bản sao | `tools/v7_load_real_copy.py`, `tools/v7_reconcile_real_copy.py` | `tests/test_v7_load_real_copy.py`, dữ liệu giả |

## HTTP

- GET `/api/v7/customers`, `/api/v7/ledger?customer=<id>`.
- POST `/api/v7/trips/paste`, `/api/v7/trips/price`, `/api/v7/trips/adjust`, `/api/v7/months/adjust`, `/api/v7/receipts`, `/api/v7/receipts/meta`, `/api/v7/receipts/void`, `/api/v7/months/lock`.
- POST chỉ gửi ý định, `customer_id`, `expected_version`, `idempotency_key`; VND dạng chuỗi, `null` khác `"0"`. Không gửi actor, tổng hay phân bổ. Vẽ lại sau GET thành công.
- `STALE_LEDGER`: GET lại và yêu cầu xem dữ liệu mới, không phát lại ý định cũ. Lỗi mạng/`RESULT_UNKNOWN`: giữ cùng payload/key để thử lại, không tạo key mới trước khi biết kết quả.
- Mỗi tháng có `prior_months_vnd`, `charges_vnd`, `received_vnd`, `outstanding_vnd`, `end_of_month_vnd`. Gốc có `today_month`, `month_locks`; giờ Việt Nam từ server. Luôn hiện khối tháng hiện tại, ô tổng thiếu số hiện `–`.
- Chỉ bật ghi khi baseline active; khách chưa có baseline chưa thể ghi. `legacy_rows` để xem, không cộng lại. Dòng “Theo sổ gốc” lấy số server để đối chiếu, không tham gia tính số dư. Cờ kỹ thuật giữ trong DB/báo cáo nạp theo V7-COPY.
- Trang API dùng cùng origin cổng thử riêng; không thay route `so-khach-v7.html`, không dùng cổng 8777. Client không xác minh danh tính Tailscale thật; phần runtime còn mở.

## Bộ đọc nguồn — mã thử, không chạy nguồn thật trong task này

- XLSX đọc bằng XML stdlib; CSV/XLSX giả trong test. Giữ NULL, cờ nguồn, hash nguồn; lỗi số tiền không nguyên trả `NON_INTEGER_AMOUNT`, không tự làm tròn.
- Gate chuỗi mỏ neo, FIFO và tổng từng khách/tháng vẫn bắt buộc. Khách không khớp bị giữ, không tự ép khớp. `--check-source` là đọc/đối soát, không nạp DB, nhưng vẫn ghi báo cáo vào đường dẫn ngoài repo được định nghĩa trong công cụ.
- Quy tắc V7-COPY: giữ TOTAL lịch sử dù thiếu đơn giá; số chuyển sang trống coi là 0 chỉ khi mỏ neo cuối tháng kiểm được; CSV thiếu dòng ghi cờ; tổng khớp nhưng chia tháng khác thì bản sao dùng FIFO từ Sheet.
- Theo ghi nhận người dùng 20/10/2026 trong tài liệu nhánh nguồn: tháng 1 có khối năm trước dùng số chuyển sang đã gõ, ghi chênh thành dòng `YEAR_END_CARRY_ADJUSTED`; dòng tổng có tiền nhưng chuyến thiếu giá thì chia nguyên đồng cho các chuyến đó (`TOTAL_SPREAD_OVER_TRIPS`, dư đồng cho dòng đầu). Đây là phạm vi bản sao được ghi nhận ở nguồn, không mở quyền áp dụng production; chưa có mục riêng trong sổ quyết định đã commit.
- `--raw-tab` chọn tên tab nguyên văn khi chỉ khác khoảng trắng, không tự gộp. Nguồn không đủ/cache thiếu/chuỗi lệch vẫn bị giữ. Nguồn đã sửa sau bản xuất phải xuất lại và đối chiếu đúng mốc.
- Công cụ Docker chỉ dành cho bản sao dùng một lần, `--network none`, bind localhost, full ID và nhãn run khi dọn. Không chạy demo/harness/loader trong nhiệm vụ chuẩn bị gộp.

## Còn mở

- Chứng minh bản xuất đúng mốc v2, tính đủ mọi dòng/khách, Sheet có tiếp tục nhập song song hay không.
- Số lẻ đồng, lịch sử thiếu giá được báo giá sau mốc, tab có thay đổi sau xuất, phân loại mặt hàng còn thiếu.
- `adjust_trip` ở tháng mở lệch model JS; chuyển âm giữa sổ/hoàn tiền; ai xem lịch sử; mốc chuyển lần hai.
- Duyệt chính xác phạm vi frontend/API thử và tự đi luồng nghiệp vụ; test fixture không thay nghiệm thu.
