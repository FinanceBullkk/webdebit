# Kết nối giao diện V7 — hợp đồng bản thử

Bản chia sẻ đã lọc từ `codex/v7-opening-read` tại `011819e`, bổ sung đúng `dcb46a1`, `d162c63`, `451efa2`, `f9fd099` ngày 21/10/2026. Nhật ký nguồn chứa tên/số liệu khách đã loại khỏi bản nhập; hồ sơ gốc chỉ đọc còn trên nhánh nguồn. Kết quả cũ không phải bằng chứng phiên này. Xem [báo cáo chuẩn bị](../../docs/v7-merge-prep.md#vòng-2).

**ĐỀ XUẤT:** schema `sokhach`, hàm PostgreSQL, HTTP API, công cụ bản sao là mã thử để review. Không phải migration production hay quyền ghi tiền thật. **ĐÃ CHỐT theo hồ sơ nguồn:** người dùng cho phép nối API thử ngày 20/10/2026; giữ bản fixture riêng, actor từ server, không lấy từ body. Chính sách xem [sổ quyết định](../../docs/decisions.md), nhất là V7-SO, V7-BE và V7-COPY. **ĐÃ TRIỂN KHAI:** mã thử trên nhánh nguồn; không xác nhận runtime hiện tại. **ĐÃ KIỂM CHỨNG phiên này:** chỉ ghi trong báo cáo chuẩn bị. **CÒN MỞ:** DB/browser tích hợp, nguồn thật, danh tính runtime, nghiệm thu và gate triển khai riêng.

## Thao tác, điểm vào và kiểm

| Thao tác | Điểm vào | Kiểm hiện có |
| --- | --- | --- |
| Mở sổ fixture | `preview/so-khach-v7.html`, fixture/model/UI V7 | `preview/test-so-khach-v7-model.js` |
| Mở sổ API | `preview/so-khach-v7-live.html`, `so-khach-v7-api.js`, `web/v7_ledger_api.py` | `preview/test-so-khach-v7-api.js`, `tests/test_v7_ledger_api.py` |
| Dán/sửa/điều chỉnh/thu/hủy/khóa | POST API, `tools/v7_backend_functions.sql` | fake HTTP/Node; `tools/test_pg_v7_backend.py` dành cho PostgreSQL cô lập, chưa chạy trong task này |
| Đọc/đối soát bản sao | `tools/v7_load_real_copy.py`, `tools/v7_reconcile_real_copy.py` | `tests/test_v7_load_real_copy.py`, dữ liệu giả |
| Xuất bản đã làm sạch | `tools/v7_export_clean.py` | `tests/test_v7_export_clean.py`, dữ liệu giả, manifest/hash và chặn đường ghi trong repo |

## HTTP

- GET `/api/v7/customers`, `/api/v7/ledger?customer=<id>`.
- POST `/api/v7/trips/paste`, `/api/v7/trips/price`, `/api/v7/trips/adjust`, `/api/v7/months/adjust`, `/api/v7/receipts`, `/api/v7/receipts/meta`, `/api/v7/receipts/void`, `/api/v7/months/lock`.
- POST chỉ gửi ý định, `customer_id`, `expected_version`, `idempotency_key`; VND dạng chuỗi, `null` khác `"0"`. Không gửi actor, tổng hay phân bổ. Vẽ lại sau GET thành công.
- `STALE_LEDGER`: GET lại và yêu cầu xem dữ liệu mới, không phát lại ý định cũ. Lỗi mạng/`RESULT_UNKNOWN`: giữ cùng payload/key để thử lại, không tạo key mới trước khi biết kết quả.
- Mỗi tháng có `prior_months_vnd`, `charges_vnd`, `received_vnd`, `outstanding_vnd`, `end_of_month_vnd`. Gốc có `today_month`, `month_locks`; giờ Việt Nam từ server. Luôn hiện khối tháng hiện tại, ô tổng thiếu số hiện `–`.
- Chỉ bật ghi khi baseline active; khách chưa có baseline chưa thể ghi. `legacy_rows` để xem, không cộng lại. Dòng “Theo sổ gốc” lấy số server để đối chiếu, không tham gia tính số dư. Cờ kỹ thuật giữ trong DB/báo cáo nạp theo V7-COPY.
- Trang API dùng cùng origin cổng thử riêng; không thay route `so-khach-v7.html`, không dùng cổng 8777. Client không xác minh danh tính Tailscale thật; phần runtime còn mở.

## Bộ đọc nguồn — mã thử, không chạy nguồn thật trong task này

- XLSX đọc bằng XML stdlib; CSV/XLSX giả trong test. Giữ NULL, cờ nguồn, hash nguồn. Theo ghi nhận người dùng trong `dcb46a1`, bước làm sạch nguồn đọc số lẻ thành đồng nguyên, giữ Decimal chính xác khi quét và cờ `ROUNDED_VND`; không đổi bigint của lược đồ. Chuyến làm tròn nửa lên, thu nửa xuống; nếu tổng chính xác khớp dòng cộng nguyên đồng thì chia theo phần dư lớn nhất, ưu tiên dòng đầu khi bằng nhau (`ROUNDING_APPORTIONED`). Tổng tháng làm tròn phát sinh, tính thu để số dư bằng số dư chính xác làm tròn nửa lên (`ROUNDED_MONTH_TOTALS`). Chuỗi mỏ neo vẫn phải khớp; ô không đọc được vẫn giữ khách. Không còn phát sinh `NON_INTEGER_AMOUNT` trong bước đọc tiền này. Đây là phạm vi làm sạch bản sao theo nguồn, không tự đổi chính sách tiền của production.
- Gate chuỗi mỏ neo, FIFO và tổng từng khách/tháng vẫn bắt buộc. Khách không khớp bị giữ, không tự ép khớp. `--check-source` là đọc/đối soát, không nạp DB, nhưng vẫn ghi báo cáo vào đường dẫn ngoài repo được định nghĩa trong công cụ.
- Quy tắc V7-COPY: giữ TOTAL lịch sử dù thiếu đơn giá; số chuyển sang trống coi là 0 chỉ khi mỏ neo cuối tháng kiểm được; CSV thiếu dòng ghi cờ; tổng khớp nhưng chia tháng khác thì bản sao dùng FIFO từ Sheet.
- Theo ghi nhận người dùng 20/10/2026 trong tài liệu nhánh nguồn: tháng 1 có khối năm trước dùng số chuyển sang đã gõ, ghi chênh thành dòng `YEAR_END_CARRY_ADJUSTED`; dòng tổng có tiền nhưng chuyến thiếu giá thì chia nguyên đồng cho các chuyến đó (`TOTAL_SPREAD_OVER_TRIPS`, dư đồng cho dòng đầu). Đây là phạm vi bản sao được ghi nhận ở nguồn, không mở quyền áp dụng production; chưa có mục riêng trong sổ quyết định đã commit.
- `--raw-tab` chọn tên tab nguyên văn khi chỉ khác khoảng trắng, không tự gộp. Nguồn không đủ/cache thiếu/chuỗi lệch vẫn bị giữ. Nguồn đã sửa sau bản xuất phải xuất lại và đối chiếu đúng mốc.
- Khoản bảo hiểm mà CSV ghi âm được so cùng độ lớn với ô XLSX dương; mặc định tính phát sinh. Nếu khách còn lý do giữ, thử cách đọc như thu và chỉ chọn khi ít lý do giữ hơn, ghi `INSURANCE_AS_RECEIPT`; chuỗi mỏ neo từng tháng vẫn phải đóng. Dòng chuyển sang không nhãn có TOTAL mẫu bằng 0 vẫn nhận là carry.
- `--sheet-is-truth` ở loader/reconcile: theo ghi nhận người dùng 21/10/2026 trong `451efa2`, ưu tiên XLSX mới hơn CSV/opening cũ. Khác dòng CSV thành `CSV_STALE_ROWS`, khác tổng opening thành `OPENING_TOTAL_DIFFERS_FROM_HAO`, bucket lấy FIFO từ Sheet (`BUCKETS_FROM_SHEET`). Không bật cờ thì vẫn giữ khách khi lệch như trước. Cờ không bỏ kiểm mỏ neo/FIFO/ô tiền không đọc được; không tự cho phép cập nhật opening thật.
- Theo ghi nhận người dùng 21/10/2026 trong `f9fd099`, bản đã làm sạch là mốc đối chiếu về sau. Exporter bắt buộc `--xlsx` và `--out` (không có đích mặc định), nhận `--source-dir` và `--raw-tab`; dùng cách đọc `sheet_is_truth`, xuất `clean_customers.csv`, `clean_months.csv`, `clean_rows.csv`, `manifest.json` có SHA-256 nguồn/file và revision công cụ. Có khách thuộc `TONG` còn bị giữ thì thoát 2, không xuất. Không in tên/số tiền ra stdout. Mọi đích ghi và staging tạm phải ngoài repo sau resolve; từ chối repo/worktree Git khác, thư mục không trống và ghi đè. Hàm `export()`/`write_csv()` cũng kiểm đường ghi. File xuất chứa dữ liệu nhạy cảm, giữ ngoài Git; nhiệm vụ này chỉ kiểm fixture giả.
- Công cụ Docker chỉ dành cho bản sao dùng một lần, `--network none`, bind localhost, full ID và nhãn run khi dọn. Không chạy demo/harness/loader trong nhiệm vụ chuẩn bị gộp.

## Còn mở

- Chứng minh bản xuất đúng mốc v2, tính đủ mọi dòng/khách, Sheet có tiếp tục nhập song song hay không.
- Nghiệm thu quy tắc làm sạch số lẻ trên nguồn được cấp quyền; lịch sử thiếu giá được báo giá sau mốc, tab có thay đổi sau xuất, phân loại mặt hàng còn thiếu.
- Chọn mốc opening tiếp theo và quyền áp dụng dữ liệu Sheet mới nhất lên bản sao/production là việc riêng; không suy ghi nhận trong nhánh nguồn thành quyền chạy thật trong nhiệm vụ nhập mã.
- `adjust_trip` ở tháng mở lệch model JS; chuyển âm giữa sổ/hoàn tiền; ai xem lịch sử; mốc chuyển lần hai.
- Duyệt chính xác phạm vi frontend/API thử và tự đi luồng nghiệp vụ; test fixture không thay nghiệm thu.
